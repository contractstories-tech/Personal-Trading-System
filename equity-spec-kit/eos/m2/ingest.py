"""M2 ingestion: raw NSE files -> versioned observations with honest availability (Document 02 s3, s6, s17).

Versioning. Source observations are keyed by the exchange source instrument when available (UDiFF FinInstrmId),
falling back to ISIN+series for legacy files. Re-ingesting identical content writes nothing. Changed content writes a new
version that supersedes the latest; a later complete-file withdrawal is represented by an explicit tombstone.

Availability. usable_from = greatest(effective_from, system_available_at).
  live      source_published_at = given (else received_at); system_available_at = processing time.
  backfill  the FIRST version of a row gets the policy's inferred publication time on its trade date,
            flagged availability_inferred. A LATER version is never inferred: we only know it existed
            when we received it, so system_available_at = received_at.

All semantic checks run before observations are written. The raw receipt is the exception: once bytes are durably
landed, receipt metadata is committed immediately even if parsing or later quality checks reject the file.
Row-level defects (malformed or duplicate ISIN, impossible OHLC, invalid quantities, an unmapped delivery
symbol) quarantine the row instead of rejecting the day (r5.5, audit C5); the file is rejected only when the
quarantined share exceeds quality.max_quarantine_share, or on a structural fault (header, dates, canary prefix).
Backfill inference is refused for a file received on its own trade date or on/after live_capture_start
(r5.5, audit B3b): a replay must never see a file its live run did not have.
Raw landing (r5.7). Before anything is parsed, the file's exact bytes are landed write-once in the warehouse
(_raw/<source_id>/<sha256><ext>) and a raw_file receipt is committed in its own transaction. Parsing reads the
landed copy. A second transaction records the parse outcome and, on success, observations/conflicts/coverage.
Thus parser failure cannot erase the historical fact that the bytes were received.
The parse/observation transaction is one warehouse batch, written under one writer lock (review B2, B3): observations, conflicts,
coverage and the ingestion-log entry become visible together or not at all, and no second ingestion can
allocate a version between this one's read and its commit.
"""
import datetime as dt
import decimal
import fractions
import os

from .. import canary
from ..source_policy import load as load_policy
from ..timeutil import IST, at_ist
from . import parsers

PRICE_FIELDS = ("symbol", "series", "open", "high", "low", "close", "prev_close", "volume", "traded_value", "num_trades")
DELIVERY_FIELDS = ("symbol", "series", "delivery_qty", "traded_qty_reported", "delivery_pct_reported")
CROSSCHECK_DELIVERY_FIELDS = ("symbol", "series", "delivery_available", "delivery_qty", "traded_qty_reported", "delivery_pct_reported")
MASTER_FIELDS = ("symbol", "series", "name", "isin", "instrument_type", "normal_market_status",
                 "normal_market_eligibility", "price_range_text", "price_range_type", "max_price", "min_price",
                 "tick_size", "delete_flag", "is_dummy", "status_code_known",
                 "security_class", "market_eligible", "effective_session", "effective_session_basis")


class QualityError(Exception):
    """Parsed file rejected; a durable raw receipt may already exist, but no rejected observations are committed."""


class KillSwitch(QualityError):
    """Row count collapsed versus the prior session; no parsed observations are written or published."""


def _source_key(r):
    """Stable identity of one exchange source observation within a session.

    Current UDiFF/MII data carries FinInstrmId.  Legacy bhavcopy/MTO data does not, so the fallback is
    intentionally series-aware: one ISIN may legitimately have EQ and BL observations on the same date.
    """
    sid = r.get("source_instrument_id")
    return ("src", str(sid)) if sid not in (None, "") else ("legacy", r.get("isin"), r.get("series"))


def _latest(rows):
    out = {}
    for r in rows:
        if canary.is_canary(r["isin"]):
            continue
        k = _source_key(r)
        if k not in out or r["version_no"] > out[k]["version_no"]:
            out[k] = r
    return out


def _check_backfill_allowed(trade_date, received_at, pol):
    b = pol["backfill"]
    start = b.get("live_capture_start")
    if start is not None and trade_date >= dt.date.fromisoformat(str(start)):
        raise QualityError(f"{trade_date}: on or after live_capture_start {start}; ingest it in live mode")
    received_day = received_at.astimezone(IST).date()
    if (received_day - trade_date).days < b["min_age_days"]:
        raise QualityError(f"{trade_date}: received {received_at.astimezone(IST).isoformat()}, fewer than "
                           f"{b['min_age_days']} day(s) after the trade date; a same-day file is a live file")


