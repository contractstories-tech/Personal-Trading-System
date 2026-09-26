#!/usr/bin/env python3
"""End-to-end golden cases (golden/pipeline_cases.yaml) through reference_engine.run_pipeline: a population of
securities to the model portfolio and the published claims, using the cards' own expressions (r5.6). Planted
defects - each a behaviour r5.5 had, or a plausible slip - must each break at least one case.

    python3 test_pipeline.py      (exit 0 = all pass)
    python3 -m pytest -q
"""
import copy
import json
import math
import os
import sys
from decimal import Decimal

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reference_engine as E  # noqa: E402
from speclint import closure_sha256, lint, load_yaml  # noqa: E402

G = yaml.safe_load(open(os.path.join(HERE, "golden", "pipeline_cases.yaml"), encoding="utf-8"))["cases"]
REG = load_yaml(os.path.join(HERE, "registry.yaml"))
SCHEMA = json.load(open(os.path.join(HERE, "schemas", "card.schema.json"), encoding="utf-8"))
CARDS = {c: load_yaml(os.path.join(HERE, "strategies", f"{c}.yaml")) for c in ("ltqv_v1", "mom_v1")}

# Real, linter-valid card variants used only as regression fixtures. They exercise semantics the shipped reference
# cards do not currently use, without changing either strategy's hypothesis.
_gate = copy.deepcopy(CARDS["mom_v1"])
_gate["selection_method"] = "gate_only"
_gate.pop("ranking")
_gate["construction"].update(max_positions=2, capacity_order="earliest_signal")
_gate["registry"]["closure_sha256"] = closure_sha256(_gate, REG)
assert lint(_gate, REG, SCHEMA, "experimental") == []
assert "ranking" not in _gate
CARDS["mom_gate_only"] = _gate

_max1 = copy.deepcopy(CARDS["mom_v1"])
_max1["construction"]["max_positions"] = 1
_max1["registry"]["closure_sha256"] = closure_sha256(_max1, REG)
assert lint(_max1, REG, SCHEMA, "experimental") == []
CARDS["mom_max1"] = _max1


def _value(spec, i):
    if isinstance(spec, list):
        return Decimal(str(spec[0])) + Decimal(str(spec[1])) * i
    if isinstance(spec, dict) and "floor" in spec:
        a, b = spec["floor"]
        return int(math.floor(Decimal(str(a)) + Decimal(str(b)) * i))
    return spec


def population(case):
    by_id = {c["id"]: c for c in G}
    feats = case["features"] if "from" not in case["features"] else by_id[case["features"]["from"]]["features"]
    over = case["overrides"] if "from" not in case["overrides"] else by_id[case["overrides"]["from"]]["overrides"]
    pop = {}
    for i in range(1, case["names"] + 1):
        name = f"S{i:02d}"
        fs = {f: {"state": "known", "value": _value(v, i)} for f, v in feats.items()}
        o = dict(over.get(name, {}))
        sector, eligible = o.pop("_sector", "it_services"), o.pop("_eligible", True)
        fs.update({f: (dict(v) if isinstance(v, dict) else {"state": "known", "value": v}) for f, v in o.items()})
        pop[name] = {"features": fs, "sector": sector, "market_eligible": eligible, "market_cap": 1000 + i,
                     "close": case["close"], "signal_at": case.get("signal_at", {}).get(name)}
    return pop


def run_case(case):
    if "expect_error" in case:
        try:
            E.run_pipeline(CARDS[case["card"]], REG, case["params"], population(case), case["held"],
                           case["cash"], case["max_positions"] if "max_positions" in case else None)
        except ValueError as exc:
            return {"error": str(exc)}, {"error": case["expect_error"]}
        return {"error": None}, {"error": case["expect_error"]}
    out, entries = E.run_pipeline(CARDS[case["card"]], REG, case["params"], population(case), case["held"],
                                  case["cash"], case.get("max_positions"))
    want, got = case["expect"], {}
    if "entries" in want:
        got["entries"] = entries
    if "entry_count" in want:
        got["entry_count"], got["entry_qty"] = len(entries), sorted({q for _, q in entries})
        want = dict(want, entry_qty=[want["entry_qty"]])
    if "published" in want:
        got["published"] = sorted(i for i, r in out.items() if r.get("published"))
    if "tranche_1" in want:
        got["tranche_1"] = {i: out[i].get("tranche_1_qty") for i in want["tranche_1"]}
    groups = {}
    for i, r in out.items():
        groups.setdefault(r["status"], []).append(i)
    got["status"] = {s: sorted(groups.get(s, [])) for s in want["status"]}
    if "confidence" in want:
        got["confidence"] = {i: out[i].get("confidence") for i in want["confidence"]}
    return got, want


def run(verbose=True):
    fails = []
    for case in G:
        got, want = run_case(case)
        bad = {k: (got.get(k), v) for k, v in want.items() if got.get(k) != v}
        if bad:
            fails.append(case["id"])
            if verbose:
                for k, (g, w) in bad.items():
                    print(f"FAIL  {case['id']} {k}: got {g!r}\n                want {w!r}")
    if verbose:
        print(f"{len(G) - len(fails)}/{len(G)} pipeline golden cases passed")
    return fails


# ---------------- planted defects: r5.5 behaviours and plausible slips ----------------
def _patch(obj, name, make):
    orig = getattr(obj, name)
    setattr(obj, name, make(orig))
    return lambda: setattr(obj, name, orig)


