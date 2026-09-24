"""M2 ingestion: raw NSE files -> versioned observations with honest availability (Document 02 s3, s6, s17).

Versioning. A row is keyed (isin, trade_date, version_no). Re-ingesting identical content writes nothing.
Changed content writes a new version that supersedes the latest; nothing is overwritten.

Availability. usable_from = greatest(effective_from, system_available_at).
  live      source_published_at = given (else received_at); system_available_at = processing time.
  backfill  the FIRST version of a row gets the policy's inferred publication time on its trade date,
            flagged availability_inferred. A LATER version is never inferred: we only know it existed
            when we received it, so system_available_at = received_at.

Every check runs before anything is written; a rejected file leaves the warehouse untouched.
Row-level defects (malformed or duplicate ISIN, impossible OHLC, invalid quantities, an unmapped delivery
symbol) quarantine the row instead of rejecting the day (r5.5, audit C5); the file is rejected only when the
quarantined share exceeds quality.max_quarantine_share, or on a structural fault (header, dates, canary prefix).
Backfill inference is refused for a file received on its own trade date or on/after live_capture_start
(r5.5, audit B3b): a replay must never see a file its live run did not have.
One file is one warehouse batch, written under one writer lock (review B2, B3): observations, conflicts,
coverage and the ingestion-log entry become visible together or not at all, and no second ingestion can
allocate a version between this one's read and its commit.
"""
import datetime as dt
import fractions
import hashlib
import os

from .. import canary
from ..source_policy import load as load_policy
from ..timeutil import IST, at_ist
from . import parsers

PRICE_FIELDS = ("series", "open", "high", "low", "close", "prev_close", "volume", "traded_value", "num_trades")
DELIVERY_FIELDS = ("series", "delivery_qty", "traded_qty_reported")


class QualityError(Exception):
    """File rejected; nothing written."""


class KillSwitch(QualityError):
    """Row count collapsed versus the prior session; nothing written or published."""


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _latest(rows):
    out = {}
    for r in rows:
        if canary.is_canary(r["isin"]):
            continue
        if r["isin"] not in out or r["version_no"] > out[r["isin"]]["version_no"]:
            out[r["isin"]] = r
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
    return dict(delivery_qty=0, traded_qty_reported=1)


def _version(wh, table, trade_date, parsed, fields, meta, mode, received_at, published, now, pol, sha):
    existing = wh.read(table, [trade_date.isoformat()])
    latest = _latest(existing)
    new, changed, unchanged = [], 0, 0
    for r in parsed:
        prev = latest.get(r["isin"])
        if prev is not None and all(prev[f] == r[f] for f in fields):
            unchanged += 1
            continue
        v = 1 if prev is None else prev["version_no"] + 1
        changed += prev is not None
        av = _availability(meta["source_id"], mode, prev is None, trade_date, received_at, published, now, pol)
        row = {**r, **meta, **av, "trade_date": trade_date, "version_no": v, "received_at": received_at,
               "supersedes_version": None if prev is None else prev["version_no"], "file_sha256": sha}
        if row["usable_from"] < row["source_published_at"]:
            raise QualityError(f"{r['isin']}: usable_from before source_published_at")
        new.append(row)
    seen = {r["isin"] for r in parsed}
    conflicts = [{"table_name": table, "isin": i, "trade_date": trade_date, "kind": "absent_in_reissue",
                  "detail": f"present at v{p['version_no']}, absent from file {sha[:12]}; prior version kept",
                  "file_sha256": sha, "logged_at": received_at}
                 for i, p in sorted(latest.items()) if i not in seen]
    if not existing and new:
        new = canary.sentinels(table, trade_date, "exchange_eod", _neutral(table)) + new
    return new, conflicts, dict(rows_new=len(new) - changed - (4 if not existing and new else 0),
                                rows_changed=changed, rows_unchanged=unchanged)


def _commit(wh, table, source_id, trade_date, new, conflicts, counts, sha, received_at, mode, n_rows, _crash_at=None,
            quarantine=()):
    """Everything one file produces, in ONE batch."""
    key = trade_date.isoformat()
    b = wh.batch()
    b.add(table, key, new)
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


def _already(wh, sha, day):
    """Only the trade date's own log partition is read (audit C6: r5.4 re-read the whole log for every file,
    so a multi-year backfill was quadratic)."""
    key = day.isoformat()
    if key not in wh.partitions("ingestion_log"):
        return False
    return any(r["file_sha256"] == sha for r in wh.read("ingestion_log", [key]))


def _quarantine_row(table, day, r, reason, detail, sha, received_at):
    return {"table_name": table, "trade_date": day, "isin": r.get("isin"), "symbol": r.get("symbol"),
            "series": r.get("series"), "reason": reason, "detail": detail, "file_sha256": sha,
            "logged_at": received_at}