def _availability(source_id, mode, first_version, trade_date, received_at, published, now, pol):
    rule = pol["sources"][source_id]["availability"]
    lag = dt.timedelta(minutes=rule["policy_lag_minutes"])
    if mode == "backfill" and first_version:
        pub = at_ist(trade_date, rule["inferred_published_time_ist"])
        eff = pub + lag
        return dict(source_published_at=pub, effective_from=eff, system_available_at=eff, usable_from=eff,
                    availability_inferred=True)
    if mode not in ("backfill", "live"):
        raise ValueError(f"mode {mode!r}")
    pub = published or received_at
    eff = pub + lag
    sysav = now if mode == "live" else received_at
    if sysav is None:
        raise ValueError("live ingestion needs the processing time `now`")
    return dict(source_published_at=pub, effective_from=eff, system_available_at=sysav,
                usable_from=max(eff, sysav), availability_inferred=False)


def _neutral(table):
    if table == "price_observation":
        one = parsers.D4 * 10000
        return dict(open=one, high=one, low=one, close=one, prev_close=one, volume=1, traded_value=one, num_trades=1)
    if table == "delivery_crosscheck_observation":
        return dict(delivery_available=True, delivery_qty=0, traded_qty_reported=1, delivery_pct_reported=parsers.D4 * 0)
    return dict(delivery_qty=0, traded_qty_reported=1, delivery_pct_reported=parsers.D4 * 0)


def _latest_events(wh, table, trade_date):
    key = trade_date.isoformat()
    obs = wh.read(table, [key]) if key in wh.partitions(table) else []
    tombs = [r for r in (wh.read("observation_tombstone", [key]) if key in wh.partitions("observation_tombstone") else [])
             if r["table_name"] == table]
    latest = {}
    for r in obs + tombs:
        if r.get("isin") and canary.is_canary(r["isin"]):
            continue
        k = _source_key(r)
        if k not in latest or r["version_no"] > latest[k]["version_no"]:
            latest[k] = r
    return obs, latest


def _version(wh, table, trade_date, parsed, fields, meta, mode, received_at, published, now, pol, sha,
             suppressed_absent_keys=None, tombstone_missing=True):
    """Version source observations and explicit withdrawals.

    A complete reissue that omits a previously active source observation creates a tombstone.  A row
    quarantined in the reissue is supplied in suppressed_absent_keys: it is neither accepted nor mis-labelled
    as an exchange withdrawal.
    """
    existing, latest = _latest_events(wh, table, trade_date)
    suppressed_absent_keys = set(suppressed_absent_keys or ())
    new, tombstones, conflicts = [], [], []
    rows_new = rows_changed = unchanged = 0
    for r in parsed:
        k = _source_key(r)
        prev = latest.get(k)
        prev_active = prev is not None and prev.get("table_name") is None
        if prev_active and all(prev.get(f) == r.get(f) for f in fields):
            unchanged += 1
            continue
        v = 1 if prev is None else prev["version_no"] + 1
        if prev is None:
            rows_new += 1
        else:
            rows_changed += 1
        av = _availability(meta["source_id"], mode, prev is None, trade_date, received_at, published, now, pol)
        row = {**r, **meta, **av, "trade_date": trade_date, "version_no": v, "received_at": received_at,
               "supersedes_version": None if prev is None else prev["version_no"], "file_sha256": sha}
        if row["usable_from"] < row["source_published_at"]:
            raise QualityError(f"{r['isin']}: usable_from before source_published_at")
        new.append(row)

    seen = {_source_key(r) for r in parsed}
    if tombstone_missing:
        for k, prev in sorted(latest.items(), key=lambda kv: repr(kv[0])):
            if k in seen or k in suppressed_absent_keys or prev.get("table_name") is not None:
                continue
            av = _availability(meta["source_id"], mode, False, trade_date, received_at, published, now, pol)
            tombstones.append({
                "table_name": table, "source_instrument_id": prev.get("source_instrument_id"),
                "isin": prev.get("isin"), "series": prev.get("series"), "trade_date": trade_date,
                "version_no": prev["version_no"] + 1, "source_id": meta["source_id"], "file_sha256": sha,
                "received_at": received_at, "usable_from": av["usable_from"],
                "availability_inferred": av["availability_inferred"], "supersedes_version": prev["version_no"],
                "reason": "absent_from_complete_reissue", "domain": meta["domain"],
            })
            conflicts.append({
                "table_name": table, "source_instrument_id": prev.get("source_instrument_id"),
                "isin": prev.get("isin"), "series": prev.get("series"), "trade_date": trade_date,
                "kind": "withdrawn_in_reissue",
                "detail": f"present at v{prev['version_no']}, absent from complete file {sha[:12]}; tombstoned",
                "file_sha256": sha, "logged_at": received_at,
            })

    if not existing and new:
        new = canary.sentinels(table, trade_date, "exchange_eod", _neutral(table)) + new
    return new, tombstones, conflicts, dict(rows_new=rows_new, rows_changed=rows_changed, rows_unchanged=unchanged)


