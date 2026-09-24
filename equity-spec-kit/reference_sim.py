#!/usr/bin/env python3
"""Reference implementations of Document 04's simulation, cost, tax and feature semantics.

These are deliberately small and plain. They exist to define behaviour executably: the
golden fixtures in golden/*.yaml carry hand-computed answers, and any production engine
(M5, M6, M14) must reproduce the same answers on the same fixtures.
"""
import bisect, datetime as dt, math
import yaml

UNKNOWN = None


class LookAheadError(Exception):
    """Raised - never silently skipped - when a row not yet usable is read."""


# ------------------------------------------------------------------ fills (Doc 04 s3)
def fill_buy_limit(limit, open_px, upper_band):
    """Pre-open buy limit. No fill if the open prints AT the upper band (no sellers can be
    assumed); otherwise fills at the open if open <= limit. Returns fill price or None."""
    if upper_band is not None and open_px >= upper_band:
        return None
    return open_px if open_px <= limit else None


def fill_sell_on_open(sessions, per_session_haircut=0.01, max_haircut=0.05, missing_band_haircut=0.02):
    """Market-on-open exit across successive sessions.
    sessions: list of {open, lower_band (None if band file missing)}.
    An open AT the lower band means locked: no fill that session. The first unlocked open fills,
    with a haircut of per_session_haircut per locked session (capped). A missing band file fills at the open with
    missing_band_haircut (2%: band data is most likely missing exactly when a stock was locked;
    Document 04 also excludes uncovered periods from evidence). Returns (fill_price, sessions_delayed) or (None, n)."""
    delayed = 0
    for s in sessions:
        lb = s.get("lower_band")
        if lb is None:
            h = missing_band_haircut + min(per_session_haircut * delayed, max_haircut)
            return round(s["open"] * (1 - h), 4), delayed
        if s["open"] <= lb:
            delayed += 1
            continue
        h = min(per_session_haircut * delayed, max_haircut)
        return round(s["open"] * (1 - h), 4), delayed
    return None, delayed


# ------------------------------------------------------------------ impact (Doc 04 s5)
def impact_cost(value_cr, adv_cr, k=0.02):
    """impact_model_v1: half-spread proxy by liquidity tier + k * sqrt(participation).
    k = 0.02 corresponds to a ~2% daily volatility with a unit square-root coefficient."""
    if adv_cr <= 0:
        return math.inf
    half_spread = 0.0005 if adv_cr >= 100 else 0.0010 if adv_cr >= 25 else 0.0020
    return half_spread + k * math.sqrt(value_cr / adv_cr)


# ------------------------------------------------------------------ costs (Doc 04 s4)
def _rate(entries, date, key):
    d = dt.date.fromisoformat(str(date))
    for e in entries:
        lo = dt.date.fromisoformat(str(e["from"]))
        hi = dt.date.fromisoformat(str(e["to"])) if e.get("to") else dt.date.max
        if lo <= d <= hi:
            return e[key]
    raise KeyError(f"no schedule entry for {date}")


def trade_costs(side, value, date, schedule, profile="flat_20"):
    c, p = schedule["components"], schedule["broker_profiles"][profile]
    r2 = lambda x: round(x + 1e-12, 2)
    out = {"brokerage": r2(p["brokerage_per_order"]),
           "stt": r2(value * _rate(c["stt"], date, side)),
           "stamp_duty": r2(value * _rate(c["stamp_duty"], date, side)),
           "exchange_txn_nse": r2(value * _rate(c["exchange_txn_nse"], date, "rate")),
           "sebi_turnover_fee": r2(value * _rate(c["sebi_turnover_fee"], date, "rate"))}
    gst_rate = _rate(c["gst"], date, "rate")
    out["gst"] = r2(gst_rate * (out["brokerage"] + out["exchange_txn_nse"] + out["sebi_turnover_fee"]))
    if side == "sell":
        dp = p["dp_charge_per_sell_scrip_day"]
        out["dp_charge"] = r2(dp + gst_rate * dp)
    out["total"] = r2(sum(out.values()))
    return out


# ------------------------------------------------------------------ tax view (Doc 04 s6)
def _fy(d):
    return d.year if d.month >= 4 else d.year - 1


def _regime(schedule, d):
    for r in schedule["regimes"]:
        lo = dt.date.fromisoformat(str(r["from"]))
        hi = dt.date.fromisoformat(str(r["to"])) if r.get("to") else dt.date.max
        if lo <= d <= hi:
            return r
    raise KeyError(d)