def _enforce_quarantine_share(path, quarantined, total, pol):
    limit = fractions.Fraction(str(pol["quality"]["max_quarantine_share"]))
    if total and fractions.Fraction(len(quarantined), total) > limit:
        reasons = "; ".join(f"{q['symbol'] or q['isin']}: {q['detail']}" for q in quarantined[:10])
        raise QualityError(f"{path}: {len(quarantined)} of {total} row(s) failed row checks, above the "
                           f"{pol['quality']['max_quarantine_share']:.0%} quarantine limit - nothing written: {reasons}")


def ingest_bhavcopy(wh, path, received_at, mode="backfill", published=None, now=None, expect_date=None, policy=None, _crash_at=None):
    with wh.writer():
        return _ingest_bhavcopy(wh, path, received_at, mode, published, now, expect_date, policy, _crash_at)


def _ingest_bhavcopy(wh, path, received_at, mode, published, now, expect_date, policy, _crash_at):
    pol = policy or load_policy()
    sha = _sha(path)
    fmt, day, rows = parsers.parse_bhavcopy(parsers.read_bytes(path), os.path.basename(path))
    if _already(wh, sha, day):
        return {"noop": True, "file_sha256": sha}
    if expect_date and day != expect_date:
        raise QualityError(f"{path}: file is for {day}, expected {expect_date}")
    if mode == "backfill":
        _check_backfill_allowed(day, received_at, pol)

    # ---- checks (Document 02 s17), all before any write
    structural = [r["isin"] for r in rows if canary.is_canary(r["isin"])]
    if structural:
        raise QualityError(f"{path}: reserved canary prefix in source data: {structural[:5]}")
    counts_by_isin = {}
    for r in rows:
        counts_by_isin[r["isin"]] = counts_by_isin.get(r["isin"], 0) + 1
    quarantined, clean = [], []
    for r in rows:
        i = r["isin"]
        o, h, l, c = r["open"], r["high"], r["low"], r["close"]
        if len(i) != 12 or not i[:2].isalpha() or not i.isalnum():
            reason, detail = "malformed_isin", f"malformed ISIN {i!r}"
        elif counts_by_isin[i] > 1:
            reason, detail = "duplicate_isin", f"{i} appears {counts_by_isin[i]} times"
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
    new, conflicts, counts = _version(wh, "price_observation", day, clean, PRICE_FIELDS, meta, mode,
                                      received_at, published, now, pol, sha)
    q_isins = {q["isin"] for q in quarantined}
    conflicts = [c for c in conflicts if c["isin"] not in q_isins]   # quarantined, not absent
    _commit(wh, "price_observation", "nse_cm_bhavcopy", day, new, conflicts, counts, sha, received_at, mode, len(rows),
            _crash_at, quarantine=quarantined)
    return {"noop": False, "file_sha256": sha, "format": fmt, "trade_date": day, "warnings": warnings,
            "conflicts": conflicts, "quarantined": quarantined, **counts}


def ingest_delivery(wh, path, received_at, mode="backfill", published=None, now=None, policy=None, _crash_at=None):
    with wh.writer():
        return _ingest_delivery(wh, path, received_at, mode, published, now, policy, _crash_at)


def _ingest_delivery(wh, path, received_at, mode, published, now, policy, _crash_at):
    pol = policy or load_policy()
    sha = _sha(path)
    fmt, day, rows = parsers.parse_mto(parsers.read_bytes(path), os.path.basename(path))
    if _already(wh, sha, day):
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
        vol = p["volume"]
        if vol and abs(r["traded_qty_reported"] - vol) / vol > tol:
            conflicts.append({"table_name": "delivery_observation", "isin": p["isin"], "trade_date": day,
                              "kind": "volume_mismatch", "file_sha256": sha, "logged_at": received_at,
                              "detail": f"delivery file traded {r['traded_qty_reported']} vs bhavcopy {vol}"})
        mapped.append({**r, "isin": p["isin"]})
    _enforce_quarantine_share(path, quarantined, len(rows), pol)
    meta = {"source_id": "nse_cm_delivery", "source_format": fmt, "domain": "exchange_eod"}
    new, reissue, counts = _version(wh, "delivery_observation", day, mapped, DELIVERY_FIELDS, meta, mode,
                                    received_at, published, now, pol, sha)
    q_isins = {q["isin"] for q in quarantined if q["isin"]}
    reissue = [c for c in reissue if c["isin"] not in q_isins]
    _commit(wh, "delivery_observation", "nse_cm_delivery", day, new, conflicts + reissue, counts, sha,
            received_at, mode, len(mapped), _crash_at, quarantine=quarantined)
    return {"noop": False, "file_sha256": sha, "format": fmt, "trade_date": day, "conflicts": conflicts + reissue,
            "quarantined": quarantined, **counts}
