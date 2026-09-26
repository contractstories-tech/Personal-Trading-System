"""Point-in-time resolution for exchange source observations and strategy-facing prices.

r5.8 distinguishes two layers:
  * source observations: every legitimate exchange observation (for example EQ and BL for one ISIN);
  * canonical strategy price: one regular-market observation per economic security/session, derived separately.

A later complete-file withdrawal is an explicit tombstone.  Security-master state is also point-in-time and
requires an explicit effective_session; an available-but-unresolved newer master version fails closed rather
than silently applying either the old or the new metadata.
"""
from .. import canary
from ..pit import guard
from ..store import IntegrityError
from ..timeutil import run_cutoffs


SERIES_PRIORITY = {"EQ": 0, "BE": 10, "BZ": 11, "SM": 20, "ST": 21, "SZ": 22}
NON_CANONICAL_SERIES = {"BL", "IQ", "RL"}


from .identity import observation_key as _source_key   # (ISIN, series) in every format (r5.10)


def _event_key(r):
    return (_source_key(r), r["trade_date"])


def select_latest_usable(rows, cutoff):
    best = {}
    for r in rows:
        if r["usable_from"] <= cutoff:
            k = _event_key(r)
            if k not in best or r["version_no"] > best[k]["version_no"]:
                best[k] = r
    return list(best.values())


def _check_identity(table, rows):
    seen = set()
    for r in rows:
        k = (_source_key(r), r["trade_date"], r["version_no"])
        if k in seen:
            raise IntegrityError(f"{table}: duplicate source identity {k} - two rows claim the same version")
        seen.add(k)


def _keys(wh, table, snapshot):
    if snapshot is None:
        return wh.partitions(table)
    return sorted({k.split("/", 1)[1] for k in snapshot["parts"] if k.startswith(table + "/")})


def select_first_known(own_cutoff, horizon):
    """Panel selection for one trade date, including withdrawal events."""
    def sel(rows, _cutoff):
        at_own = select_latest_usable(rows, own_cutoff)
        have = {_event_key(r) for r in at_own}
        late = {}
        for r in rows:
            k = _event_key(r)
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
    tomb_keys = [k for k in keys if k in set(_keys(wh, "observation_tombstone", snapshot))]
    tombs = [dict(r, _is_tombstone=True) for r in wh.read("observation_tombstone", tomb_keys, snapshot)
             if r["table_name"] == table]
    obs = [dict(r, _is_tombstone=False) for r in rows]
    events = obs + tombs
    _check_identity(table, events)
    chosen = select(events, cutoff)
    # The canary exists only in observation rows; tombstones are never generated for sentinels.
    canary.check([r for r in chosen if not r.get("_is_tombstone")],
                 {r["trade_date"] for r in rows if canary.is_canary(r["isin"])}, cutoff)
    guard(chosen, horizon or cutoff)
    return [{k: v for k, v in r.items() if k != "_is_tombstone"}
            for r in chosen if not r.get("_is_tombstone") and not canary.is_canary(r["isin"])]


def canonicalize_price_rows(rows):
    """Derive one strategy-facing regular-market price per ISIN/session without deleting source evidence.

    BL/IQ/RL are never canonical.  When more than one regular series exists, explicit NSE series precedence is
    used; an exact tie is an integrity failure rather than an arbitrary choice.  Security-master classification
    is a separate layer and may further exclude a row from an investable universe.
    """
    grouped = {}
    for r in rows:
        if r["series"] in NON_CANONICAL_SERIES:
            continue
        grouped.setdefault((r["isin"], r["trade_date"]), []).append(r)
    out = []
    for k, rs in grouped.items():
        ranked = sorted(rs, key=lambda r: (SERIES_PRIORITY.get(r["series"], 100), r["series"],
                                           str(r.get("source_instrument_id") or "")))
        if len(ranked) > 1:
            a, b = ranked[0], ranked[1]
            if SERIES_PRIORITY.get(a["series"], 100) == SERIES_PRIORITY.get(b["series"], 100):
                raise IntegrityError(f"price_observation: two canonical candidates for {k}: "
                                     f"{a['series']}/{a.get('source_instrument_id')} and "
                                     f"{b['series']}/{b.get('source_instrument_id')}")
        out.append(ranked[0])
    return out