def is_long_term(buy, sell):
    b, s = dt.date.fromisoformat(str(buy)), dt.date.fromisoformat(str(sell))
    try:
        anniv = b.replace(year=b.year + 1)
    except ValueError:  # 29 Feb
        anniv = b.replace(year=b.year + 1, day=28)
    return s > anniv


def tax_view(disposals, schedule, fy_start_year):
    """disposals: [{buy_date, sell_date, qty, cost_per_share, sale_per_share, fmv_2018 (optional)}]
    for sales within FY fy_start_year. Returns gains and tax before cess, and after cess."""
    st, lt, rates = 0.0, 0.0, {}
    for x in disposals:
        sd = dt.date.fromisoformat(str(x["sell_date"]))
        assert _fy(sd) == fy_start_year
        reg = _regime(schedule, sd)
        cost = x["cost_per_share"]
        if x.get("fmv_2018") is not None and dt.date.fromisoformat(str(x["buy_date"])) < dt.date(2018, 2, 1):
            cost = max(cost, min(x["fmv_2018"], x["sale_per_share"]))
        g = (x["sale_per_share"] - cost) * x["qty"]
        if is_long_term(x["buy_date"], x["sell_date"]):
            lt += g
        else:
            st += g
        rates = reg
    # set-off: short-term loss against short-term gain then long-term gain; long-term loss only against long-term
    if st < 0:
        lt += st
        st = 0.0
    st_tax = max(st, 0) * rates["stcg_rate"]
    exempt = rates.get("ltcg_exemption_per_fy") or 0
    taxable_lt = max(lt - exempt, 0) if rates["ltcg_rate"] > 0 else 0.0
    lt_tax = taxable_lt * rates["ltcg_rate"]
    tax = st_tax + lt_tax
    cess = schedule["view_parameters"]["cess"]
    return {"stcg": round(st, 2), "ltcg": round(lt, 2), "taxable_ltcg": round(taxable_lt, 2),
            "tax_before_cess": round(tax, 2), "tax_with_cess": round(tax * (1 + cess), 2)}


# ------------------------------------------------------------------ stop state machine (Doc 01 s11)
def run_stop(entry_fill, atr_at_entry, sessions, mult=2.5):
    """sessions: [{close, atr_pct}] STARTING WITH THE FILL SESSION - the position exists at that
    close, so the stop is tested there too. Test-then-update; strict-greater peak rule; ATR frozen
    at the peak. Returns per-session stop tested, and the exit session index or None."""
    stop = entry_fill * (1 - mult * atr_at_entry)
    peak, atr_peak = entry_fill, atr_at_entry
    tested = []
    for i, s in enumerate(sessions):
        tested.append(round(stop, 4))
        if s["close"] < stop:                                  # 1. test
            return {"stops_tested": tested, "exit_session": i}
        if s["close"] > peak:                                  # 2. strict new high
            peak, atr_peak = s["close"], s["atr_pct"]
        stop = max(stop, peak * (1 - mult * atr_peak))         # 3. update
    return {"stops_tested": tested, "exit_session": None}


# ------------------------------------------------------------------ tranches (card ltqv_v1)
def lt_tranches(target_value, entry_ref, weights, t2, t3):
    """t2/t3: {revised_target_value, prior_close, attempts: [recheck_pass bool]}.
    Returns quantities filled per tranche and the final earmark."""
    target_qty = math.floor(target_value / entry_ref)
    q1 = math.floor(weights[0] * target_qty)
    earmark, out = q1, [q1]
    for i, t in enumerate((t2, t3), start=2):
        if t is None:
            out.append(0); continue
        if not any(t["attempts"]):
            out.append(0)
            return {"quantities": out + [0] * (3 - len(out)), "earmark": earmark, "cancelled_after": i}
        rtq = math.floor(t["revised_target_value"] / t["prior_close"])
        if i == 2:
            q = max(0, min(math.floor(weights[1] * rtq), rtq - earmark))
        else:
            q = max(0, rtq - earmark)
        earmark += q
        out.append(q)
    return {"quantities": out, "earmark": earmark, "cancelled_after": None}


# ------------------------------------------------------------------ corporate actions (Doc 02 s5)
def split_bonus(qty, price_state, f, p_cum):
    """Returns new whole quantity, price state x f, and cash in lieu for the fraction,
    valued at the post-action theoretical price p_cum * f."""
    new_qty_exact = qty / f
    whole = math.floor(new_qty_exact + 1e-9)
    frac = new_qty_exact - whole
    return {"qty": whole, "price_state": {k: round(v * f, 4) for k, v in price_state.items()},
            "cash_in_lieu": round(frac * p_cum * f, 2)}


