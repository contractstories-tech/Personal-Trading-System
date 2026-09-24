#!/usr/bin/env python3
"""Runs golden/feature_cases.yaml against reference_features.py, then plants one defect per ambiguity that the
registry 3.0.0 feature text resolves; every planted defect must make a case fail (audit B8).

    python3 test_features.py        (exit 0 = all pass)
    python3 -m pytest -q
"""
import datetime as dt
import os
import statistics
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reference_features as F  # noqa: E402
from test_golden import close  # noqa: E402

G = yaml.safe_load(open(os.path.join(HERE, "golden", "feature_cases.yaml"), encoding="utf-8"))


def _field(spec, i, base=None):
    if spec is None:
        return None
    if "set" in spec and i in spec["set"]:
        return spec["set"][i]
    if "const" in spec:
        return spec["const"]
    if "linear" in spec:
        return spec["linear"][0] + spec["linear"][1] * i
    if "alt" in spec:
        return spec["alt"][i % 2]
    if "offset" in spec:
        return base + spec["offset"]
    raise ValueError(spec)


def build_series(spec):
    out = []
    for i in range(spec["n"]):
        if i in spec.get("absent", []):
            out.append(None)
            continue
        b = {"present": True}
        for k in ("tr", "adj_close", "traded_value", "volume", "delivery_qty"):
            if k in spec:
                b[k] = _field(spec[k], i)
        for k in ("adj_high", "adj_low"):
            if k in spec:
                b[k] = _field(spec[k], i, b["adj_close"])
        out.append(b)
    return out


def _years(c):
    ys = [dict(y) for y in c["years"]]
    for i, patch in (c.get("patch") or {}).items():
        ys[i].update(patch)
    return ys[:c["slice"]] if c.get("slice") else ys


def _peer(r):
    if isinstance(r, dict):
        return {"market_cap": 0, "borrowings": 0, "lease_liabilities": 0, "cash_equivalents": 0, **r}
    return {"market_cap": abs(r) * 100, "borrowings": 0, "lease_liabilities": 0, "cash_equivalents": 0,
            "ttm_ebitda": 100 if r > 0 else -100}


def cases():
    for c in G["fundamentals"]:
        fn = getattr(F, c["fn"])
        if c["fn"] == "annual_roce":
            got = fn(_years(c), c["index"])
        elif "years" in c:
            got = fn(_years(c))
        elif "revenues" in c:
            got = fn(c["revenues"])
        elif "exceptionals" in c:
            got = fn(c["exceptionals"])
        else:
            got = fn(*c["args"])
        yield c["id"], got, c["expect"]
    for c in G["ey_median"]:
        daily = [{"ey": v, "blackout": False} for n, v in c["blocks"] for _ in range(n)]
        yield c["id"], F.ey_median_5y(daily, c["transformative_index"]), c["expect"]
    for c in G["ev_ebitda"]:
        yield c["id"], F.ev_ebitda_vs_sector(_peer(c["own"]), [_peer(p) for p in c["peers"]], c.get("blackout", False)), c["expect"]
    for c in G["events"]:
        yield c["id"], F.auditor_resignation_5y(c["events"], c["cutoff"], c["covered"]), c["expect"]
    for c in G["flags"]:
        fn = getattr(F, c["fn"])
        if c["fn"] == "forensic_count_and_coverage":
            got = list(fn([tuple(x) for x in c["flags"]]))
        elif "years" in c:
            got = fn(c["years"])
        elif "events" in c:
            got = fn(c["events"], c["cutoff"], c["covered"])
        else:
            got = fn(*c["args"])
        yield c["id"], got, c["expect"]
    for c in G["states"]:
        if c["fn"] == "surveillance_stage":
            got = F.surveillance_stage(c["on_date"], c["starts"], c["listed"], c["covered"])
        else:
            got = getattr(F, c["fn"])(*c["args"])
        yield c["id"], got, c["expect"]
    for c in G["prices"]:
        fn = getattr(F, c["fn"])
        if "index" in c:
            got = fn(build_series(c["series"]), build_series(c["index"]))
        elif "series" in c:
            got = fn(build_series(c["series"]))
        elif "bands" in c:
            b = c["bands"]
            states = [None if i in b.get("uncovered", []) else
                      ("closed_at_upper_band" if i in b["closed"] else "within_band") for i in range(b["n"])]
            got = fn(states)
        else:
            got = fn(*c["args"])
        yield c["id"], got, c["expect"]


