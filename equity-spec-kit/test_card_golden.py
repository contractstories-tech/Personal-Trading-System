#!/usr/bin/env python3
"""Card-level golden cases (golden/card_cases.yaml) through reference_engine.py, plus planted CARD edits that
must each break at least one case (audit A1). r5.4 had no way to notice a changed card.

    python3 test_card_golden.py      (exit 0 = all pass)
    python3 -m pytest -q
"""
import copy
import os
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reference_engine as E  # noqa: E402
from speclint import load_yaml  # noqa: E402
from test_golden import close  # noqa: E402

G = yaml.safe_load(open(os.path.join(HERE, "golden", "card_cases.yaml"), encoding="utf-8"))
REG = load_yaml(os.path.join(HERE, "registry.yaml"))
CARDS = {c: load_yaml(os.path.join(HERE, "strategies", f"{c}.yaml")) for c in ("ltqv_v1", "mom_v1")}


def variants(cards):
    """r5.10: card variants that exercise engine branches the shipped cards never use (engine mutation showed them
    unpinned). Each is derived from the cards under test, so a planted edit to a base card flows into its variants,
    and each must pass the linter: they are shapes a real card may take."""
    import json
    from speclint import closure_sha256, lint
    schema = json.load(open(os.path.join(HERE, "schemas", "card.schema.json"), encoding="utf-8"))
    out = {}
    v = copy.deepcopy(cards["ltqv_v1"])
    v["gates"].append({"code": "G10", "expr": "quality_composite >= 0", "unknown_blocks": True})
    out["ltqv_composite_gate"] = v
    v = copy.deepcopy(cards["ltqv_v1"])
    v["gates"].append({"code": "G10", "expr": "roce_stability >= 0.5", "unknown_blocks": False})
    out["ltqv_waivable_gate"] = v
    for name in ("ltqv_composite_gate", "ltqv_waivable_gate"):
        out[name]["proposed_execution_rule"]["tranches"][0]["recheck_gates"].append("G10")
    v = copy.deepcopy(cards["ltqv_v1"])
    v["ranking"]["expr"] = "0.5 * value_composite + 0.5 * z(market_cap)"
    out["ltqv_value_and_z"] = v
    for name, v in out.items():
        v["registry"]["closure_sha256"] = closure_sha256(v, REG)
        errs = lint(v, REG, schema, "experimental")
        assert not errs, f"variant {name} must be a valid card: {errs[:2]}"
    return out


def feats(d):
    return {k: (v if isinstance(v, dict) else {"state": "known", "value": v}) for k, v in (d or {}).items()}


def engine(card_code, cards, params=None):
    return E.Engine(cards[card_code], REG, params)


def _card(code, cards):
    return cards[code] if code in cards else variants(cards)[code]