def demerger(parent_qty, p_cum, p_discovered, ratio):
    """ratio = resulting-entity shares received PER PARENT SHARE (1-for-2 -> 0.5; 3-for-1 -> 3.0).
    Value detached per parent share is P_cum - P_discovered, whatever the ratio; the implied price of one
    resulting share is that value / ratio. Whole shares become the stub; a fractional entitlement is cash
    in lieu at the implied price. Total = parent_qty x (P_cum - P_discovered), always (review B1)."""
    implied = (p_cum - p_discovered) / ratio
    entitled = parent_qty * ratio
    whole = math.floor(entitled + 1e-9)
    return {"f": round(p_discovered / p_cum, 6), "parent_qty": parent_qty, "stub_qty": whole,
            "stub_value": round(whole * implied, 2), "stub_implied_per_share": round(implied, 4),
            "cash_in_lieu": round((entitled - whole) * implied, 2)}


def rights_value(held, a, b, S, p_cum, re_listed_close=None):
    terp = (b * p_cum + a * S) / (a + b)
    f = terp / p_cum if S < p_cum else 1.0
    ent = held * a / b
    per = re_listed_close if re_listed_close is not None else max(0.0, terp - S)
    return {"terp": round(terp, 4), "f": round(f, 6), "entitlements": ent, "value": round(ent * per, 2)}


# ------------------------------------------------------------------ features and scoring
def persist(values, n):
    last = values[-n:]
    if len(last) < n or any(v is UNKNOWN for v in last):
        return UNKNOWN
    return all(last)