def source_prices_known_as_of(wh, eval_date, start=None, isins=None, snapshot=None, registry=None,
                              select=select_latest_usable):
    """All legitimate source price observations known at eval_date's exchange cutoff."""
    cut = run_cutoffs(eval_date, registry)["exchange_eod"]
    keys = [k for k in _keys(wh, "price_observation", snapshot)
            if k <= eval_date.isoformat() and (start is None or k >= start.isoformat())]
    rows = _resolve(wh, "price_observation", keys, cut, snapshot, select)
    if isins is not None:
        rows = [r for r in rows if r["isin"] in isins]
    return sorted(rows, key=lambda r: (r["trade_date"], r["isin"], r["series"], str(r.get("source_instrument_id") or "")))


def _resolved_rows(wh, keys, cut, snapshot, select, isins, horizon=None):
    horizon = horizon or cut
    source_prices = _resolve(wh, "price_observation", keys, cut, snapshot, select, horizon)
    prices = canonicalize_price_rows(source_prices)
    deliv_rows = _resolve(wh, "delivery_observation", keys, cut, snapshot, select, horizon)
    deliv = {(_source_key(r), r["trade_date"]): r for r in deliv_rows}
    cov_keys = [k for k in keys if k in set(_keys(wh, "source_coverage", snapshot))]
    cov_rows = guard([r for r in wh.read("source_coverage", cov_keys, snapshot) if r["usable_from"] <= horizon
                      and r["source_id"] == "nse_cm_delivery" and r["complete"]], horizon)
    covered = {}
    for r in cov_rows:
        covered[r["trade_date"]] = min(covered.get(r["trade_date"], r["usable_from"]), r["usable_from"])
    q_keys = [k for k in keys if k in set(_keys(wh, "row_quarantine", snapshot))]
    quarantined = {(_source_key(q), q["trade_date"]) for q in wh.read("row_quarantine", q_keys, snapshot)
                   if q["table_name"] == "delivery_observation" and q["isin"]}
    out = []
    for p in prices:
        if isins is not None and p["isin"] not in isins:
            continue
        d = deliv.get((_source_key(p), p["trade_date"]))
        # Legacy MTO/Bhavcopy have no token, and match naturally on ISIN+series through _source_key.
        cov_at = covered.get(p["trade_date"])
        if d is not None:
            extra = dict(delivery_qty=d["delivery_qty"], delivery_state="known", delivery_missing_reason=None,
                         delivery_availability_inferred=d["availability_inferred"], delivery_usable_from=d["usable_from"])
        else:
            if cov_at is None:
                reason = "no_source_coverage"
            elif (_source_key(p), p["trade_date"]) in quarantined:
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


price_raw_resolved = history_known_as_of


def point_in_time_panel(wh, start, end, isins=None, snapshot=None, registry=None, select=None):
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
    n = len(rows)
    pi = sum(1 for r in rows if r["availability_inferred"])
    dk = [r for r in rows if r["delivery_state"] == "known"]
    di = sum(1 for r in dk if r["delivery_availability_inferred"])
    return {"rows": n, "price_inferred": pi, "price_inferred_share": (pi / n) if n else None,
            "delivery_known": len(dk), "delivery_inferred": di,
            "delivery_inferred_share": (di / len(dk)) if dk else None}


# ------------------------------------------------------------------ security-master PIT state / session reconciliation