ACQUISITION_METHODS = {"manual_upload", "scheduled_download", "api", "vendor_drop", "archive_import"}


def _validate_provenance(method, source_url, retrieved_at, received_at):
    if method not in ACQUISITION_METHODS:
        raise QualityError(f"unknown acquisition_method {method!r}")
    if not isinstance(received_at, dt.datetime) or received_at.tzinfo is None:
        raise QualityError("received_at must be timezone-aware")
    if method in {"scheduled_download", "api"}:
        if not source_url:
            raise QualityError(f"{method} acquisition requires source_url")
        if retrieved_at is None:
            raise QualityError(f"{method} acquisition requires retrieved_at")
    if method in {"vendor_drop", "archive_import"} and retrieved_at is None:
        raise QualityError(f"{method} acquisition requires retrieved_at")
    if retrieved_at is not None:
        if not isinstance(retrieved_at, dt.datetime) or retrieved_at.tzinfo is None:
            raise QualityError("retrieved_at must be timezone-aware")
        if retrieved_at > received_at:
            raise QualityError("retrieved_at cannot be after received_at")


def _receipt_key(received_at):
    return received_at.astimezone(IST).date().isoformat()


def _land(wh, source_id, path, received_at, source_url, retrieved_at, acquisition_method):
    _validate_provenance(acquisition_method, source_url, retrieved_at, received_at)
    sha, rel, size = wh.land(source_id, path)
    raw = {"source_id": source_id, "file_sha256": sha, "original_name": os.path.basename(path),
           "source_url": source_url, "retrieved_at": retrieved_at, "received_at": received_at,
           "size_bytes": size, "landed_path": rel, "acquisition_method": acquisition_method}
    # Receipt writes are idempotent for the same acquisition event. This matters when transaction 2 crashes
    # after transaction 1 and orchestration retries the same input with the same receipt timestamp.
    key = _receipt_key(received_at)
    if raw not in wh.read("raw_file", [key]):
        wh.append("raw_file", key, [raw])
    return sha, wh.raw_path(rel), raw


def _rejected_parse_event(wh, raw, exc):
    row = {"source_id": raw["source_id"], "file_sha256": raw["file_sha256"], "received_at": raw["received_at"],
           "parsed_at": dt.datetime.now(dt.timezone.utc), "status": "rejected", "source_format": None,
           "trade_date": None, "parse_error": f"{type(exc).__name__}: {exc}"}
    wh.append("raw_parse_event", _receipt_key(raw["received_at"]), [row])


def _parsed_event(raw, fmt, day):
    return {"source_id": raw["source_id"], "file_sha256": raw["file_sha256"], "received_at": raw["received_at"],
            "parsed_at": dt.datetime.now(dt.timezone.utc), "status": "parsed", "source_format": fmt,
            "trade_date": day, "parse_error": None}