def quantile_linear(sorted_vals, q):
    pos = (len(sorted_vals) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def zscores(values, direction="higher_better", min_n=30):
    known = [v for v in values if v is not UNKNOWN]
    if len(known) < min_n:
        return [UNKNOWN] * len(values)
    s = sorted(known)
    lo, hi = quantile_linear(s, 0.01), quantile_linear(s, 0.99)
    clip = lambda v: min(max(v, lo), hi)
    c = [clip(v) for v in known]
    mean = sum(c) / len(c)
    sd = math.sqrt(sum((v - mean) ** 2 for v in c) / len(c))
    if sd == 0:
        return [UNKNOWN] * len(values)
    sign = -1 if direction == "lower_better" else 1
    return [UNKNOWN if v is UNKNOWN else sign * (clip(v) - mean) / sd for v in values]


def roce(ebit, equity, borrowings, leases, cash, total_assets, prior_ce):
    if equity <= 0:
        return {"state": "out_of_domain", "outcome": "fail"}
    ce = equity + borrowings + leases - cash
    if ce <= 0.05 * total_assets:
        return {"state": "known", "value": 1.0, "cash_rich_capped": True}
    return {"state": "known", "value": round(ebit / ((ce + prior_ce) / 2), 6), "cash_rich_capped": False}


def cfo_pat(sum_cfo, sum_pat):
    if sum_pat <= 0:
        return {"state": "out_of_domain", "outcome": "fail"}
    return {"state": "known", "value": round(sum_cfo / sum_pat, 6)}


def rank_order(rows, tol=1e-9):
    """rows: [{isin, score, market_cap}]. Scores within tol are ties -> higher market cap -> ISIN."""
    rows = sorted(rows, key=lambda r: r["isin"])
    rows = sorted(rows, key=lambda r: -r["market_cap"])
    out = []
    for r in sorted(rows, key=lambda r: -r["score"]):
        out.append(r)
    # stable merge of near-ties: re-sort adjacent groups within tolerance
    i = 0
    while i < len(out):
        j = i
        while j + 1 < len(out) and abs(out[j + 1]["score"] - out[i]["score"]) <= tol:
            j += 1
        out[i:j + 1] = sorted(out[i:j + 1], key=lambda r: (-r["market_cap"], r["isin"]))
        i = j + 1
    return [r["isin"] for r in out]


# ------------------------------------------------------------------ point-in-time read (Doc 01 s14)
def asof(rows, isin, basis, cutoff):
    """Latest row of the requested basis whose usable_from <= cutoff. The basis filter is applied
    BEFORE choosing the latest row."""
    cands = [r for r in rows if r["isin"] == isin and r["basis"] == basis and r["usable_from"] <= cutoff]
    return max(cands, key=lambda r: r["usable_from"]) if cands else None


def read_checked(row, cutoff):
    if row["usable_from"] > cutoff:
        raise LookAheadError(f"row usable_from {row['usable_from']} after cutoff {cutoff}")
    return row


def in_blackout(post_action_quarters_filed, required=4):
    return post_action_quarters_filed < required


# ================================================================== r5.2 additions
# ------------------------------------------------------------------ two cutoff domains (Doc 02 s3)
def usable(row, cutoffs):
    """A row is usable when its usable_from is at or before the cutoff OF ITS OWN DOMAIN.
    cutoffs: {'disclosure': ts, 'exchange_eod': ts}. One scalar cutoff cannot express the policy:
    a 21:00 filing must be excluded from the same run that uses a 22:30 bhavcopy."""
    return row["usable_from"] <= cutoffs[row["domain"]]


def asof_domain(rows, isin, domain, cutoffs):
    c = [r for r in rows if r["isin"] == isin and r["domain"] == domain and usable(r, cutoffs)]
    return max(c, key=lambda r: r["usable_from"]) if c else None


def asof_with_basis_fallback(rows, isin, cutoff, company_files_consolidated):
    """Consolidated is used when the company files it at all; standalone is a fallback only for
    companies that file no consolidated statements - never a per-date substitution."""
    basis = "consolidated" if company_files_consolidated else "standalone"
    return asof(rows, isin, basis, cutoff)


# ------------------------------------------------------------------ sizing bound (r5.2)
def bounded_qty(target_value, reference_price, hard_cap_value, limit_price):
    """Quantity from the reference price (unbiased), but never more than the hard cap allows at
    the worst permitted fill - so an allowed higher fill cannot breach the cap."""
    return min(math.floor(target_value / reference_price), math.floor(hard_cap_value / limit_price))


# ------------------------------------------------------------------ allocator (Doc 01 s9)
def security_target(claims):
    """The security's target is the LARGEST live claim target, never the sum: two strategies
    agreeing must not mechanically double exposure."""
    live = [c for c in claims if c.get("state", "live") == "live"]
    return max((c["target_value"] for c in live), default=0.0)


def allocate_slots(candidates, max_open_positions, existing_isins):
    """Deterministic, non-comparative priority: existing holdings, then earliest signal,
    then larger market cap, then ISIN. No cross-strategy score is ever invented."""
    ranked = sorted(candidates, key=lambda c: (0 if c["isin"] in existing_isins else 1,
                                               c["signal_ts"], -c["market_cap"], c["isin"]))
    taken = [c["isin"] for c in ranked[:max_open_positions]]
    return {"actionable": taken,
            "valid_but_not_currently_actionable": [c["isin"] for c in ranked[max_open_positions:]]}


# ------------------------------------------------------------------ dividend cash timing (Doc 04 s3)
def dividend_cash(amount, ex_date, pay_date, as_of_date):
    """Return is accrued on the ex-date; cash is spendable only from the payment date."""
    d = dt.date.fromisoformat(str(as_of_date))
    return {"accrued": amount if d >= dt.date.fromisoformat(str(ex_date)) else 0.0,
            "spendable": amount if d >= dt.date.fromisoformat(str(pay_date)) else 0.0}


# ------------------------------------------------------------------ tax across years (Doc 04 s6)
def tax_year(disposals, schedule):
    """Gains bucketed BY THE REGIME IN FORCE ON EACH SALE DATE, so a straddle year is correct."""
    buckets = {}
    for x in disposals:
        sd = dt.date.fromisoformat(str(x["sell_date"]))
        reg = _regime(schedule, sd)
        cost = x["cost_per_share"]
        if x.get("fmv_2018") is not None and dt.date.fromisoformat(str(x["buy_date"])) < dt.date(2018, 2, 1):
            cost = max(cost, min(x["fmv_2018"], x["sale_per_share"]))
        g = (x["sale_per_share"] - cost) * x["qty"]
        key = (reg["stcg_rate"], reg["ltcg_rate"], reg.get("ltcg_exemption_per_fy") or 0)
        b = buckets.setdefault(key, {"st": 0.0, "lt": 0.0})
        b["lt" if is_long_term(x["buy_date"], x["sell_date"]) else "st"] += g
    return buckets


def tax_multi_year(years, schedule, carry_in=None):
    """years: [{fy, disposals}] in order. Per year: current-year short-term loss against long-term gain;
    then brought-forward losses, oldest first - short-term vintages against short-term then long-term gains,
    long-term vintages against long-term gains only; then the FY exemption on the NET long-term gain; then
    each regime bucket taxed at its own rate on its pro-rata share.
    Unabsorbed losses carry forward BY VINTAGE and KIND, and lapse after carry_forward_years (review H7).
    carry_in: a list of vintages [{fy, kind: st|lt, amount (negative)}]."""
    return _tax_multi_year(years, schedule, carry_in)


def _tax_multi_year(years, schedule, carry_in=None, _expire=True, _st_carry_as_lt=False):
    life = schedule["set_off"]["carry_forward_years"]
    vint = [dict(v) for v in (carry_in or [])]
    out = []
    for y in years:
        fy = y["fy"]
        if _expire:
            vint = [v for v in vint if fy <= v["fy"] + life]       # usable in FY v+1 .. v+life
        buckets = tax_year(y["disposals"], schedule)
        st = sum(b["st"] for b in buckets.values())
        lt = sum(b["lt"] for b in buckets.values())
        if st < 0 < lt:                                            # current-year ST loss against LT gain
            use = min(-st, lt)
            st, lt = st + use, lt - use
        for v in sorted(vint, key=lambda v: v["fy"]):               # brought-forward, oldest first
            heads = ("st", "lt") if v["kind"] == "st" else ("lt",)
            for h in heads:
                gain = st if h == "st" else lt
                if gain > 0 and v["amount"] < 0:
                    use = min(-v["amount"], gain)
                    v["amount"] += use
                    if h == "st":
                        st -= use
                    else:
                        lt -= use
        vint = [v for v in vint if v["amount"] < 0]
        if st < 0:
            vint.append({"fy": fy, "kind": "lt" if _st_carry_as_lt else "st", "amount": st})
        if lt < 0:
            vint.append({"fy": fy, "kind": "lt", "amount": lt})
        net_st, net_lt = max(st, 0.0), max(lt, 0.0)
        # the FY exemption is the one in force at FY end (a straddle year uses the later regime)
        fy_end = dt.date(fy + 1, 3, 31)
        exemption = _regime(schedule, fy_end).get("ltcg_exemption_per_fy") or 0
        taxable_lt = max(net_lt - exemption, 0.0)
        pos_st = {k: max(b["st"], 0) for k, b in buckets.items()}
        pos_lt = {k: max(b["lt"], 0) for k, b in buckets.items()}
        tot_st, tot_lt = sum(pos_st.values()), sum(pos_lt.values())
        tax = 0.0
        for key in buckets:
            st_rate, lt_rate, _ = key
            if tot_st:
                tax += net_st * (pos_st[key] / tot_st) * st_rate
            if tot_lt:
                tax += taxable_lt * (pos_lt[key] / tot_lt) * lt_rate
        cess = schedule["view_parameters"]["cess"]
        out.append({"fy": fy, "stcg": round(net_st, 2), "ltcg": round(net_lt, 2),
                    "carried_st_loss": round(sum(v["amount"] for v in vint if v["kind"] == "st"), 2),
                    "carried_lt_loss": round(sum(v["amount"] for v in vint if v["kind"] == "lt"), 2),
                    "tax_before_cess": round(tax, 2), "tax_with_cess": round(tax * (1 + cess), 2)})
    return out


# ------------------------------------------------------------------ promotion metrics (Doc 04 s11)
def alpha_annualised(monthly_excess):
    return sum(monthly_excess) / len(monthly_excess) * 12


def sharpe_annualised(monthly_excess):
    n = len(monthly_excess)
    mu = sum(monthly_excess) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in monthly_excess) / (n - 1))   # sample sd
    return (mu / sd) * math.sqrt(12)


