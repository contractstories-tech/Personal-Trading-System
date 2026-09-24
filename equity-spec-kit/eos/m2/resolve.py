"""Resolved price reads (Document 02 s6). Two contracts, because they answer different questions (review B8):

  history_known_as_of(E)          Everything known at evaluation date E's exchange_eod cutoff, for every
                                  trade date up to E. A correction received by E replaces the original
                                  print even for earlier bars. This is the exact input of ONE decision at E.
                                  (`price_raw_resolved` is its Document 02 name.)

  point_in_time_panel(start, end) Each trade date's bar as known at THAT date's own cutoff ("as first known").
                                  A bar whose FIRST version arrived after its own cutoff (a late publication)
                                  is kept, as that first version, carrying its real usable_from (r5.5, audit
                                  B3a: r5.4 dropped such bars permanently, although every later decision had
                                  them). The panel ignores corrections a later decision could have known.

  panel_as_of(panel, E)           The panel as one decision at E may use it: bars with trade_date <= E and
                                  usable_from <= E's cutoff; delivery values not yet available at E are masked.

A sequence of historical decisions is built either from history_known_as_of(E) for each E (exact), or from
panel_as_of(panel, E) (conservative). history_known_as_of(end) over a long range must NEVER be used for a
sequence: every earlier decision would see corrections that arrived after it.

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


def select_first_known(own_cutoff, horizon):
    """Panel selection for one trade date: the latest version usable at the bar's own cutoff; if none was, the
    earliest version usable by the panel's horizon (a late first publication), keeping its usable_from."""
    def sel(rows, _cutoff):
        at_own = select_latest_usable(rows, own_cutoff)
        have = {(r["isin"], r["trade_date"]) for r in at_own}
        late = {}
        for r in rows:
            k = (r["isin"], r["trade_date"])
            if k in have or r["usable_from"] > horizon:
                continue
            if k not in late or r["version_no"] < late[k]["version_no"]:
                late[k] = r
        return at_own + list(late.values())
    return sel


def _resolve(wh, table, keys, cutoff, snapshot, select, horizon=None):
    present = set(_keys(wh, table, snapshot))
    keys = [k for k in keys if k in present]
    rows = wh.read(table, keys, snapshot)
    _check_identity(table, rows)
    chosen = select(rows, cutoff)
    canary.check(chosen, {r["trade_date"] for r in rows if canary.is_canary(r["isin"])}, cutoff)
    guard(chosen, horizon or cutoff)
    return [r for r in chosen if not canary.is_canary(r["isin"])]


def _resolved_rows(wh, keys, cut, snapshot, select, isins, horizon=None):
    horizon = horizon or cut
    prices = _resolve(wh, "price_observation", keys, cut, snapshot, select, horizon)
    deliv = {(r["isin"], r["trade_date"]): r
             for r in _resolve(wh, "delivery_observation", keys, cut, snapshot, select, horizon)}
    cov_keys = [k for k in keys if k in set(_keys(wh, "source_coverage", snapshot))]
    cov_rows = guard([r for r in wh.read("source_coverage", cov_keys, snapshot) if r["usable_from"] <= horizon
                      and r["source_id"] == "nse_cm_delivery" and r["complete"]], horizon)
    covered = {}
    for r in cov_rows:
        covered[r["trade_date"]] = min(covered.get(r["trade_date"], r["usable_from"]), r["usable_from"])
    q_keys = [k for k in keys if k in set(_keys(wh, "row_quarantine", snapshot))]
    # a quarantine record only relabels a row that visible coverage would otherwise call absent
    quarantined = {(q["isin"], q["trade_date"]) for q in wh.read("row_quarantine", q_keys, snapshot)
                   if q["table_name"] == "delivery_observation" and q["isin"]}
    out = []
    for p in prices:
        if isins is not None and p["isin"] not in isins:
            continue
        d = deliv.get((p["isin"], p["trade_date"]))
        cov_at = covered.get(p["trade_date"])
        if d is not None:
            extra = dict(delivery_qty=d["delivery_qty"], delivery_state="known", delivery_missing_reason=None,
                         delivery_availability_inferred=d["availability_inferred"],
                         delivery_usable_from=d["usable_from"])
        else:
            if cov_at is None:
                reason = "no_source_coverage"
            elif (p["isin"], p["trade_date"]) in quarantined:
                reason = "quarantined"
            else:
                reason = "absent_in_covered_file"
            extra = dict(delivery_qty=None, delivery_state="missing", delivery_missing_reason=reason,
                         delivery_availability_inferred=None, delivery_usable_from=None)
        out.append({**p, **extra, "delivery_coverage_usable_from": cov_at, "resolved_at_cutoff": cut})
    return out


def history_known_as_of(wh, eval_date, start=None, isins=None, snapshot=None, registry=None,
                        select=select_latest_usable):
    cut = run_cutoffs(eval_date, registry)["exchange_eod"]
    keys = [k for k in _keys(wh, "price_observation", snapshot)
            if k <= eval_date.isoformat() and (start is None or k >= start.isoformat())]
    return sorted(_resolved_rows(wh, keys, cut, snapshot, select, isins), key=lambda r: (r["trade_date"], r["isin"]))


price_raw_resolved = history_known_as_of   # Document 02 name


def point_in_time_panel(wh, start, end, isins=None, snapshot=None, registry=None, select=None):
    """select: test hook only (planted read defects). The panel's horizon is the cutoff of `end`."""
    horizon = run_cutoffs(end, registry)["exchange_eod"]
    out = []
    for k in _keys(wh, "price_observation", snapshot):
        if start.isoformat() <= k <= end.isoformat():
            d = type(start).fromisoformat(k)
            own = run_cutoffs(d, registry)["exchange_eod"]
            sel = select or select_first_known(own, horizon)
            out += _resolved_rows(wh, [k], own, snapshot, sel, isins, horizon)
    return sorted(out, key=lambda r: (r["trade_date"], r["isin"]))


def panel_as_of(panel, decision_date, registry=None):
    """What one decision at `decision_date` may use from a panel (look-ahead-free, nothing dropped)."""
    cut = run_cutoffs(decision_date, registry)["exchange_eod"]
    out = []
    for r in panel:
        if r["trade_date"] > decision_date or r["usable_from"] > cut:
            continue
        r = dict(r)
        if r["delivery_state"] == "known" and r["delivery_usable_from"] > cut:
            r.update(delivery_qty=None, delivery_state="missing", delivery_missing_reason="not_yet_available",
                     delivery_availability_inferred=None, delivery_usable_from=None)
        elif r["delivery_missing_reason"] in ("absent_in_covered_file", "quarantined") \
                and r["delivery_coverage_usable_from"] > cut:
            r.update(delivery_missing_reason="no_source_coverage")
        out.append(r)
    return out


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