def _commit(wh, table, source_id, trade_date, new, conflicts, counts, sha, received_at, mode, n_rows, _crash_at=None,
            quarantine=(), parse_event=None, tombstones=()):
    """Transaction 2: every successful parse output is committed atomically."""
    key = trade_date.isoformat()
    b = wh.batch()
    if parse_event is not None:
        b.add("raw_parse_event", _receipt_key(received_at), [parse_event])
    b.add(table, key, new)
    b.add("observation_tombstone", key, list(tombstones))
    b.add("data_conflict", key, conflicts)
    b.add("row_quarantine", key, list(quarantine))
    cov = [r for r in wh.read("source_coverage", [key]) if r["source_id"] == source_id]
    if not cov:
        real = [r["usable_from"] for r in new if not canary.is_canary(r["isin"])] or \
               [r["usable_from"] for r in wh.read(table, [key]) if not canary.is_canary(r["isin"])]
        b.add("source_coverage", key, [{
            "source_id": source_id, "trade_date": trade_date, "complete": True, "rows": n_rows,
            "file_sha256": sha, "usable_from": min(real), "received_at": received_at, "domain": "exchange_eod"}])
    b.add("ingestion_log", key, [{"file_sha256": sha, "source_id": source_id, "trade_date": trade_date,
                                  "received_at": received_at, "mode": mode, **counts}])
    b.commit(_crash_at)


def _already(wh, sha, day, source_id):
    """Source-scoped duplicate check, reading only the date's log partition.

    A byte-identical payload under a different source ID is independent evidence and must not become a false noop.
    """
    key = day.isoformat()
    if key not in wh.partitions("ingestion_log"):
        return False
    return any(r["file_sha256"] == sha and r["source_id"] == source_id for r in wh.read("ingestion_log", [key]))


def _quarantine_row(table, day, r, reason, detail, sha, received_at):
    return {"table_name": table, "trade_date": day, "source_instrument_id": r.get("source_instrument_id"),
            "isin": r.get("isin"), "symbol": r.get("symbol"), "series": r.get("series"), "reason": reason, "detail": detail, "file_sha256": sha,
            "logged_at": received_at}


def _enforce_quarantine_share(path, quarantined, total, pol):
    limit = fractions.Fraction(str(pol["quality"]["max_quarantine_share"]))
    if total and fractions.Fraction(len(quarantined), total) > limit:
        reasons = "; ".join(f"{q['symbol'] or q['isin']}: {q['detail']}" for q in quarantined[:10])
        raise QualityError(f"{path}: {len(quarantined)} of {total} row(s) failed row checks, above the "
                           f"{pol['quality']['max_quarantine_share']:.0%} quarantine limit - nothing written: {reasons}")


def ingest_bhavcopy(wh, path, received_at, mode="backfill", published=None, now=None, expect_date=None, policy=None,
                    source_url=None, retrieved_at=None, acquisition_method="manual_upload", _crash_at=None):
    with wh.writer():
        return _ingest_bhavcopy(wh, path, received_at, mode, published, now, expect_date, policy, source_url,
                                retrieved_at, acquisition_method, _crash_at)


