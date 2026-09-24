#!/usr/bin/env python3
"""Reference implementations of every feature the strategy cards read (registry 3.0.0 `features`,
`forensic_flags` and `window_conventions`). Audit B8: in r5.4 only 2 of the 36 card-read features had any
executable definition; the rest were a registry sentence. Each function here implements that sentence
literally, and golden/feature_cases.yaml fixes it with hand-computed answers. M6 must reproduce them.

Conventions:
  - Every function returns a value-state dict: {"state": "known", "value": v, ...flags}, {"state": "missing"},
    or {"state": "out_of_domain", "outcome": "fail" | "drop"}.
  - A session series is a list, oldest first, with the evaluation session t LAST. An absent session (suspended
    or untraded, window_conventions.present) is None, or a bar whose "present" is False.
  - Muhurat sessions are not in any series (window_conventions.session).
"""
import math
import statistics

import reference_sim as R

ANNUAL = math.sqrt(250)


def K(v, **flags):
    return {"state": "known", "value": v, **flags}


def MISSING(reason=None):
    return {"state": "missing", **({"reason": reason} if reason else {})}


def OOD(outcome):
    return {"state": "out_of_domain", "outcome": outcome}


def known(x):
    return isinstance(x, dict) and x.get("state") == "known"


def _q(x):
    """evaluation_semantics.arithmetic applies inside forensic flags too: quantise to 9 dp, then compare exactly,
    so (0.1 + 0.1 + 0.1) / 3 is 0.10, not 0.10000000000000002 > 0.10."""
    import decimal
    return decimal.Decimal(repr(float(x))).quantize(decimal.Decimal("1e-9"), rounding=decimal.ROUND_HALF_EVEN)


def gt(a, b):
    return _q(a) > _q(b)


def lt(a, b):
    return _q(a) < _q(b)


# ------------------------------------------------------------------ fundamentals
def ebit_underlying(y):
    return y["pbt"] + y["finance_costs"] - y["other_income"] - y["exceptional_net"]


def capital_employed(y):
    return y["total_equity_owners"] + y["borrowings"] + y["lease_liabilities"] - y["cash_equivalents"]


def _complete_pl(y):
    return all(y.get(k) is not None for k in ("revenue", "pbt", "tax", "pat_owners"))


def operating_history_years(years):
    """Consecutive FYs ending with the latest, each with a complete canonical P&L."""
    n = 0
    for y in reversed(years):
        if not _complete_pl(y):
            break
        n += 1
    return K(n)


def annual_roce(years, i):
    """roce_rule for FY years[i], with years[i-1] giving the FY-start balance sheet."""
    if i < 1:
        return MISSING("no prior FY balance sheet")
    y, p = years[i], years[i - 1]
    need = ("pbt", "finance_costs", "other_income", "exceptional_net", "total_equity_owners", "borrowings",
            "lease_liabilities", "cash_equivalents", "total_assets")
    if any(y.get(k) is None for k in need) or any(p.get(k) is None for k in need[4:]):
        return MISSING()
    return R.roce(ebit_underlying(y), y["total_equity_owners"], y["borrowings"], y["lease_liabilities"],
                  y["cash_equivalents"], y["total_assets"], capital_employed(p), p["total_assets"])


def _roce_series(years, n):
    if len(years) < n + 1:
        return None, MISSING("insufficient history")
    vals = [annual_roce(years, i) for i in range(len(years) - n, len(years))]
    if any(v["state"] == "out_of_domain" for v in vals):
        return None, OOD("fail")
    if any(v["state"] != "known" for v in vals):
        return None, MISSING()
    return [v["value"] for v in vals], None


def roce_3y_avg(years):
    vals, bad = _roce_series(years, 3)
    return bad or K(round(sum(vals) / 3, 6))


def roce_hy_ttm(ttm_ebit, equity_now, ce_now, ce_12m, ta_now, ta_12m):
    """roce_rule on TTM EBIT, CE averaged now and 12 months earlier."""
    if equity_now <= 0:
        return OOD("fail")
    ce_avg, ta_avg = (ce_now + ce_12m) / 2, (ta_now + ta_12m) / 2
    if ce_avg <= 0.05 * ta_avg:
        return OOD("fail") if ttm_ebit <= 0 else K(1.0, cash_rich_capped=True, capped=True)
    v = ttm_ebit / ce_avg
    return K(round(min(v, 1.0), 6), cash_rich_capped=False, capped=v > 1.0)


