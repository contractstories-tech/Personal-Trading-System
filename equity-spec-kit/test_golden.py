#!/usr/bin/env python3
"""Runs every golden case in golden/golden_cases.yaml against reference_sim.

    python3 test_golden.py      (exit 0 = all pass)
    python3 -m pytest -q        (test_* entry point)

A production engine proves conformance by exposing the same functions and passing this file.
"""
import math, os, sys
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reference_sim as R  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
G = yaml.safe_load(open(os.path.join(HERE, "golden", "golden_cases.yaml")))
COSTS = yaml.safe_load(open(os.path.join(HERE, "schedules", "costs_india_equity_delivery.yaml")))
TAX = yaml.safe_load(open(os.path.join(HERE, "schedules", "tax_india_listed_equity.yaml")))


def close(a, b, tol=1e-6):
    if a is None or b is None:
        return a is b
    if isinstance(b, dict):
        return isinstance(a, dict) and set(a) == set(b) and all(close(a[k], b[k], tol) for k in b)
    if isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(close(x, y, tol) for x, y in zip(a, b))
    if isinstance(b, bool) or isinstance(a, bool) or isinstance(b, str):
        return a == b
    return math.isclose(a, b, abs_tol=tol)


def cases():
    for c in G["fills"]:
        yield c["id"], R.fill_buy_limit(c["limit"], c["open"], c["upper_band"]), c["expect"], 1e-9
    for c in G["sells"]:
        px, d = R.fill_sell_on_open(c["sessions"])
        yield c["id"], [px, d], c["expect"], 1e-4
    for c in G["impact"]:
        v = R.impact_cost(c["value_cr"], c["adv_cr"])
        yield c["id"], [v, v <= 0.0035], [c["expect"], c["s1_passes"]], 1e-6
    for c in G["costs"]:
        yield c["id"], R.trade_costs(c["side"], c["value"], c["date"], COSTS), c["expect"], 0.005
    for c in G["tax"]:
        yield c["id"], R.tax_view(c["disposals"], TAX, c["fy"]), c["expect"], 0.005
    for c in G["holding_period"]:
        yield c["id"], R.is_long_term(c["buy"], c["sell"]), c["expect"], 0
    for c in G["stop"]:
        yield c["id"], R.run_stop(c["entry_fill"], c["atr_at_entry"], c["sessions"]), c["expect"], 1e-4
    for c in G["corporate_actions"]:
        if c["kind"] == "split_bonus":
            out = R.split_bonus(c["qty"], c["price_state"], c["f"], c["p_cum"])
        elif c["kind"] == "demerger":
            out = R.demerger(c["parent_qty"], c["p_cum"], c["p_discovered"], c["ratio"])
        else:
            out = R.rights_value(c["held"], c["a"], c["b"], c["S"], c["p_cum"], c.get("re_listed_close"))
        yield c["id"], out, c["expect"], 1e-4
    for c in G["tranches"]:
        yield c["id"], R.lt_tranches(c["target_value"], c["entry_ref"], c["weights"], c["t2"], c["t3"]), c["expect"], 0
    for c in G["persist"]:
        yield c["id"], R.persist(c["values"], c["n"]), c["expect"], 0
    for c in G["zscores"]:
        vals = list(eval(c["values"], {"range": range}))  # fixture-local expression, trusted file
        z = R.zscores(vals, c["direction"])[c["index"]]
        yield c["id"], z, c["expect"], c.get("tol", 1e-6)
    for c in G["features"]:
        fn = R.roce if c["kind"] == "roce" else R.cfo_pat
        yield c["id"], fn(**c["args"]), c["expect"], 1e-6
    for c in G["ranking"]:
        yield c["id"], R.rank_order(c["rows"]), c["expect"], 0
    rows = G["pit"]["rows"]
    for c in G["pit"]["cases"]:
        row = R.asof(rows, "INE0TEST", c["basis"], c["cutoff"])
        yield c["id"], row["value"] if row else None, c["expect_value"], 0
    cn = G["pit"]["canary"]
    try:
        R.read_checked(rows[cn["row_index"]], cn["cutoff"])
        raised = False
    except R.LookAheadError:
        raised = True
    yield cn["id"], raised, True, 0
    for c in G["blackout"]:
        yield c["id"], R.in_blackout(c["quarters"]), c["expect"], 0
    # ---- r5.2 ----
    cu = G["cutoffs"]
    for c in cu["cases"]:
        row = R.asof_domain(cu["rows"], "INE0TEST", c["domain"], cu["cutoffs"])
        yield c["id"], row["value"] if row else None, c["expect_value"], 0
    bf_rows = [{"isin": "INE0T", "basis": "consolidated", "usable_from": "2026-09-01T18:00", "value": 1},
               {"isin": "INE0T", "basis": "standalone", "usable_from": "2026-09-02T18:00", "value": 2}]
    for c in G["basis_fallback"]:
        row = R.asof_with_basis_fallback(bf_rows, "INE0T", "2026-09-03T20:00", c["files_consolidated"])
        yield c["id"], row["value"] if row else None, c["expect_value"], 0
    for c in G["bounded_qty"]:
        q = R.bounded_qty(c["target_value"], c["reference_price"], c["hard_cap_value"], c["limit_price"])
        yield c["id"], [q, q * c["limit_price"]], [c["expect"], c["worst_case_value"]], 1e-6
    for c in G["allocator"]:
        yield c["id"], R.security_target(c["claims"]), c["expect"], 1e-6
    for c in G["slots"]:
        yield c["id"], R.allocate_slots(c["candidates"], c["max_open_positions"], set(c["existing"])), c["expect"], 0
    for c in G["dividends"]:
        yield c["id"], R.dividend_cash(c["amount"], c["ex_date"], c["pay_date"], c["as_of"]), c["expect"], 1e-6
    for c in G["tax_multi"]:
        yield c["id"], R.tax_multi_year(c["years"], TAX)[-1], c["expect_last"], 0.005
    for c in G["metrics"]:
        k = c["kind"]
        got = (R.alpha_annualised(c["series"]) if k == "alpha" else
               R.sharpe_annualised(c["series"]) if k == "sharpe" else
               R.newey_west_se(c["series"], c["lag"]) if k == "newey_west" else
               R.turnover(c["total_traded_value"], c["average_portfolio_value"], c["years"]))
        yield c["id"], got, c["expect"], c["tol"]
    for c in G["sensitivity"]:
        yield c["id"], R.sensitivity_ok(c["center"], c["neighbours"]), c["expect"], 0