# every feature a card reads, and the golden function(s) that fix it (audit B8: coverage is checked, not claimed)
CARD_FEATURE_TO_FN = {
    "operating_history_years": ["operating_history_years"], "roce_3y_avg": ["roce_3y_avg", "annual_roce"], "roce_hy_ttm": ["roce_hy_ttm"],
    "roce_5y_trend": ["roce_5y_trend"], "roce_stability": ["roce_stability"], "cfo_pat_3y": ["cfo_pat_3y"],
    "debt_equity": ["debt_equity"], "interest_coverage": ["interest_coverage"],
    "positive_revenue_growth_years_5y": ["positive_revenue_growth_years_5y"], "exceptional_frequency": ["exceptional_frequency"],
    "market_cap": ["market_cap"], "earnings_yield_ttm": ["earnings_yield_ttm", "pat_underlying"], "ey_median_5y": ["ey_median"],
    "ey_vs_own_5y_median": ["ey_vs_own_5y_median"], "ev_ebitda_vs_sector": ["ev_ebitda"], "earnings_yield_spread": ["earnings_yield_spread"],
    "realised_vol_1y": ["realised_vol_1y"], "promoter_pledge_pct": ["promoter_pledge_pct"],
    "auditor_resignation_5y": ["auditor_resignation_5y"],
    "forensic_flag_count": ["forensic_count_and_coverage", "flag_accrual_high", "flag_receivables_diverging",
                            "flag_inventory_diverging", "flag_exceptional_habitual", "flag_dilution_persistent",
                            "flag_auditor_churn", "flag_related_party_large", "flag_promoter_reducing"],
    "forensic_coverage_pct": ["forensic_count_and_coverage"], "surveillance_stage": ["surveillance_stage"],
    "ret_12m_skip_1m": ["ret_12m_skip_1m"], "ret_6m_skip_1m": ["ret_6m_skip_1m"], "realised_vol_60d": ["realised_vol_60d"],
    "vol_adj_mom_12m": ["vol_adj"], "vol_adj_mom_6m": ["vol_adj"],
    "rel_strength_6m_vs_nifty200_tri": ["rel_strength_6m_vs_nifty200_tri"], "adv_20d_cr": ["adv_20d_cr"],
    "delivery_pct_20d_avg": ["delivery_pct_20d_avg"], "is_fno_eligible": ["is_fno_eligible"], "price_vs_dma50": ["price_vs_dma50"],
    "price_vs_dma200": ["price_vs_dma200"], "atr_pct_20": ["atr_pct_20"], "circuit_days_60d": ["circuit_days_60d"],
    "market_breadth": ["market_breadth"],
}


def coverage_gaps():
    """Features read by a card with no golden case for every function that defines them."""
    cards = [yaml.safe_load(open(os.path.join(HERE, "strategies", f), encoding="utf-8")) for f in sorted(os.listdir(os.path.join(HERE, "strategies")))]
    used = {f for c in cards for f in c["features"]}
    have = {c.get("fn") for sec in G.values() if isinstance(sec, list) for c in sec if isinstance(c, dict)}
    have |= {"ey_median", "ev_ebitda"} if G.get("ey_median") and G.get("ev_ebitda") else set()
    gaps = sorted(f for f in used if f not in CARD_FEATURE_TO_FN)
    gaps += sorted(f"{f} -> {fn}" for f in used for fn in CARD_FEATURE_TO_FN.get(f, []) if fn not in have)
    return gaps


def run(verbose=True):
    fails = []
    for cid, got, want in cases():
        ok = close(got, want, 1e-6)
        if verbose and not ok:
            print(f"FAIL  {cid}   got {got!r}  want {want!r}")
        if not ok:
            fails.append(cid)
    n = sum(1 for _ in cases())
    if verbose:
        print(f"{n - len(fails)}/{n} feature golden cases passed")
    return fails