def cases(cards):
    allc = dict(cards, **variants(cards))
    for c in G["gates"]:
        e = engine(c["card"], allc, c.get("params"))
        g = next(x for x in allc[c["card"]]["gates"] if x["code"] == c["gate"])
        yield c["id"], e.gate(g, feats(c["features"]), c.get("composites")), c["expect"]
    for c in G["exits"]:
        e = engine(c["card"], cards)
        x = dict(next(x for x in cards[c["card"]]["exit_rules"] if x["code"] == c["exit"]), **(c.get("override") or {}))
        units = {u: [feats(s) for s in snaps] for u, snaps in (c.get("units") or {}).items()}
        yield c["id"], e.exit(x, feats(c["features"]), units=units), c["expect"]
    for c in G["filters"]:
        yield c["id"], list(engine(c["card"], cards).filter_membership(feats(c["features"]))), c["expect"]
    for c in G["confidence"]:
        e = engine(c["card"], cards)
        f = {k: {"state": "known", "value": 1} for k in cards[c["card"]]["features"]}
        f.update({k: {"state": "missing"} for k in c.get("missing", [])})
        f.update({k: {"state": "conflicted", "value": 1} for k in c.get("conflicted", [])})
        yield c["id"], list(e.confidence(f)), c["expect"]
    for c in G["stops"]:
        yield c["id"], engine(c["card"], cards).run_stop(c["entry_fill"], c["atr_at_signal"], c["sessions"]), c["expect"]
    for c in G["quantities"]:
        e = engine(c["card"], cards, c.get("params"))
        if "t2" in c:
            prices = {("close", "signal_date"): c["entry_close"]}
            got = e.tranche_quantities({"target_value": c["target_value"], "hard_cap_value": c["hard_cap_value"]}, prices,
                                       c["t2"], c["t3"])
            got = {**got, "quantities": [int(q) for q in got["quantities"]]}
        else:
            q = e.quantities(c["runtime"], {("close", "signal_date"): c["prices"]["close_signal"]})
            got = {"target_qty": q["target_qty"], "cap_enforced": q["cap_enforced"]}
        yield c["id"], got, c["expect"]
    for c in G["size_checks"]:
        yield c["id"], engine(c["card"], cards).size_checks(feats(c["features"]), c["provisional_value_cr"]), c["expect"]
    for c in G["construction"]:
        try:
            taken, rest = E.construct(c["candidates"], set(c["held"]), c["max_positions"], c["cash"])
            got = {"taken": [[i, v] for i, v in taken], "not_taken": rest}
        except ValueError as e:
            got = {"error": str(e)}
        yield c["id"], got, c["expect"]
    for c in G["scale"]:
        yield c["id"], float(E.actual_target(c["target_value"], c["notional"], c["total"], c["headroom"])), c["expect"]
    for c in G["weekly"]:
        yield c["id"], E.weekly_sessions([tuple(x) for x in c["calendar"]], c["weekday"], REG), c["expect"]
    for c in G["ranking"]:
        e = engine(c["card"], cards)
        pop = {f"S{i:02d}" if i < 10 else f"S{i}": {"vol_adj_mom_12m": {"state": "known", "value": i},
                                                   "vol_adj_mom_6m": {"state": "known", "value": c["population"]["n"] + 1 - i}}
               for i in range(1, c["population"]["n"] + 1)}
        pop["SNONE"] = {}
        ranks = e.rank_scores(pop)
        order = sorted((i for i in ranks if ranks[i] is not None), key=lambda i: -ranks[i])
        yield c["id"], order[:3] + [ranks["SNONE"]], c["expect_top3"] + [None]
    for c in G["ranking_states"]:
        e = engine(c["card"], allc)
        detail = e.rank_detail(ranking_population(e, c["n"], c.get("overrides"), c.get("constant")))
        if "expect_rank" in c:
            yield c["id"], {i: float(detail[i]["rank"]) for i in c["expect_rank"]}, c["expect_rank"]
            continue
        if "expect_equal_rank" in c:
            name = c["expect_equal_rank"][0]
            twin = {k: {**v, "state": "known"} for k, v in c["overrides"][name].items()}
            twin_detail = e.rank_detail(ranking_population(e, c["n"], {name: twin}, c.get("constant")))
            yield c["id"], detail[name]["rank"], twin_detail[name]["rank"]
            continue
        got = {i: (None if detail[i]["rank"] is None else "ranked") for i in c["expect"]}
        got.update({f"{i} reason": detail[i]["reason"] for i in c.get("reason", {})})
        want = dict(c["expect"], **{f"{i} reason": r for i, r in c.get("reason", {}).items()})
        yield c["id"], got, want
    for c in G["evaluate"]:
        e = engine(c["card"], allc, c.get("params"))
        r = e.evaluate(feats(c["features"]), rank=c["rank"])
        yield c["id"], {"candidate": r["candidate"], "status": r["status"]}, c["expect"]
    for c in G["api"]:
        card = None
        if "card_edit" in c:
            card = copy.deepcopy(cards[c["card"]])
            for g in card["gates"]:
                g["expr"] = c["card_edit"].get(g["code"], g["expr"])
        e = E.load(c["card"], card=card) if card is not None else E.load(c["card"])
        g = next(x for x in e.card["gates"] if x["code"] == c["gate"])
        yield c["id"], e.gate(g, feats(c["features"])), c["expect"]


def ranking_population(e, n, overrides=None, constant=None):
    """Names S01..Sn; every ranking input of Si is i (known) unless `constant` fixes it for every name; then
    per-name state overrides."""
    pop = {f"S{i:02d}": {f: {"state": "known", "value": (constant or {}).get(f, i)} for f in e.ranking_inputs()}
           for i in range(1, n + 1)}
    for name, fs in (overrides or {}).items():
        pop[name].update(fs)
    return pop


def run(cards=CARDS, verbose=True):
    fails = []
    for cid, got, want in cases(cards):
        ok = close(got, want, 1e-6)
        if verbose and not ok:
            print(f"FAIL  {cid}   got {got!r}  want {want!r}")
        if not ok:
            fails.append(cid)
    if verbose:
        n = sum(1 for _ in cases(cards))
        print(f"{n - len(fails)}/{n} card golden cases passed")
    return fails


# ---------------- planted CARD edits (the audit's A1 demonstration, and others) ----------------
def _edit(code, path, fn):
    cards = copy.deepcopy(CARDS)
    node = cards[code]
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = fn(node[path[-1]])
    return cards


def _gate(code, g):
    return ["gates", [x["code"] for x in CARDS[code]["gates"]].index(g), "expr"]