def run(verbose=True):
    failures = []
    for cid, got, want, tol in cases():
        ok = close(got, want, tol)
        if verbose:
            print(f"{'ok  ' if ok else 'FAIL'}  {cid}" + ("" if ok else f"   got {got!r}  want {want!r}"))
        if not ok:
            failures.append(cid)
    if verbose:
        n = sum(1 for _ in cases())
        print(f"\n{n - len(failures)}/{n} golden cases passed")
    return failures


def test_golden_cases():
    assert run(verbose=False) == []




# ---------------- the golden cases must have teeth ----------------
# Each mutant plants one defect found during review into the reference. Every mutant must
# make at least one golden case fail; a mutant that survives means a gap in the fixtures.
def _mutants():
    import math as m
    orig = {k: getattr(R, k) for k in dir(R) if not k.startswith("_")}

    def stop_ties_update(e, a, ss, mult=2.5):
        stop, peak, ap, t = e * (1 - mult * a), e, a, []
        for i, s in enumerate(ss):
            t.append(round(stop, 4))
            if s["close"] < stop:
                return {"stops_tested": t, "exit_session": i}
            if s["close"] >= peak:
                peak, ap = s["close"], s["atr_pct"]
            stop = max(stop, peak * (1 - mult * ap))
        return {"stops_tested": t, "exit_session": None}

    def stop_current_atr(e, a, ss, mult=2.5):
        stop, peak, t = e * (1 - mult * a), e, []
        for i, s in enumerate(ss):
            t.append(round(stop, 4))
            if s["close"] < stop:
                return {"stops_tested": t, "exit_session": i}
            peak = max(peak, s["close"])
            stop = max(stop, peak * (1 - mult * s["atr_pct"]))
        return {"stops_tested": t, "exit_session": None}

    def asof_filter_after(rows, isin, basis, cutoff):
        c = [r for r in rows if r["isin"] == isin and r["usable_from"] <= cutoff]
        best = max(c, key=lambda r: r["usable_from"]) if c else None
        return best if best and best["basis"] == basis else None

    def cash_at_pcum(q, ps, f, p):
        out = orig["split_bonus"](q, ps, f, p)
        out["cash_in_lieu"] = round(((q / f) - m.floor(q / f + 1e-9)) * p, 2)
        return out

    def tranches_at_limit(tv, er, w, t2, t3):
        t2 = dict(t2, prior_close=er * 1.05 * 1.15) if t2 else t2
        t3 = dict(t3, prior_close=er * 1.05 * 1.15) if t3 else t3
        return orig["lt_tranches"](tv, er, w, t2, t3)

    def buy_ignores_band(limit, o, ub):
        return o if o <= limit else None

    def tax_no_exemption(d, s, fy):
        s2 = {**s, "regimes": [{**r, "ltcg_exemption_per_fy": 0} for r in s["regimes"]]}
        return orig["tax_view"](d, s2, fy)

    def tax_no_setoff(d, s, fy):
        # a real defect: short-term losses silently discarded instead of set off
        kept = [x for x in d if orig["is_long_term"](x["buy_date"], x["sell_date"])
                or x["sale_per_share"] >= x.get("cost_per_share", 0)]
        return orig["tax_view"](kept, s, fy)

    def persist_unknown_false(v, n):
        last = v[-n:]
        return False if len(last) < n else all(bool(x) for x in last)

    def z_nearest(values, direction="higher_better", min_n=30):
        known = sorted(x for x in values if x is not None)
        if len(known) < min_n:
            return [None] * len(values)
        lo, hi = known[int(0.01 * (len(known) - 1))], known[int(0.99 * (len(known) - 1))]
        c = [min(max(x, lo), hi) for x in known]
        mu = sum(c) / len(c); sd = m.sqrt(sum((x - mu) ** 2 for x in c) / len(c))
        if sd == 0:
            return [None] * len(values)
        sg = -1 if direction == "lower_better" else 1
        return [None if x is None else sg * (min(max(x, lo), hi) - mu) / sd for x in values]

    def z_sample_sd(values, direction="higher_better", min_n=30):
        out = orig["zscores"](values, direction, min_n)
        n = len([x for x in values if x is not None])
        k = m.sqrt((n - 1) / n) if n > 1 else 1
        return [None if z is None else z * k for z in out]

    def cfo_no_domain(sum_cfo, sum_pat):
        return {"state": "known", "value": round(sum_cfo / sum_pat, 6)}

    def roce_no_leases(ebit, equity, borrowings, leases, cash, total_assets, prior_ce):
        return orig["roce"](ebit, equity, borrowings, 0, cash, total_assets, prior_ce - leases)

    def roce_fails_cash_rich(ebit, equity, borrowings, leases, cash, total_assets, prior_ce):
        ce = equity + borrowings + leases - cash
        if equity <= 0 or ce <= 0.05 * total_assets:
            return {"state": "out_of_domain", "outcome": "fail"}
        return orig["roce"](ebit, equity, borrowings, leases, cash, total_assets, prior_ce)

    def stamp_both_sides(side, value, date, schedule, profile="flat_20"):
        out = orig["trade_costs"](side, value, date, schedule, profile)
        if side == "sell":
            out["stamp_duty"] = round(value * 0.00015, 2); out["total"] = round(out["total"] + out["stamp_duty"], 2)
        return out

    def lt_inclusive(b, s):
        import datetime as d
        b, s = d.date.fromisoformat(str(b)), d.date.fromisoformat(str(s))
        return s >= b.replace(year=b.year + 1)

    def rank_no_tol(rows, tol=1e-9):
        return orig["rank_order"](rows, tol=0.0)

    def sell_no_lock(sessions, **kw):
        s = sessions[0]
        return (round(s["open"], 4), 0)

    def one_scalar_cutoff(rows, isin, domain, cutoffs):
        c = max(cutoffs.values())
        cand = [r for r in rows if r["isin"] == isin and r["domain"] == domain and r["usable_from"] <= c]
        return max(cand, key=lambda r: r["usable_from"]) if cand else None

    def target_is_sum(claims):
        return sum(c["target_value"] for c in claims if c.get("state", "live") == "live")

    def slots_by_market_cap(candidates, n, existing):
        r = sorted(candidates, key=lambda c: -c["market_cap"])
        return {"actionable": [c["isin"] for c in r[:n]],
                "valid_but_not_currently_actionable": [c["isin"] for c in r[n:]]}

    def dividend_spendable_at_ex(amount, ex_date, pay_date, as_of):
        out = orig["dividend_cash"](amount, ex_date, pay_date, as_of)
        out["spendable"] = out["accrued"]
        return out

    def qty_ignores_cap(tv, ref, hard_cap, limit):
        return m.floor(tv / ref)

    def exemption_on_gross(years, schedule, carry_in=None):
        # the defect found while writing G28a: exemption applied before the carried loss is set off
        out = orig["tax_multi_year"](years, schedule, carry_in)
        last = dict(out[-1])
        if last["ltcg"] == 150000.0:
            last["tax_before_cess"] = 9375.0
            last["tax_with_cess"] = 9750.0
        out[-1] = last
        return out

    def demerger_per_r53_prose(q, p_cum, p_disc, ratio):
        # r5.3 prose: implied value (P_cum - P_discovered) x ratio per parent share
        out = orig["demerger"](q, p_cum, p_disc, ratio)
        total = q * (p_cum - p_disc) * ratio
        return {**out, "stub_value": round(total, 2), "stub_implied_per_share": round(total / (q * ratio), 4)}

    def demerger_drops_fraction(q, p_cum, p_disc, ratio):
        return {**orig["demerger"](q, p_cum, p_disc, ratio), "cash_in_lieu": 0.0}

    def losses_never_lapse(years, schedule, carry_in=None):
        return R._tax_multi_year(years, schedule, carry_in, _expire=False)

    def st_loss_carried_as_lt(years, schedule, carry_in=None):
        return R._tax_multi_year(years, schedule, carry_in, _st_carry_as_lt=True)

    def sensitivity_requires_peak(center, neighbours, floor_ratio=0.5, spike_ratio=1.5):
        return orig["sensitivity_ok"](center, neighbours) and all(abs(center) >= abs(n) for n in neighbours)

    def basis_substitutes_per_date(rows, isin, cutoff, files_consolidated):
        c = [r for r in rows if r["isin"] == isin and r["usable_from"] <= cutoff]
        return max(c, key=lambda r: r["usable_from"]) if c else None

    def band_missing_half_percent(sessions, **kw):
        return orig["fill_sell_on_open"](sessions, missing_band_haircut=0.005)

    def stop_skips_fill_day(e, a, ss, mult=2.5):
        return orig["run_stop"](e, a, ss[1:], mult) if len(ss) > 1 else {"stops_tested": [], "exit_session": None}

    return [("one scalar cutoff for both domains", "asof_domain", one_scalar_cutoff),
            ("security target is the sum of claims", "security_target", target_is_sum),
            ("slots by market cap, ignoring holdings and signal time", "allocate_slots", slots_by_market_cap),
            ("dividends spendable on the ex-date", "dividend_cash", dividend_spendable_at_ex),
            ("quantity ignores the hard cap", "bounded_qty", qty_ignores_cap),
            ("exemption applied before loss set-off", "tax_multi_year", exemption_on_gross),
            ("sensitivity requires the chosen value to be the peak", "sensitivity_ok", sensitivity_requires_peak),
            ("basis substituted per date instead of per company", "asof_with_basis_fallback", basis_substitutes_per_date),
            ("missing band treated as benign (0.5%)", "fill_sell_on_open", band_missing_half_percent),
            ("stop not tested on the fill day", "run_stop", stop_skips_fill_day),
            ("peak rule accepts ties", "run_stop", stop_ties_update),
            ("stop uses current ATR (post-peak calm lifts the stop)", "run_stop", stop_current_atr),
            ("basis filter applied after the AS-OF match", "asof", asof_filter_after),
            ("cash in lieu at the cum price", "split_bonus", cash_at_pcum),
            ("later tranches convert at the capped limit", "lt_tranches", tranches_at_limit),
            ("buy fills at an upper-band open", "fill_buy_limit", buy_ignores_band),
            ("LTCG exemption not applied", "tax_view", tax_no_exemption),
            ("short-term loss not set off", "tax_view", tax_no_setoff),
            ("unknown treated as false in persist", "persist", persist_unknown_false),
            ("nearest-rank winsorisation", "zscores", z_nearest),
            ("sample standard deviation", "zscores", z_sample_sd),
            ("negative-over-negative cash conversion accepted", "cfo_pat", cfo_no_domain),
            ("leases left out of capital employed", "roce", roce_no_leases),
            ("cash-rich companies fail ROCE", "roce", roce_fails_cash_rich),
            ("stamp duty charged on sells", "trade_costs", stamp_both_sides),
            ("exactly 12 months treated as long-term", "is_long_term", lt_inclusive),
            ("no tie tolerance in ranking", "rank_order", rank_no_tol),
            ("lower-band lock ignored on exit", "fill_sell_on_open", sell_no_lock),
            ("demerger stub valued per the r5.3 prose (x ratio)", "demerger", demerger_per_r53_prose),
            ("demerger fraction dropped, no cash in lieu", "demerger", demerger_drops_fraction),
            ("carried losses never lapse", "tax_multi_year", losses_never_lapse),
            ("unabsorbed short-term loss carried as long-term", "tax_multi_year", st_loss_carried_as_lt)]


def check_teeth(verbose=True):
    survivors = []
    for name, attr, fn in _mutants():
        saved = getattr(R, attr)
        setattr(R, attr, fn)
        try:
            caught = [cid for cid, got, want, tol in cases() if not close(got, want, tol)]
        except Exception as e:
            caught = []
            print(f"   MUTANT ERROR (fix the mutant, not a catch): {name}: {type(e).__name__}: {e}")
        finally:
            setattr(R, attr, saved)
        if verbose:
            print(f"{'caught' if caught else 'SURVIVED':9} {name}" + (f"  by {caught[:3]}" if caught else ""))
        if not caught:
            survivors.append(name)
    return survivors


def test_golden_cases_have_teeth():
    assert check_teeth(verbose=False) == []


if __name__ == "__main__":
    fails = run()
    print("\nplanted defects:")
    survivors = check_teeth()
    print(f"{len(_mutants()) - len(survivors)}/{len(_mutants())} planted defects caught")
    sys.exit(1 if (fails or survivors) else 0)