def roce_5y_trend(years):
    """OLS slope of the latest 5 annual ROCE against 1..5, over their mean; mean <= 0 -> out_of_domain fail."""
    vals, bad = _roce_series(years, 5)
    if bad:
        return {**bad, "outcome": "fail"} if bad["state"] == "out_of_domain" else bad
    mean = sum(vals) / 5
    if mean <= 0:
        return OOD("fail")
    xs = [1, 2, 3, 4, 5]
    slope = sum((x - 3) * (v - mean) for x, v in zip(xs, vals)) / sum((x - 3) ** 2 for x in xs)
    return K(round(slope / mean, 6))


def roce_stability(years):
    vals, bad = _roce_series(years, 5)
    if bad:
        return OOD("drop") if bad["state"] == "out_of_domain" else bad
    return K(round(1 / (1 + statistics.pstdev(vals)), 6))


def cfo_pat_3y(years):
    last = years[-3:]
    if len(last) < 3 or any(y.get("cfo") is None or y.get("pat_owners") is None for y in last):
        return MISSING()
    return R.cfo_pat(sum(y["cfo"] for y in last), sum(y["pat_owners"] for y in last))


def debt_equity(borrowings, lease_liabilities, equity):
    if equity <= 0:
        return OOD("fail")
    return K(round((borrowings + lease_liabilities) / equity, 6))


def interest_coverage(ttm_ebit, ttm_finance_costs):
    if ttm_finance_costs == 0:
        return K(100.0, no_finance_cost=True)
    return K(round(min(ttm_ebit / ttm_finance_costs, 100.0), 6), no_finance_cost=False)


def positive_revenue_growth_years_5y(revenues):
    """Revenues oldest first; needs 6 FY; counts the latest 5 FY with revenue above the prior FY's."""
    r = revenues[-6:]
    if len(r) < 6 or any(v is None for v in r):
        return MISSING()
    return K(sum(1 for a, b in zip(r, r[1:]) if b > a))


def exceptional_frequency(exceptionals):
    e = exceptionals[-5:]
    if len(e) < 5 or any(v is None for v in e):
        return MISSING()
    return K(sum(1 for v in e if v != 0))


def pat_underlying(pat_owners, exceptional_net, tax, pbt):
    """Doc 02 s7: exceptionals removed net of the effective tax rate when 0 <= etr <= 0.5 and pbt > 0, else gross."""
    etr = tax / pbt if pbt > 0 else None
    if etr is None or not (0 <= etr <= 0.5):
        etr = 0.0
    return pat_owners - exceptional_net * (1 - etr)


def market_cap(close_raw, shares_outstanding):
    return K(close_raw * shares_outstanding)


def earnings_yield_ttm(quarterly_pat_underlying, mcap, in_blackout=False):
    if in_blackout:
        return OOD("drop")
    q = quarterly_pat_underlying[-4:]
    if len(q) < 4 or any(v is None for v in q):
        return MISSING()
    return K(round(sum(q) / mcap, 6))


def ey_median_5y(daily, last_transformative_index=None):
    """daily: the last <=1250 sessions of {"ey": value or None, "blackout": bool}, oldest first.
    Excludes blackout sessions and sessions on or before the latest valuation-transformative ex-date
    (index into `daily`); >= 750 known values, else out_of_domain drop. Rights issues are not transformative."""
    window = daily[-1250:]
    offset = len(daily) - len(window)
    vals = [d["ey"] for i, d in enumerate(window) if d["ey"] is not None and not d["blackout"]
            and (last_transformative_index is None or i + offset > last_transformative_index)]
    if len(vals) < 750:
        return OOD("drop")
    return K(round(statistics.median(vals), 6))


def ey_vs_own_5y_median(ey, median, in_blackout=False):
    if not (known(ey) and known(median)):
        return MISSING()
    if in_blackout or ey["value"] <= 0 or median["value"] <= 0:
        return OOD("fail")
    return K(round(ey["value"] / median["value"], 6))


def _ev_ebitda(x):
    return (x["market_cap"] + x["borrowings"] + x["lease_liabilities"] - x["cash_equivalents"]) / x["ttm_ebitda"]


def ev_ebitda_vs_sector(own, peers, in_blackout=False):
    """own/peers: {market_cap, borrowings, lease_liabilities, cash_equivalents, ttm_ebitda}; peers exclude the
    security itself and are the same sector, market-eligible on the date, before any card's exclusions."""
    if in_blackout or own["ttm_ebitda"] <= 0:
        return OOD("drop")
    valid = [_ev_ebitda(p) for p in peers if p["ttm_ebitda"] > 0]
    if len(valid) < 8:
        return OOD("drop")
    med = statistics.median(valid)
    if med <= 0:
        return OOD("drop")
    return K(round(_ev_ebitda(own) / med, 6))


