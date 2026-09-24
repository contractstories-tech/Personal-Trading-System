"""M2 ingestion: raw NSE files -> versioned observations with honest availability (Document 02 s3, s6, s17).

Versioning. A row is keyed (isin, trade_date, version_no). Re-ingesting identical content writes nothing.
Changed content writes a new version that supersedes the latest; nothing is overwritten.

Availability. usable_from = greatest(effective_from, system_available_at).
  live      source_published_at = given (else received_at); system_available_at = processing time.
  backfill  the FIRST version of a row gets the policy's inferred publication time on its trade date,
            flagged availability_inferred. A LATER version is never inferred: we only know it existed
            when we received it, so system_available_at = received_at.

Every check runs before anything is written; a rejected file leaves the warehouse untouched.
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
from ..timeutil import at_ist
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


def _commit(wh, table, source_id, trade_date, new, conflicts, counts, sha, received_at, mode, n_rows, _crash_at=None):
    """Everything one file produces, in ONE batch."""
    key = trade_date.isoformat()
    b = wh.batch()
    b.add(table, key, new)
    b.add("data_conflict", key, conflicts)
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


def _already(wh, sha):
    return any(r["file_sha256"] == sha for r in wh.read("ingestion_log"))


def ingest_bhavcopy(wh, path, received_at, mode="backfill", published=None, now=None, expect_date=None, policy=None, _crash_at=None):
    with wh.writer():
        return _ingest_bhavcopy(wh, path, received_at, mode, published, now, expect_date, policy, _crash_at)


def _ingest_bhavcopy(wh, path, received_at, mode, published, now, expect_date, policy, _crash_at):
    pol = policy or load_policy()
    sha = _sha(path)
    if _already(wh, sha):
        return {"noop": True, "file_sha256": sha}
    fmt, day, rows = parsers.parse_bhavcopy(parsers.read_bytes(path), os.path.basename(path))
    if expect_date and day != expect_date:
        raise QualityError(f"{path}: file is for {day}, expected {expect_date}")

    # ---- checks (Document 02 s17), all before any write
    errs, seen = [], set()
    for r in rows:
        i = r["isin"]
        if len(i) != 12 or not i[:2].isalpha() or not i.isalnum():
            errs.append(f"{r['symbol']}: malformed ISIN {i!r}")
        if canary.is_canary(i):
            errs.append(f"{i}: reserved canary prefix in source data")
        if i in seen:
            errs.append(f"{i}: duplicate (isin, trade_date)")
        seen.add(i)
        o, h, l, c = r["open"], r["high"], r["low"], r["close"]
        if min(o, h, l, c) <= 0 or l > min(o, c) or h < max(o, c):
            errs.append(f"{i}: OHLC ordering violated (O {o} H {h} L {l} C {c})")
        if r["volume"] < 0 or r["traded_value"] < 0:
            errs.append(f"{i}: negative volume or traded value")
    if errs:
        raise QualityError(f"{path}: {len(errs)} problem(s): " + "; ".join(errs[:10]))

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
    new, conflicts, counts = _version(wh, "price_observation", day, rows, PRICE_FIELDS, meta, mode,
                                      received_at, published, now, pol, sha)
    _commit(wh, "price_observation", "nse_cm_bhavcopy", day, new, conflicts, counts, sha, received_at, mode, len(rows),
            _crash_at)
    return {"noop": False, "file_sha256": sha, "format": fmt, "trade_date": day, "warnings": warnings,
            "conflicts": conflicts, **counts}


def ingest_delivery(wh, path, received_at, mode="backfill", published=None, now=None, policy=None, _crash_at=None):
    with wh.writer():
        return _ingest_delivery(wh, path, received_at, mode, published, now, policy, _crash_at)


def _ingest_delivery(wh, path, received_at, mode, published, now, policy, _crash_at):
    pol = policy or load_policy()
    sha = _sha(path)
    if _already(wh, sha):
        return {"noop": True, "file_sha256": sha}
    fmt, day, rows = parsers.parse_mto(parsers.read_bytes(path), os.path.basename(path))
    prices = _latest(wh.read("price_observation", [day.isoformat()]))
    if not prices:
        raise QualityError(f"{path}: no bhavcopy ingested for {day}; delivery rows cannot be mapped to ISINs")
    by_sym = {(p["symbol"], p["series"]): p for p in prices.values()}
    errs, mapped, conflicts = [], [], []
    tol = pol["quality"]["delivery_volume_tolerance"]
    for r in rows:
        p = by_sym.get((r["symbol"], r["series"]))
        if p is None:
            errs.append(f"{r['symbol']} {r['series']}: not in the {day} bhavcopy")
            continue
        if r["delivery_qty"] < 0 or r["delivery_qty"] > r["traded_qty_reported"]:
            errs.append(f"{r['symbol']}: deliverable {r['delivery_qty']} outside 0..traded {r['traded_qty_reported']}")
        vol = p["volume"]
        if vol and abs(r["traded_qty_reported"] - vol) / vol > tol:
            conflicts.append({"table_name": "delivery_observation", "isin": p["isin"], "trade_date": day,
                              "kind": "volume_mismatch", "file_sha256": sha, "logged_at": received_at,
                              "detail": f"delivery file traded {r['traded_qty_reported']} vs bhavcopy {vol}"})
        mapped.append({**r, "isin": p["isin"]})
    if errs:
        raise QualityError(f"{path}: {len(errs)} problem(s): " + "; ".join(errs[:10]))
    meta = {"source_id": "nse_cm_delivery", "source_format": fmt, "domain": "exchange_eod"}
    new, reissue, counts = _version(wh, "delivery_observation", day, mapped, DELIVERY_FIELDS, meta, mode,
                                    received_at, published, now, pol, sha)
    _commit(wh, "delivery_observation", "nse_cm_delivery", day, new, conflicts + reissue, counts, sha,
            received_at, mode, len(mapped), _crash_at)
    return {"noop": False, "file_sha256": sha, "format": fmt, "trade_date": day, "conflicts": conflicts + reissue,
            **counts}