def _exit(code, x):
    return ["exit_rules", [e["code"] for e in CARDS[code]["exit_rules"]].index(x), "expr"]


EDITS = [
    ("mom_v1 stop 2.5 -> 4.0 x ATR (initial and trail)",
     lambda: _edit("mom_v1", ["stop"], lambda st: {k: v.replace("2.5", "4.0") if isinstance(v, str) else v for k, v in st.items()})),
    ("ltqv_v1 G2 ROCE 15% -> 5%", lambda: _edit("ltqv_v1", _gate("ltqv_v1", "G2"), lambda s: s.replace("0.15", "0.05"))),
    ("ltqv_v1 G3 cash conversion 0.70 -> 0.10", lambda: _edit("ltqv_v1", _gate("ltqv_v1", "G3"), lambda s: s.replace("0.70", "0.10"))),
    ("mom_v1 G1 >= becomes >", lambda: _edit("mom_v1", _gate("mom_v1", "G1"), lambda s: s.replace(">=", ">"))),
    ("ltqv_v1 X4 OR becomes AND", lambda: _edit("ltqv_v1", _exit("ltqv_v1", "X4"), lambda s: s.replace(" OR ", " AND "))),
    ("mom_v1 X2 persist 3 -> 2 sessions", lambda: _edit("mom_v1", _exit("mom_v1", "X2"), lambda s: s.replace(", 3,", ", 2,"))),
    ("mom_v1 target_qty inner min() becomes max()",
     lambda: _edit("mom_v1", ["proposed_execution_rule", "target_qty"], lambda s: s.replace("min(floor(hard_cap", "max(floor(hard_cap"))),
    ("ltqv_v1 tranche-2 remainder clamp removed",
     lambda: _edit("ltqv_v1", ["proposed_execution_rule", "tranches", 1, "qty"], lambda s: "floor(tranche_weight * revised_target_qty)")),
    ("mom_v1 filter circuit days 5 -> 10", lambda: _edit("mom_v1", ["universe", "filters", 0], lambda s: s.replace("5", "10"))),
    ("mom_v1 S1 impact limit 0.35% -> 0.60%",
     lambda: _edit("mom_v1", ["size_dependent_checks", 0, "expr"], lambda s: s.replace("0.0035", "0.0060"))),
    ("mom_v1 ranking weights swapped to 6-month",
     lambda: _edit("mom_v1", ["ranking", "expr"], lambda s: "0.60 * z(vol_adj_mom_6m) - 0.40 * z(vol_adj_mom_12m)")),
    ("ltqv_v1 G5 unknown override fail -> exclude",
     lambda: _edit("ltqv_v1", ["unknown_overrides", "promoter_pledge_pct"], lambda s: "exclude")),
]


def check_teeth(verbose=True):
    survivors = []
    for name, make in EDITS:
        try:
            caught = run(make(), verbose=False)
        except Exception as e:
            caught = []
            print(f"   EDIT ERROR (fix the edit): {name}: {type(e).__name__}: {e}")
        if verbose:
            print(f"{'caught' if caught else 'SURVIVED':9} {name}" + (f"  by {caught[:3]}" if caught else ""))
        if not caught:
            survivors.append(name)
    return survivors


def engine_enforces_the_cap_whatever_the_card_says():
    """Belt and braces for audit B2: even an (unlintable) card whose quantity ignores the cap is clamped."""
    card = copy.deepcopy(CARDS["mom_v1"])
    card["proposed_execution_rule"]["target_qty"] = "floor(target_value / entry_ref)"
    e = E.Engine(card, REG, {"notional_capital": 10000000, "risk_to_stop_pct": 0.005, "max_position_pct": 0.05})
    q = e.quantities({"atr_pct_at_signal": 0.02, "hard_cap_value": 100000}, {("close", "signal_date"): 100})
    return q["target_qty"] == 970 and q["cap_enforced"]          # floor(100000 / 103) = 970


def test_engine_cap_invariant():
    assert engine_enforces_the_cap_whatever_the_card_says()


def test_card_golden_cases():
    assert run(verbose=False) == []


def test_card_edits_are_caught():
    assert check_teeth(verbose=False) == []


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):   # UTF-8 output whatever the console or pipe (Windows defaults to cp1252)
        _s.reconfigure(encoding="utf-8")
    fails = run()
    cap_ok = engine_enforces_the_cap_whatever_the_card_says()
    print(f"{'ok  ' if cap_ok else 'FAIL'}  engine clamps a quantity that ignores the hard cap")
    fails += [] if cap_ok else ["engine cap invariant"]
    print("planted card edits:")
    surv = check_teeth()
    print(f"{len(EDITS) - len(surv)}/{len(EDITS)} planted card edits caught")
    sys.exit(1 if (fails or surv) else 0)