def _ingest_bhavcopy(wh, path, received_at, mode, published, now, expect_date, policy, source_url, retrieved_at,
                     acquisition_method, _crash_at):
    pol = policy or load_policy()
    sha, landed, raw = _land(wh, "nse_cm_bhavcopy", path, received_at, source_url, retrieved_at, acquisition_method)
    try:
        fmt, day, rows = parsers.parse_bhavcopy(parsers.read_bytes(landed), os.path.basename(path))
    except Exception as exc:
        _rejected_parse_event(wh, raw, exc)
        raise
    if _already(wh, sha, day, "nse_cm_bhavcopy"):
        return {"noop": True, "file_sha256": sha}
    if expect_date and day != expect_date:
        raise QualityError(f"{path}: file is for {day}, expected {expect_date}")
    if mode == "backfill":
        _check_backfill_allowed(day, received_at, pol)

    # ---- checks (Document 02 s17), all before any write
    structural = [r["isin"] for r in rows if canary.is_canary(r["isin"])]
    if structural:
        raise QualityError(f"{path}: reserved canary prefix in source data: {structural[:5]}")
    counts_by_key = {}
    for r in rows:
        k = _source_key(r)
        counts_by_key[k] = counts_by_key.get(k, 0) + 1
    quarantined, clean = [], []
    for r in rows:
        i = r["isin"]
        o, h, l, c = r["open"], r["high"], r["low"], r["close"]
        if len(i) != 12 or not i[:2].isalpha() or not i.isalnum():
            reason, detail = "malformed_isin", f"malformed ISIN {i!r}"
        elif counts_by_key[_source_key(r)] > 1:
            reason, detail = "duplicate_source_observation", f"source identity {_source_key(r)!r} appears {counts_by_key[_source_key(r)]} times"
        elif min(o, h, l, c) <= 0 or l > min(o, c) or h < max(o, c):
            reason, detail = "ohlc_invalid", f"OHLC ordering violated (O {o} H {h} L {l} C {c})"
        elif r["volume"] < 0 or r["traded_value"] < 0:
            reason, detail = "negative_quantity", "negative volume or traded value"
        else:
            clean.append(r)
            continue
        quarantined.append(_quarantine_row("price_observation", day, r, reason, detail, sha, received_at))
    _enforce_quarantine_share(path, quarantined, len(rows), pol)

    warnings = []
    prior = [k for k in wh.partitions("price_observation") if k < day.isoformat()]
    if prior:
        n_prior = len(_latest(wh.read("price_observation", [prior[-1]])))
        # exact arithmetic: a threshold must not depend on float rounding (19/20 is exactly inside +-5%)
        ratio = fractions.Fraction(len(rows), n_prior)
        q = pol["quality"]
        kill = fractions.Fraction(str(q["row_count_kill_ratio"]))
        band = fractions.Fraction(str(q["row_count_warn_band"]))
        if ratio < kill:
            raise KillSwitch(f"{path}: {len(rows)} rows vs {n_prior} on {prior[-1]} ({float(ratio):.1%}); "
                             f"below {q['row_count_kill_ratio']:.0%} - nothing written")
        if abs(ratio - 1) > band:
            warnings.append(f"row count {len(rows)} vs {n_prior} on {prior[-1]} ({float(ratio):.1%})")

    meta = {"source_id": "nse_cm_bhavcopy", "source_format": fmt, "domain": "exchange_eod"}
    q_keys = {_source_key(q) for q in quarantined}
    new, tombstones, conflicts, counts = _version(wh, "price_observation", day, clean, PRICE_FIELDS, meta, mode,
                                                  received_at, published, now, pol, sha,
                                                  suppressed_absent_keys=q_keys)
    _commit(wh, "price_observation", "nse_cm_bhavcopy", day, new, conflicts, counts, sha, received_at, mode, len(rows),
            _crash_at, quarantine=quarantined, parse_event=_parsed_event(raw, fmt, day), tombstones=tombstones)
    return {"noop": False, "file_sha256": sha, "format": fmt, "trade_date": day, "warnings": warnings,
            "conflicts": conflicts, "quarantined": quarantined, **counts}


def ingest_delivery(wh, path, received_at, mode="backfill", published=None, now=None, policy=None, source_url=None,
                    retrieved_at=None, acquisition_method="manual_upload", _crash_at=None):
    with wh.writer():
        return _ingest_delivery(wh, path, received_at, mode, published, now, policy, source_url, retrieved_at,
                                acquisition_method, _crash_at)