def earnings_yield_spread(ey, gsec_10y):
    return K(round(ey - gsec_10y, 6))


def promoter_pledge_pct(pledged_shares, promoter_shares):
    """A company with no promoter holding has 0.0: nothing can be pledged (it does not fail a pledge gate)."""
    if promoter_shares == 0:
        return K(0.0, no_promoter=True)
    return K(round(pledged_shares / promoter_shares, 6), no_promoter=False)


def auditor_resignation_5y(events, cutoff_date, coverage_complete_for_window):
    if not coverage_complete_for_window:
        return MISSING("no_source_coverage")
    start = cutoff_date.replace(year=cutoff_date.year - 5)
    return K(any(e["kind"] == "resignation" and start < e["effective_date"] <= cutoff_date for e in events))


# ------------------------------------------------------------------ forensic flags
def flag_accrual_high(years):
    if len(years) < 4:
        return None
    ratios = []
    for i in range(len(years) - 3, len(years)):
        y, p = years[i], years[i - 1]
        if any(v is None for v in (y.get("pat_owners"), y.get("cfo"), y.get("total_assets"), p.get("total_assets"))):
            return None
        ratios.append((y["pat_owners"] - y["cfo"]) / ((y["total_assets"] + p["total_assets"]) / 2))
    return gt(sum(ratios) / 3, 0.10)


def flag_receivables_diverging(receivable_days, opm):
    """Both lists oldest first; needs the latest 3 FY of each."""
    rd, om = receivable_days[-3:], opm[-3:]
    if len(rd) < 3 or len(om) < 3 or any(v is None for v in rd + om):
        return None
    return all(gt(rd[i], 1.20 * rd[i - 1]) and lt(om[i], om[i - 1]) for i in (1, 2))


def flag_inventory_diverging(inventory_days, revenues, inventory_latest):
    """Applicable only if inventory > 0 at the latest FY end. Returns (applicable, value)."""
    if inventory_latest is None or inventory_latest <= 0:
        return False, None
    idays, rev = inventory_days[-2:], revenues[-3:]
    if len(idays) < 2 or len(rev) < 3 or any(v is None for v in idays + rev):
        return True, None
    g_now, g_prev = rev[2] / rev[1] - 1, rev[1] / rev[0] - 1
    return True, gt(idays[1], 1.25 * idays[0]) and lt(g_now, g_prev)


def flag_exceptional_habitual(exc_freq):
    return None if not known(exc_freq) else exc_freq["value"] >= 3


def flag_dilution_persistent(shares_now, shares_5y_ago):
    if shares_now is None or not shares_5y_ago:
        return None
    return gt(shares_now / shares_5y_ago - 1, 0.15)


def flag_auditor_churn(events, cutoff_date, coverage_complete_for_window):
    if not coverage_complete_for_window:
        return None
    start = cutoff_date.replace(year=cutoff_date.year - 5)
    changes = [e for e in events if start < e["effective_date"] <= cutoff_date
               and e["kind"] in ("resignation", "other")]      # 'rotation' (mandatory) excluded
    return len(changes) >= 2


def flag_related_party_large(rpt_total, revenue, disclosure_present):
    if not disclosure_present:
        return False, None
    if rpt_total is None or not revenue:
        return True, None
    return True, gt(rpt_total / revenue, 0.10)


def flag_promoter_reducing(promoter_holdings_last4):
    """Promoter holding (decimal) in the last 4 shareholding filings, oldest first."""
    h = promoter_holdings_last4[-4:]
    if len(h) < 4 or any(v is None for v in h):
        return None
    return gt(h[0] - h[3], 0.05)


def forensic_count_and_coverage(flags):
    """flags: [(applicable: bool, value: True | False | None)] for the 8 registered flags."""
    applicable = [v for a, v in flags if a]
    evaluable = [v for v in applicable if v is not None]
    cov = 1.0 if not applicable else len(evaluable) / len(applicable)
    return K(sum(1 for v in evaluable if v)), K(round(cov, 6))


def surveillance_stage(on_date, framework_starts, listed_stage, covered):
    """Before every framework's start: known none. After a start: the listed stage if the list for the date is
    covered (absent from a covered list = none), else missing."""
    if all(on_date < s for s in framework_starts.values()):
        return K("none")
    if not covered:
        return MISSING("no_source_coverage")
    return K(listed_stage or "none")


def is_fno_eligible(eligible, covered):
    return K(bool(eligible)) if covered else MISSING("no_source_coverage")


# ------------------------------------------------------------------ price features (window_conventions)
def _present(b):
    return b is not None and b.get("present", True)