def _r55_construct(orig):
    def construct(candidates, held, max_positions, cash, tol=1e-9, capacity_order="rank"):
        # Semantic reintroduction of the r5.5 defect, not a signature mismatch: unranked names are admitted last.
        ranked = [c for c in candidates if c["rank"] is not None]
        taken, rest = orig(ranked, held, max_positions, cash, tol, capacity_order=capacity_order)
        spare = max_positions - len(held) - len(taken)
        cash_left = cash - sum(v for _, v in taken)
        for c in sorted((c for c in candidates if c["rank"] is None), key=lambda c: (-c["market_cap"], c["isin"])):
            if spare > 0 and cash_left > 0:
                taken.append((c["isin"], min(c["target_value"], cash_left)))
                cash_left -= taken[-1][1]
                spare -= 1
        return taken, rest
    return construct


def _unrankable_as_rank_none(orig):
    def evaluate(self, features, composites=None, rank=E.NOT_GIVEN, in_candidates=True):
        r = orig(self, features, composites, 0 if rank is None else rank, in_candidates)
        return r                      # candidate as if ranked; the pipeline then passes rank None to construct
    return evaluate


def _both(*undos):
    return lambda: [u() for u in undos]


def _unrankable_is_candidate(orig):
    def evaluate(self, features, composites=None, rank=E.NOT_GIVEN, in_candidates=True):
        return orig(self, features, composites, 0 if rank is None else rank, in_candidates)
    return evaluate


def _r55_confidence(orig):
    def confidence(self, features):          # counted a conflicted penalised input twice; ignored others
        drops = sum(1 for f in self.card["features"] if self.unknown_behaviour(f) == "penalise"
                    and features.get(f, {"state": "missing"})["state"] != "known")
        drops += sum(1 for f in self.card["features"] if features.get(f, {}).get("state") == "conflicted"
                     and self.unknown_behaviour(f) == "penalise")
        band = E.BANDS[min(drops, len(E.BANDS) - 1)]
        return band, E.BANDS.index(band) <= E.BANDS.index(self.reg["confidence_policy"]["publish_minimum"])
    return confidence


def _conflicted_dropped_from_ranking(orig):
    def _rank_input(self, f, fs):
        if fs.get(f, {}).get("state") == "conflicted":
            return "none", f"{f} conflicted"
        return orig(self, f, fs)
    return _rank_input


def _no_size_checks(orig):
    def size_checks(self, features, provisional_value_cr):
        return {c["code"]: "PASS" for c in self.card.get("size_dependent_checks", [])}
    return size_checks


def _cap_ignores_allotment(orig):
    def quantities(self, runtime, prices, features=None):
        rt = dict(runtime, hard_cap_value=E.num(self.params["notional_capital"]) * E.num(self.params["max_position_pct"]))
        return orig(self, rt, prices, features)
    return quantities


def _unknown_filter_scored_out(orig):
    def filter_membership(self, features):
        a, b = orig(self, features)
        return (a, a) if not a else (a, b)
    return filter_membership


def _construct_forces_rank(orig):
    def construct(candidates, held, max_positions, cash, tol=1e-9, capacity_order="rank"):
        return orig(candidates, held, max_positions, cash, tol, capacity_order="rank")
    return construct


def _runtime_overrides_card(orig):
    def resolve(card, supplied):
        return supplied if supplied is not None else orig(card, supplied)
    return resolve


DEFECTS = [
    ("r5.5: unrankable is a candidate and construct admits it after the ranked names", lambda: _both(
        _patch(E.Engine, "evaluate", _unrankable_as_rank_none), _patch(E, "construct", _r55_construct))),
    ("an unrankable security treated as a candidate", lambda: _patch(E.Engine, "evaluate", _unrankable_is_candidate)),
    ("r5.5 confidence: double count / missed conflicted ranking input", lambda: _patch(E.Engine, "confidence", _r55_confidence)),
    ("conflicted ranking input makes the security unrankable", lambda: _patch(E.Engine, "_rank_input", _conflicted_dropped_from_ranking)),
    ("size-dependent checks skipped", lambda: _patch(E.Engine, "size_checks", _no_size_checks)),
    ("model hard cap ignores the cash allotted", lambda: _patch(E.Engine, "quantities", _cap_ignores_allotment)),
    ("an UNKNOWN filter also removes the security from the scoring population",
     lambda: _patch(E.Engine, "filter_membership", _unknown_filter_scored_out)),
    ("gate-only construction is forced back through rank ordering", lambda: _patch(E, "construct", _construct_forces_rank)),
    ("runtime max_positions silently overrides the card", lambda: _patch(E, "_resolve_max_positions", _runtime_overrides_card)),
]


def check_teeth(verbose=True):
    survivors = []
    for name, plant in DEFECTS:
        undo = plant()
        try:
            try:
                caught = run(verbose=False)
            except Exception as e:
                caught = [f"raised {type(e).__name__}"]
        finally:
            undo()
        if verbose:
            print(f"{'caught' if caught else 'SURVIVED':9} {name}" + (f"  by {caught[:3]}" if caught else ""))
        if not caught:
            survivors.append(name)
    return survivors


def test_pipeline_cases():
    assert run(verbose=False) == []


def test_pipeline_defects_are_caught():
    assert check_teeth(verbose=False) == []


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):   # UTF-8 output whatever the console or pipe (Windows defaults to cp1252)
        _s.reconfigure(encoding="utf-8")
    fails = run()
    print("planted defects:")
    surv = check_teeth()
    print(f"{len(DEFECTS) - len(surv)}/{len(DEFECTS)} planted defects caught")
    sys.exit(1 if fails or surv else 0)