# ---------------- planted definition defects: each is a reasonable misreading of r5.4's prose ----------------
def _mutants():
    orig = {k: getattr(F, k) for k in dir(F) if callable(getattr(F, k)) and not k.startswith("_")}

    def delivery_mean_of_ratios(series):
        w = [b for b in series[-20:] if F._present(b) and b["volume"] > 0 and b.get("delivery_qty") is not None]
        return F.MISSING() if len(w) < 15 else F.K(round(sum(b["delivery_qty"] / b["volume"] for b in w) / len(w), 6))

    def dma_over_calendar_sessions(series, n, min_present):
        w = [b["adj_close"] for b in series[-n:] if F._present(b)]
        return F.MISSING() if len(w) < min_present else F.K(round(series[-1]["adj_close"] / (sum(w) / n), 6))

    def lookback_without_fallback(series, k, field):
        b = series[len(series) - 1 - k]
        return b[field] if F._present(b) else None

    def vol_population_sd(series, n, min_returns):
        rets = F._log_returns(series[-(n + 1):])
        return F.OOD("drop") if len(rets) < min_returns else F.K(round(statistics.pstdev(rets) * F.ANNUAL, 6))

    def ey_median_no_window(daily, last_transformative_index=None):
        return orig["ey_median_5y"]([{"ey": None, "blackout": False}] * 0 + daily * 1, last_transformative_index) \
            if len(daily) <= 1250 else F.K(round(statistics.median([d["ey"] for d in daily]), 6))

    def pledge_missing_without_promoter(pledged, promoter):
        return F.MISSING() if promoter == 0 else orig["promoter_pledge_pct"](pledged, promoter)

    def atr_ignores_prior_close(series):
        w = [b for b in series[-20:] if F._present(b)]
        if len(w) < 18:
            return F.OOD("drop")
        return F.K(round(sum(b["adj_high"] - b["adj_low"] for b in w) / len(w) / series[-1]["adj_close"], 6))

    def ev_peer_median_includes_self(own, peers, in_blackout=False):
        return orig["ev_ebitda_vs_sector"](own, peers + [own], in_blackout)

    def growth_counts_flat_years(revenues):
        r = revenues[-6:]
        if len(r) < 6 or any(v is None for v in r):
            return F.MISSING()
        return F.K(sum(1 for a, b in zip(r, r[1:]) if b >= a))

    def history_counts_all_years(years):
        return F.K(sum(1 for y in years if F._complete_pl(y)))

    def adv_skips_untraded_days(series):
        w = [b for b in series[-20:] if F._present(b) and b["traded_value"] > 0]
        return F.MISSING() if len(w) < 15 else F.K(round(sum(b["traded_value"] for b in w) / len(w) / 1e7, 6))

    def trend_not_scaled(years):
        out = orig["roce_5y_trend"](years)
        return out if out["state"] != "known" else F.K(round(out["value"] * 0.24, 6))

    def churn_counts_rotation(events, cutoff_date, covered):
        return orig["flag_auditor_churn"]([dict(e, kind="other") for e in events], cutoff_date, covered)

    def surveillance_missing_before_frameworks(on_date, starts, listed, covered):
        return F.MISSING("no_source_coverage") if not covered else orig["surveillance_stage"](on_date, starts, listed, covered)

    return [("delivery % as the mean of daily ratios", "delivery_pct_20d_avg", delivery_mean_of_ratios),
            ("DMA divided by the window length, not the present sessions", "price_vs_dma", dma_over_calendar_sessions),
            ("lookback with no fallback for an absent session", "lookback", lookback_without_fallback),
            ("population sd for volatility", "realised_vol", vol_population_sd),
            ("earnings-yield median over all history, not 1250 sessions", "ey_median_5y", ey_median_no_window),
            ("no promoter -> pledge missing (fails the gate)", "promoter_pledge_pct", pledge_missing_without_promoter),
            ("ATR ignores the prior close (gaps vanish)", "atr_pct_20", atr_ignores_prior_close),
            ("EV/EBITDA peer median includes the security itself", "ev_ebitda_vs_sector", ev_peer_median_includes_self),
            ("flat revenue counted as growth", "positive_revenue_growth_years_5y", growth_counts_flat_years),
            ("operating history counts non-consecutive years", "operating_history_years", history_counts_all_years),
            ("ADV skips listed-but-untraded days", "adv_20d_cr", adv_skips_untraded_days),
            ("ROCE trend not divided by its mean", "roce_5y_trend", trend_not_scaled),
            ("auditor churn counts mandatory rotation", "flag_auditor_churn", churn_counts_rotation),
            ("surveillance missing before any framework existed", "surveillance_stage", surveillance_missing_before_frameworks)]


def check_teeth(verbose=True):
    survivors = []
    for name, attr, fn in _mutants():
        saved = getattr(F, attr)
        setattr(F, attr, fn)
        try:
            caught = [cid for cid, got, want in cases() if not close(got, want, 1e-6)]
        except Exception as e:
            caught = []
            print(f"   MUTANT ERROR (fix the mutant): {name}: {type(e).__name__}: {e}")
        finally:
            setattr(F, attr, saved)
        if verbose:
            print(f"{'caught' if caught else 'SURVIVED':9} {name}" + (f"  by {caught[:3]}" if caught else ""))
        if not caught:
            survivors.append(name)
    return survivors


def test_feature_golden_cases():
    assert run(verbose=False) == []


def test_every_card_feature_has_golden_cases():
    assert coverage_gaps() == []


def test_feature_cases_have_teeth():
    assert check_teeth(verbose=False) == []


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):   # UTF-8 output whatever the console or pipe (Windows defaults to cp1252)
        _s.reconfigure(encoding="utf-8")
    fails = run()
    gaps = coverage_gaps()
    print("every card-read feature has golden cases" if not gaps else f"COVERAGE GAPS: {gaps}")
    fails += gaps
    surv = check_teeth()
    print(f"{len(_mutants()) - len(surv)}/{len(_mutants())} planted feature defects caught")
    sys.exit(1 if (fails or surv) else 0)