def _ingest_delivery(wh, path, received_at, mode, published, now, policy, source_url, retrieved_at, acquisition_method, _crash_at):
    pol = policy or load_policy()
    sha, landed, raw = _land(wh, "nse_cm_delivery", path, received_at, source_url, retrieved_at, acquisition_method)
    try:
        fmt, day, rows = parsers.parse_mto(parsers.read_bytes(landed), os.path.basename(path))
    except Exception as exc:
        _rejected_parse_event(wh, raw, exc)
        raise
    if _already(wh, sha, day, "nse_cm_delivery"):
        return {"noop": True, "file_sha256": sha}
    if mode == "backfill":
        _check_backfill_allowed(day, received_at, pol)
    prices = _latest(wh.read("price_observation", [day.isoformat()])) if day.isoformat() in \
        wh.partitions("price_observation") else {}
    if not prices:
        raise QualityError(f"{path}: no bhavcopy ingested for {day}; delivery rows cannot be mapped to ISINs")
    by_sym = {(p["symbol"], p["series"]): p for p in prices.values()}
    quarantined, mapped, conflicts = [], [], []
    tol = pol["quality"]["delivery_volume_tolerance"]
    for r in rows:
        p = by_sym.get((r["symbol"], r["series"]))
        if p is None:
            quarantined.append(_quarantine_row("delivery_observation", day, r, "unmapped_symbol",
                                               f"{r['symbol']} {r['series']} not in the {day} bhavcopy", sha, received_at))
            continue
        if r["delivery_qty"] < 0 or r["delivery_qty"] > r["traded_qty_reported"]:
            quarantined.append(_quarantine_row("delivery_observation", day, {**r, "isin": p["isin"]}, "invalid_quantity",
                                               f"deliverable {r['delivery_qty']} outside 0..traded "
                                               f"{r['traded_qty_reported']}", sha, received_at))
            continue
        pct = r.get("delivery_pct_reported")
        if pct is not None and r["traded_qty_reported"] > 0:
            expected_pct = (decimal.Decimal(100) * decimal.Decimal(r["delivery_qty"]) / decimal.Decimal(r["traded_qty_reported"])).quantize(parsers.D4)
            pct_tol = parsers.money(str(pol["quality"].get("delivery_pct_tolerance_pp", 0.02)), "delivery pct tolerance", "policy")
            if abs(pct - expected_pct) > pct_tol:
                conflicts.append({"table_name": "delivery_observation", "source_instrument_id": p.get("source_instrument_id"),
                                  "isin": p["isin"], "series": r["series"], "trade_date": day,
                                  "kind": "delivery_pct_mismatch", "file_sha256": sha, "logged_at": received_at,
                                  "detail": f"delivery file reports {pct}% vs quantities imply {expected_pct}%"})
        vol = p["volume"]
        if vol and abs(r["traded_qty_reported"] - vol) / vol > tol:
            conflicts.append({"table_name": "delivery_observation", "isin": p["isin"], "trade_date": day,
                              "kind": "volume_mismatch", "file_sha256": sha, "logged_at": received_at,
                              "detail": f"delivery file traded {r['traded_qty_reported']} vs bhavcopy {vol}"})
        mapped.append({**r, "isin": p["isin"], "source_instrument_id": p.get("source_instrument_id")})
    _enforce_quarantine_share(path, quarantined, len(rows), pol)
    meta = {"source_id": "nse_cm_delivery", "source_format": fmt, "domain": "exchange_eod"}
    q_keys = {_source_key(q) for q in quarantined if q.get("isin")}
    new, tombstones, reissue, counts = _version(wh, "delivery_observation", day, mapped, DELIVERY_FIELDS, meta, mode,
                                                received_at, published, now, pol, sha,
                                                suppressed_absent_keys=q_keys)
    _commit(wh, "delivery_observation", "nse_cm_delivery", day, new, conflicts + reissue, counts, sha,
            received_at, mode, len(mapped), _crash_at, quarantine=quarantined, parse_event=_parsed_event(raw, fmt, day),
            tombstones=tombstones)
    return {"noop": False, "file_sha256": sha, "format": fmt, "trade_date": day, "conflicts": conflicts + reissue,
            "quarantined": quarantined, **counts}