def security_master_state_as_of(wh, session_date, cutoff=None, snapshot=None, registry=None):
    """Return {source_instrument_id: {state,row}} for the session.

    An available newer row with effective_session=None blocks use of an older row for that instrument: the
    platform knows the reference state changed but does not know when it became effective.  A known future
    effective row does not block the older state before its effective session.
    """
    cutoff = cutoff or run_cutoffs(session_date, registry)["exchange_eod"]
    keys = [k for k in _keys(wh, "security_master_observation", snapshot) if k <= session_date.isoformat()]
    rows = [r for r in wh.read("security_master_observation", keys, snapshot) if r["usable_from"] <= cutoff]
    guard(rows, cutoff)
    by_id = {}
    for r in rows:
        by_id.setdefault(r["source_instrument_id"], []).append(r)
    out = {}
    for sid, rs in by_id.items():
        rs.sort(key=lambda r: (r["master_file_date"], r["version_no"]))
        latest = rs[-1]
        if latest["effective_session"] is None:
            out[sid] = {"state": "master_state_unresolved", "row": latest}
            continue
        if latest["effective_session"] <= session_date:
            out[sid] = {"state": "resolved", "row": latest}
            continue
        prior = [r for r in rs[:-1] if r["effective_session"] is not None and r["effective_session"] <= session_date]
        out[sid] = {"state": "resolved", "row": prior[-1]} if prior else {"state": "master_state_unresolved", "row": latest}
    return out


def resolve_session_states(wh, session_date, snapshot=None, registry=None):
    """Resolve traded/no-trade/unresolved states for source instruments on one session.

    `no_trade` is asserted only when (a) a resolved effective master says a company-equity instrument is
    normal-market eligible, (b) the final bhavcopy has complete visible coverage, and (c) that source instrument
    is absent and not quarantined.  No synthetic zero OHLC row is ever created.
    """
    cut = run_cutoffs(session_date, registry)["exchange_eod"]
    key = session_date.isoformat()
    source = source_prices_known_as_of(wh, session_date, start=session_date, snapshot=snapshot, registry=registry)
    source_by_id = {str(r.get("source_instrument_id")): r for r in source if r.get("source_instrument_id") is not None}
    canonical = {str(r.get("source_instrument_id")): r for r in canonicalize_price_rows(source)
                 if r.get("source_instrument_id") is not None}
    masters = security_master_state_as_of(wh, session_date, cut, snapshot, registry)
    cov = [r for r in wh.read("source_coverage", [key], snapshot)
           if r["source_id"] == "nse_cm_bhavcopy" and r["complete"] and r["usable_from"] <= cut] \
          if key in set(_keys(wh, "source_coverage", snapshot)) else []
    coverage_complete = bool(cov)
    qrows = wh.read("row_quarantine", [key], snapshot) if key in set(_keys(wh, "row_quarantine", snapshot)) else []
    qids = {str(q["source_instrument_id"]) for q in qrows
            if q["table_name"] == "price_observation" and q.get("source_instrument_id") is not None}

    out = []
    ids = set(masters) | set(source_by_id) | qids
    for sid in sorted(ids):
        m = masters.get(sid)
        src = source_by_id.get(sid)
        can = canonical.get(sid)
        if sid in qids:
            trade_state = "quarantined"
        elif src is not None:
            trade_state = "traded"
        elif not coverage_complete:
            trade_state = "source_not_available"
        elif m is None or m["state"] != "resolved":
            trade_state = "master_state_unresolved"
        else:
            mr = m["row"]
            if mr["security_class"] == "unresolved" or mr["market_eligible"] is None:
                trade_state = "master_state_unresolved"
            elif mr["security_class"] == "company_equity" and mr["market_eligible"] is True:
                trade_state = "no_trade"
            else:
                trade_state = "not_in_target_universe"
        mr = m["row"] if m else None
        mismatch = None
        if src is not None and mr is not None and m["state"] == "resolved":
            diffs = [f for f in ("isin", "symbol", "series") if src.get(f) != mr.get(f)]
            mismatch = diffs or None
        out.append({
            "source_instrument_id": sid,
            "trade_state": trade_state,
            "source_observation": src,
            "canonical_price": can,
            "master_state": None if m is None else m["state"],
            "master_row": mr,
            "metadata_mismatch_fields": mismatch,
        })
    return out
