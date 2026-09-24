"""Resolved price reads (Document 02 s6). Two contracts, because they answer different questions (review B8):

  history_known_as_of(E)          Everything known at evaluation date E's exchange_eod cutoff, for every
                                  trade date up to E. A correction received by E replaces the original
                                  print even for earlier bars. This is the exact input of ONE decision at E.
                                  (`price_raw_resolved` is its Document 02 name.)

  point_in_time_panel(start, end) Each trade date's bar as known at THAT date's own cutoff ("as first known").
                                  Look-ahead-free for any sequence of decisions, and fast to build, but it
                                  ignores corrections a later decision could legitimately have known.

A sequence of historical decisions is built either from history_known_as_of(E) for each E (exact), or from
the panel (conservative). history_known_as_of(end) over a long range must NEVER be used for a sequence:
every earlier decision would see corrections that arrived after it.

Every read passes the duplicate-identity check, the canary and the look-ahead guard; sentinels are removed
only after all three.
"""
from .. import canary
from ..pit import guard
from ..store import IntegrityError
from ..timeutil import run_cutoffs


def select_latest_usable(rows, cutoff):
    best = {}
    for r in rows:
        if r["usable_from"] <= cutoff:
            k = (r["isin"], r["trade_date"])
            if k not in best or r["version_no"] > best[k]["version_no"]:
                best[k] = r
    return list(best.values())


def _check_identity(table, rows):
    seen = set()
    for r in rows:
        k = (r["isin"], r["trade_date"], r["version_no"])
        if k in seen:
            raise IntegrityError(f"{table}: duplicate identity {k} - two rows claim the same version")
        seen.add(k)


def _keys(wh, table, snapshot):
    if snapshot is None:
        return wh.partitions(table)
    return sorted({k.split("/", 1)[1] for k in snapshot["parts"] if k.startswith(table + "/")})


def _resolve(wh, table, keys, cutoff, snapshot, select):
    present = set(_keys(wh, table, snapshot))
    keys = [k for k in keys if k in present]
    rows = wh.read(table, keys, snapshot)
    _check_identity(table, rows)
    chosen = select(rows, cutoff)
    canary.check(chosen, {r["trade_date"] for r in rows if canary.is_canary(r["isin"])}, cutoff)
    guard(chosen, cutoff)
    return [r for r in chosen if not canary.is_canary(r["isin"])]


def _resolved_rows(wh, keys, cut, snapshot, select, isins):
    prices = _resolve(wh, "price_observation", keys, cut, snapshot, select)
    deliv = {(r["isin"], r["trade_date"]): r for r in _resolve(wh, "delivery_observation", keys, cut, snapshot, select)}
    cov_keys = [k for k in keys if k in set(_keys(wh, "source_coverage", snapshot))]
    cov_rows = wh.read("source_coverage", cov_keys, snapshot)
    covered = {r["trade_date"] for r in guard([r for r in cov_rows if r["usable_from"] <= cut
                                              and r["source_id"] == "nse_cm_delivery" and r["complete"]], cut)}
    out = []
    for p in prices:
        if isins is not None and p["isin"] not in isins:
            continue
        d = deliv.get((p["isin"], p["trade_date"]))
        if d is not None:
            extra = dict(delivery_qty=d["delivery_qty"], delivery_state="known", delivery_missing_reason=None,
                         delivery_availability_inferred=d["availability_inferred"])
        else:
            reason = "absent_in_covered_file" if p["trade_date"] in covered else "no_source_coverage"
            extra = dict(delivery_qty=None, delivery_state="missing", delivery_missing_reason=reason,
                         delivery_availability_inferred=None)
        out.append({**p, **extra, "resolved_at_cutoff": cut})
    return out


def history_known_as_of(wh, eval_date, start=None, isins=None, snapshot=None, registry=None,
                        select=select_latest_usable):
    cut = run_cutoffs(eval_date, registry)["exchange_eod"]
    keys = [k for k in _keys(wh, "price_observation", snapshot)
            if k <= eval_date.isoformat() and (start is None or k >= start.isoformat())]
    return sorted(_resolved_rows(wh, keys, cut, snapshot, select, isins), key=lambda r: (r["trade_date"], r["isin"]))


price_raw_resolved = history_known_as_of   # Document 02 name


def point_in_time_panel(wh, start, end, isins=None, snapshot=None, registry=None, select=select_latest_usable):
    out = []
    for k in _keys(wh, "price_observation", snapshot):
        if start.isoformat() <= k <= end.isoformat():
            d = type(start).fromisoformat(k)
            out += _resolved_rows(wh, [k], run_cutoffs(d, registry)["exchange_eod"], snapshot, select, isins)
    return sorted(out, key=lambda r: (r["trade_date"], r["isin"]))


def availability_profile(rows):
    """How much of a resolved set rests on inferred rather than observed availability (review B9).
    Validation reports carry this so results can be read against the timing assumption behind them."""
    n = len(rows)
    pi = sum(1 for r in rows if r["availability_inferred"])
    dk = [r for r in rows if r["delivery_state"] == "known"]
    di = sum(1 for r in dk if r["delivery_availability_inferred"])
    return {"rows": n, "price_inferred": pi, "price_inferred_share": (pi / n) if n else None,
            "delivery_known": len(dk), "delivery_inferred": di,
            "delivery_inferred_share": (di / len(dk)) if dk else None}