def ingest_delivery_crosscheck(wh, path, received_at, mode="backfill", published=None, now=None, policy=None,
                               source_url=None, retrieved_at=None, acquisition_method="manual_upload", _crash_at=None):
    """Ingest `sec_bhavdata_full` delivery fields as independent evidence, never as the primary delivery feed."""
    with wh.writer():
        pol = policy or load_policy()
        source_id = "nse_cm_full_bhav_delivery"
        sha, landed, raw = _land(wh, source_id, path, received_at, source_url, retrieved_at, acquisition_method)
        try:
            fmt, day, rows = parsers.parse_full_bhav_delivery(parsers.read_bytes(landed), os.path.basename(path))
        except Exception as exc:
            _rejected_parse_event(wh, raw, exc)
            raise
        if _already(wh, sha, day, source_id):
            return {"noop": True, "file_sha256": sha}
        if mode == "backfill":
            _check_backfill_allowed(day, received_at, pol)
        prices = _latest(wh.read("price_observation", [day.isoformat()])) if day.isoformat() in wh.partitions("price_observation") else {}
        if not prices:
            raise QualityError(f"{path}: no bhavcopy ingested for {day}; full-bhav delivery rows cannot be mapped")
        by_sym = {(p["symbol"], p["series"]): p for p in prices.values()}
        quarantined, mapped, conflicts = [], [], []
        tol = pol["quality"]["delivery_volume_tolerance"]
        pct_tol = parsers.money(str(pol["quality"].get("delivery_pct_tolerance_pp", 0.02)), "delivery pct tolerance", "policy")
        for r in rows:
            p = by_sym.get((r["symbol"], r["series"]))
            if p is None:
                quarantined.append(_quarantine_row("delivery_crosscheck_observation", day, r, "unmapped_symbol",
                                                   f"{r['symbol']} {r['series']} not in the {day} bhavcopy", sha, received_at))
                continue
            if r["delivery_available"]:
                if r["delivery_qty"] < 0 or r["delivery_qty"] > r["traded_qty_reported"]:
                    quarantined.append(_quarantine_row("delivery_crosscheck_observation", day,
                                                       {**r, "isin": p["isin"]}, "invalid_quantity",
                                                       f"deliverable {r['delivery_qty']} outside 0..traded {r['traded_qty_reported']}",
                                                       sha, received_at))
                    continue
                if r["traded_qty_reported"] > 0 and r.get("delivery_pct_reported") is not None:
                    expected_pct = (decimal.Decimal(100) * decimal.Decimal(r["delivery_qty"]) / decimal.Decimal(r["traded_qty_reported"])).quantize(parsers.D4)
                    if abs(r["delivery_pct_reported"] - expected_pct) > pct_tol:
                        conflicts.append({"table_name": "delivery_crosscheck_observation",
                                          "source_instrument_id": p.get("source_instrument_id"), "isin": p["isin"],
                                          "series": r["series"], "trade_date": day, "kind": "delivery_pct_mismatch",
                                          "file_sha256": sha, "logged_at": received_at,
                                          "detail": f"full bhav reports {r['delivery_pct_reported']}% vs quantities imply {expected_pct}%"})
            vol = p["volume"]
            if vol and abs(r["traded_qty_reported"] - vol) / vol > tol:
                conflicts.append({"table_name": "delivery_crosscheck_observation",
                                  "source_instrument_id": p.get("source_instrument_id"), "isin": p["isin"],
                                  "series": r["series"], "trade_date": day, "kind": "volume_mismatch",
                                  "file_sha256": sha, "logged_at": received_at,
                                  "detail": f"full bhav traded {r['traded_qty_reported']} vs bhavcopy {vol}"})
            mapped.append({**r, "isin": p["isin"], "source_instrument_id": p.get("source_instrument_id")})
        _enforce_quarantine_share(path, quarantined, len(rows), pol)
        meta = {"source_id": source_id, "source_format": fmt, "domain": "exchange_eod"}
        q_keys = {_source_key(q) for q in quarantined if q.get("isin")}
        new, tombstones, reissue, counts = _version(wh, "delivery_crosscheck_observation", day, mapped,
                                                    CROSSCHECK_DELIVERY_FIELDS, meta, mode, received_at, published,
                                                    now, pol, sha, suppressed_absent_keys=q_keys)
        _commit(wh, "delivery_crosscheck_observation", source_id, day, new, conflicts + reissue, counts, sha,
                received_at, mode, len(mapped), _crash_at, quarantine=quarantined,
                parse_event=_parsed_event(raw, fmt, day), tombstones=tombstones)
        return {"noop": False, "file_sha256": sha, "format": fmt, "trade_date": day,
                "conflicts": conflicts + reissue, "quarantined": quarantined, **counts}


def capture_unparsed_reference(wh, source_id, path, received_at, source_url=None, retrieved_at=None,
                               acquisition_method="manual_upload"):
    """Durably capture a known-needed reference file before its semantics are implemented.

    This is intentionally *not* source coverage: it records only immutable receipt evidence and a parse-event
    status of `captured_unparsed`. It is used for sources such as the price-band list while Stage 0 is still
    validating historical layout/effective-date/tick-rounding semantics.
    """
    if source_id not in {"nse_cm_price_band"}:
        raise QualityError(f"source {source_id!r} is not approved for unparsed reference capture")
    with wh.writer():
        sha, _landed, raw = _land(wh, source_id, path, received_at, source_url, retrieved_at, acquisition_method)
        event = {"source_id": source_id, "file_sha256": sha, "received_at": received_at,
                 "parsed_at": dt.datetime.now(dt.timezone.utc), "status": "captured_unparsed",
                 "source_format": None, "trade_date": None, "parse_error": None}
        key = _receipt_key(received_at)
        if event not in wh.read("raw_parse_event", [key]):
            wh.append("raw_parse_event", key, [event])
        return {"file_sha256": sha, "source_id": source_id, "status": "captured_unparsed"}