def lookback(series, k, field):
    """X(t-k): the value k sessions before t (t is last); if absent, the last present value at or before t-k
    within 5 sessions, else None."""
    idx = len(series) - 1 - k
    for j in range(idx, idx - 6, -1):
        if 0 <= j < len(series) and _present(series[j]):
            return series[j][field]
    return None


def _ret(series, near, far):
    a, b = lookback(series, near, "tr"), lookback(series, far, "tr")
    return MISSING() if a is None or b is None else K(round(a / b - 1, 6))


def ret_12m_skip_1m(series):
    return _ret(series, 21, 252)


def ret_6m_skip_1m(series):
    return _ret(series, 21, 126)


def _log_returns(window):
    return [math.log(b["adj_close"] / a["adj_close"]) for a, b in zip(window, window[1:]) if _present(a) and _present(b)]


def realised_vol(series, n, min_returns):
    """Sample stdev of daily log returns among the last n sessions (returns between consecutive present
    sessions only) x sqrt(250)."""
    rets = _log_returns(series[-(n + 1):])
    if len(rets) < min_returns:
        return OOD("drop")
    v = statistics.stdev(rets) * ANNUAL
    return K(round(v, 6)) if v > 0 else OOD("drop")


def realised_vol_60d(series):
    return realised_vol(series, 60, 54)


def realised_vol_1y(series):
    return realised_vol(series, 250, 225)


def vol_adj(ret, vol):
    if not (known(ret) and known(vol)):
        return MISSING()
    return K(round(ret["value"] / vol["value"], 6))


def rel_strength_6m_vs_nifty200_tri(stock, index):
    a, b = lookback(stock, 21, "tr"), lookback(stock, 126, "tr")
    c, d = lookback(index, 21, "tr"), lookback(index, 126, "tr")
    if None in (a, b, c, d):
        return MISSING()
    return K(round(a / b - c / d, 6))


def adv_20d_cr(series):
    """Mean traded value (INR) / 1e7 over the present sessions of the last 20; an untraded but listed session is
    present with traded value 0; >= 15 present."""
    w = [b for b in series[-20:] if _present(b)]
    if len(w) < 15:
        return MISSING()
    return K(round(sum(b["traded_value"] for b in w) / len(w) / 1e7, 6))


def delivery_pct_20d_avg(series):
    """Volume-weighted ratio of sums over the sessions of the last 20 with volume > 0 and known delivery;
    >= 15 such sessions. (Not the mean of daily ratios: a 10-share day must not weigh like a 10-lakh day.)"""
    w = [b for b in series[-20:] if _present(b) and b["volume"] > 0 and b.get("delivery_qty") is not None]
    if len(w) < 15:
        return MISSING()
    return K(round(sum(b["delivery_qty"] for b in w) / sum(b["volume"] for b in w), 6))


def price_vs_dma(series, n, min_present):
    if not _present(series[-1]):
        return MISSING()
    w = [b["adj_close"] for b in series[-n:] if _present(b)]
    if len(w) < min_present:
        return MISSING()
    return K(round(series[-1]["adj_close"] / (sum(w) / len(w)), 6))


def price_vs_dma50(series):
    return price_vs_dma(series, 50, 45)


def price_vs_dma200(series):
    return price_vs_dma(series, 200, 180)


def atr_pct_20(series):
    """Mean true range over the present sessions of the last 20 / adjusted close at t. True range uses the prior
    session's close when that session was present, else high - low. >= 18 present."""
    if not _present(series[-1]):
        return OOD("drop")
    start = len(series) - 20
    trs = []
    for i in range(max(0, start), len(series)):
        b = series[i]
        if not _present(b):
            continue
        p = series[i - 1] if i > 0 else None
        if _present(p):
            trs.append(max(b["adj_high"], p["adj_close"]) - min(b["adj_low"], p["adj_close"]))
        else:
            trs.append(b["adj_high"] - b["adj_low"])
    if len(trs) < 18:
        return OOD("drop")
    v = sum(trs) / len(trs) / series[-1]["adj_close"]
    return K(round(v, 6)) if v > 0 else OOD("drop")


def circuit_days_60d(band_states):
    """band_states: the last 60 sessions' band_close_state, None where no band file covers the session."""
    w = band_states[-60:]
    if len(w) < 60 or any(s is None for s in w):
        return MISSING("no_source_coverage")
    return K(sum(1 for s in w if s in ("closed_at_upper_band", "closed_at_lower_band")))


def market_breadth(dma200_values):
    k = [v for v in dma200_values if known(v)]
    return MISSING() if not k else K(round(sum(1 for v in k if gt(v["value"], 1)) / len(k), 6))