def newey_west_se(series, lag):
    """SE of the mean with Bartlett weights: gamma0 + 2*sum (1 - j/(lag+1)) * gamma_j, all over n."""
    n = len(series)
    mu = sum(series) / n
    dev = [x - mu for x in series]
    g = lambda j: sum(dev[t] * dev[t - j] for t in range(j, n)) / n
    var = g(0) + 2 * sum((1 - j / (lag + 1)) * g(j) for j in range(1, lag + 1))
    return math.sqrt(var / n)


def turnover(total_traded_value, average_portfolio_value, years):
    return total_traded_value / 2 / average_portfolio_value / years


def rolling_windows(monthly_returns, window=36, step=1):
    out = []
    for i in range(0, len(monthly_returns) - window + 1, step):
        w = monthly_returns[i:i + window]
        out.append((1 + sum(w) / len(w)) ** 12 - 1)
    return out


def sensitivity_ok(center, neighbours, floor_ratio=0.5, spike_ratio=1.5):
    """Anti-overfitting shape: a broad stable region - same sign everywhere, no cliff, and the
    chosen point is not an isolated spike. It does NOT require the chosen point to be the peak."""
    if not neighbours:
        return False
    same_sign = all((n > 0) == (center > 0) for n in neighbours)
    no_cliff = min(abs(n) for n in neighbours) >= floor_ratio * abs(center)
    mean_n = sum(neighbours) / len(neighbours)
    no_spike = abs(center) <= spike_ratio * abs(mean_n)
    return same_sign and no_cliff and no_spike