def ingest_security_master(wh, path, received_at, mode="backfill", published=None, now=None, policy=None,
                           source_url=None, retrieved_at=None, acquisition_method="manual_upload",
                           effective_session=None, effective_session_basis="unresolved", _crash_at=None):
    """Ingest one immutable NSE CM MII security-master snapshot.

    master_file_date is source provenance; effective_session is a separate semantic assertion.  r5.8 never
    infers the latter from the filename.  Callers may supply an exchange-notice/validated effective session;
    otherwise the snapshot remains useful evidence but fails closed for historical eligibility decisions.
    """
    with wh.writer():
        pol = policy or load_policy()
        sha, landed, raw = _land(wh, "nse_cm_security_master", path, received_at, source_url, retrieved_at,
                                 acquisition_method)
        try:
            fmt, master_date, rows = parsers.parse_security_master(parsers.read_bytes(landed), os.path.basename(path))
        except Exception as exc:
            _rejected_parse_event(wh, raw, exc)
            raise
        if _already(wh, sha, master_date, "nse_cm_security_master"):
            return {"noop": True, "file_sha256": sha}
        if mode == "backfill":
            _check_backfill_allowed(master_date, received_at, pol)
        if effective_session is not None and not isinstance(effective_session, dt.date):
            raise QualityError("effective_session must be a date or None")
        if effective_session is None and effective_session_basis != "unresolved":
            raise QualityError("an unresolved effective_session must use effective_session_basis='unresolved'")
        if effective_session is not None and effective_session_basis not in {"exchange_notice", "validated_convention", "measured"}:
            raise QualityError("resolved effective_session_basis must be exchange_notice, validated_convention or measured")

        key = master_date.isoformat()
        existing = [r for r in wh.read("security_master_observation", [key])] if key in wh.partitions("security_master_observation") else []
        prev = {}
        for r in existing:
            sid = r["source_instrument_id"]
            if sid not in prev or r["version_no"] > prev[sid]["version_no"]:
                prev[sid] = r
        new = []
        changed = unchanged = 0
        for r in rows:
            p = prev.get(r["source_instrument_id"])
            enriched = {**r, "effective_session": effective_session,
                        "effective_session_basis": effective_session_basis}
            if p is not None and all(p.get(f) == enriched.get(f) for f in MASTER_FIELDS):
                unchanged += 1
                continue
            v = 1 if p is None else p["version_no"] + 1
            changed += p is not None
            av = _availability("nse_cm_security_master", mode, p is None, master_date, received_at,
                               published, now, pol)
            new.append({**enriched, "master_file_date": master_date, "version_no": v,
                        "source_id": "nse_cm_security_master", "source_format": fmt, "file_sha256": sha,
                        "received_at": received_at, "supersedes_version": None if p is None else p["version_no"],
                        "domain": "exchange_eod", **av})

        counts = {"rows_new": len(new) - changed, "rows_changed": changed, "rows_unchanged": unchanged}
        b = wh.batch()
        b.add("raw_parse_event", _receipt_key(received_at), [_parsed_event(raw, fmt, master_date)])
        b.add("security_master_observation", key, new)
        cov = [r for r in wh.read("source_coverage", [key]) if r["source_id"] == "nse_cm_security_master"]
        if not cov:
            avs = [r["usable_from"] for r in new]
            if not avs:
                avs = [r["usable_from"] for r in existing]
            b.add("source_coverage", key, [{
                "source_id": "nse_cm_security_master", "trade_date": master_date, "complete": True,
                "rows": len(rows), "file_sha256": sha, "usable_from": min(avs), "received_at": received_at,
                "domain": "exchange_eod"}])
        b.add("ingestion_log", key, [{"file_sha256": sha, "source_id": "nse_cm_security_master",
                                      "trade_date": master_date, "received_at": received_at,
                                      "mode": mode, **counts}])
        b.commit(_crash_at)
        return {"noop": False, "file_sha256": sha, "format": fmt, "master_file_date": master_date,
                "effective_session": effective_session, "effective_session_basis": effective_session_basis,
                **counts}
