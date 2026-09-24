#!/usr/bin/env python3
"""Regression suite for speclint v4. Every defect found in any review round is a case here.

Run either way:
    python3 test_speclint.py        (prints each case; exit 0 = all pass)
    python3 -m pytest -q            (discovers test_* functions)

Each case mutates a known-good card and asserts the linter FAILS it with a violation that
contains the expected fragment, so a case cannot pass by accident on an unrelated error.
"""
import copy
import shutil, hashlib, io, json, os, sys
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from speclint import lint, load_yaml, sha256_file, StrictLoader, lint_paths, closure_sha256  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REG_PATH = os.path.join(HERE, "registry.yaml")
REG = load_yaml(REG_PATH)
REG_SHA = sha256_file(REG_PATH)
SCHEMA = json.load(open(os.path.join(HERE, "schemas", "card.schema.json"), encoding="utf-8"))
A = load_yaml(os.path.join(HERE, "strategies", "ltqv_v1.yaml"))
B = load_yaml(os.path.join(HERE, "strategies", "mom_v1.yaml"))


def at(c, path):
    for k in path:
        c = c[k]
    return c


def setp(path, value):
    return lambda c: at(c, path[:-1]).__setitem__(path[-1], value)


def pop(path):
    return lambda c: at(c, path[:-1]).pop(path[-1])


def app(path, value):
    return lambda c: at(c, path).append(value)


def status(st):
    """Status is not a card field (r5.5): the case supplies the lifecycle status the card is linted at."""
    return lambda c: c.__setitem__("__status__", st)


def seq(*fns):
    def f(c):
        for fn in fns:
            fn(c)
    return f


T1 = ["proposed_execution_rule", "tranches", 0]
T2 = ["proposed_execution_rule", "tranches", 1]

CASES = [
    # ---------------- rounds r2-r3 (original twelve) ----------------
    ("r2 sign bug: composite input without direction", A,
     pop(["composites", "value_composite", "inputs", 1, "direction"]), "direction"),
    ("r3 prose inside a rule", A, setp(["exit_rules", 0, "expr"], "roce_hy_ttm < 0.12 for 2 consecutive half-years"), "X1"),
    ("retired atr_20", B, setp(["stop", "initial"], "entry_basis * (1 - 2.5 * atr_20)"), "atr_20"),
    ("undeclared feature in a gate", B, app(["gates"], {"code": "G9", "expr": "roce_3y_avg > 0", "unknown_blocks": True}), "not declared"),
    ("research_only feature in sizing", B, setp(["sizing", "formula"], "notional_capital * market_breadth"), "research_only"),
    ("gate without unknown_blocks", A, pop(["gates", 0, "unknown_blocks"]), "unknown_blocks"),
    ("ambiguous sizing name", A, setp(["sizing", "method"], "volatility_target"), "sizing.method"),
    ("price-index benchmark", B, setp(["benchmark"], "NIFTY_200_MOMENTUM_30"), "benchmark"),
    ("validation methodology inside card", A, setp(["validation", "refit"], "annual"), "unknown field 'refit'"),
    ("order language", A, setp(["proposed_execution_rule", "order_type"], "buy_limit"), "unknown field 'order_type'"),
    ("corporate-action policy missing", B, pop(["corporate_action_policy"]), "corporate_action_policy"),
    ("identifier typo", A, setp(["gates", 1, "expr"], "roce_3y_avgg >= 0.15"), "roce_3y_avgg"),
    # ---------------- round r4 (index 14) ----------------
    ("research_only hidden inside a composite", A,
     seq(app(["features"], "market_breadth"),
         app(["composites", "consistency_composite", "inputs"], {"code": "market_breadth", "direction": "higher_better"})),
     "research_only"),
    ("duplicate gate code", A, lambda c: c["gates"].append(dict(c["gates"][0])), "duplicate code"),
    ("duplicate exit code", B, lambda c: c["exit_rules"].append(dict(c["exit_rules"][0])), "duplicate code"),
    ("recheck_gates references G99", A, setp(T2 + ["recheck_gates"], ["G99"]), "G99"),
    ("cooldown applies_after X99", A, setp(["cooldown", "applies_after"], ["X99"]), "X99"),
    ("unregistered void event", A, setp(["signal_void_on"], ["full_moon"]), "full_moon"),
    ("wrong function arity", B, setp(["exit_rules", 1, "expr"], "persist(price_vs_dma50 < 1.0)"), "takes 3 args"),
    ("tranche weights above 1", A, setp(T1 + ["weight"], 0.9), "weights sum"),
    ("made-up benchmark", B, setp(["benchmark"], "BANANA_TRI"), "BANANA_TRI"),
    ("invalid CA state field", A, app(["ca_state_held"], "nonsense_level"), "nonsense_level"),
    # ---------------- round r4.1 (indices 14-16) ----------------
    ("close_raw used as a scalar", B, setp(["exit_rules", 0, "expr"], "close_raw < stop_in_force"), "without arguments"),
    ("prose attempt policy", A, setp(T1 + ["attempt_policy"], "every session until expiry"), "attempt_policy"),
    ("tranche quantity not integer", A, setp(T2 + ["qty"], "tranche_weight * revised_target_qty"), "qty"),
    ("tranche 1 without a qty", A, pop(T1 + ["qty"]), "qty"),
    ("earmark quantity not held", B, lambda c: c["ca_state_held"].remove("current_earmark_qty"), "current_earmark_qty"),
    ("CA-sensitive state not held", B, lambda c: c["ca_state_held"].remove("highest_close_since_entry"), "highest_close_since_entry"),
    ("rewrites the immutable fill", B, setp(["stop", "initial"], "entry_fill * (1 - 2.5 * atr_pct_20)"), "entry_fill"),
    ("stop evaluation order unstated", B, pop(["stop", "evaluation_order"]), "evaluation_order"),
    ("exit cadence dropped (r4 X3 regression)", B, pop(["exit_rules", 2, "cadence"]), "cadence"),
    ("CALIBRATE left at shadow", B, status("shadow"), "CALIBRATE"),
    ("TTL without a unit", A, setp(["lifecycle", "signal_ttl"], {"value": 30}), "unit"),
    ("enum compared with a number", A, setp(["gates", 7, "expr"], "surveillance_stage >= 2"), "compare"),
    ("boolean gate that is really a number", A, setp(["gates", 1, "expr"], "roce_3y_avg * 2"), "boolean"),
    ("sizing param from the wrong method", A, setp(["sizing", "params", "risk_to_stop_pct"], "OPEN"), "do not belong"),
    ("min_inputs_known larger than inputs", A, setp(["composites", "value_composite", "min_inputs_known"], 7), "min_inputs_known"),
    # ---------------- round r4.1 review (index 17) ----------------
    ("revised_formula removed but revised value used", A, pop(["sizing", "revised_formula"]), "never assigned"),
    ("revised_target_qty definition removed", A, pop(["proposed_execution_rule", "revised_target_qty"]), "never assigned"),
    ("negative TTL", A, setp(["lifecycle", "signal_ttl", "value"], -5), "minimum"),
    ("negative cooldown", A, setp(["cooldown", "trading_days"], -3), "minimum"),
    ("negative retry window", A, setp(T2 + ["retry_sessions"], -1), "minimum"),
    ("persist count 2.5", A, setp(["exit_rules", 0, "expr"], "persist(roce_hy_ttm < 0.12, 2.5, persist_unit.half_year)"), "expected qty"),
    ("evaluation schedule removed", B, pop(["evaluation"]), "evaluation"),
    ("revised_formula as prose", A, setp(["sizing", "revised_formula"], "same_formula_at_tranche_date"), "unresolved identifier"),
    # ---------------- rounds 20, 22 and the audit ----------------
    ("production with OPEN sizing", A, status("production"), "OPEN"),
    ("unknown executable-looking section", A, setp(["execution"], {"broker": "place_order"}), "unknown field 'execution'"),
    ("invalid universe base", A, setp(["universe", "base"], "whole_world"), "universe.base"),
    ("invented sector code", A, app(["universe", "exclude_sectors"], "bananas"), "bananas"),
    ("wrong weekday", B, setp(["evaluation", "entry_triggers", 0, "weekday"], "sun"), "weekday"),
    ("trigger not allowed for class", A, setp(["evaluation", "entry_triggers", 0, "trigger"], "continuous_session"), "not allowed"),
    ("empty hypothesis", A, setp(["hypothesis"], ""), "hypothesis"),
    ("version 'latest'", A, setp(["version"], "latest"), "version"),
    ("offsetting negative weights", A,
     lambda c: [at(c, ["proposed_execution_rule", "tranches", i]).__setitem__("weight", w) for i, w in enumerate([1.5, -0.5, 0.0])],
     "weight"),
    ("holdout longer than evaluable history", A, setp(["validation", "holdout_years"], 20), "holdout_years"),
    ("momentum stop removed while exit tests it", B, pop(["stop"]), "no stop"),
    ("dead stop: no exit tests it", B, setp(["exit_rules", 0, "expr"], "holding_days >= 999"), "dead stop"),
    ("malformed shape: list replaced by number", B, setp(["size_dependent_checks"], 3.14), "must be array"),
    ("tranche-1 recheck removed", A, setp(T1 + ["recheck_gates"], ["G1"]), "every gate"),
    ("recheck_gates missing entirely", A, pop(T1 + ["recheck_gates"]), "recheck_gates"),
    ("recheck failure behaviour missing", A, pop(T2 + ["recheck_failure"]), "recheck_failure"),
    ("retirement as free prose", A, setp(["retirement"], {"rule": "stop when it feels wrong"}), "retirement"),
    ("arbitrary strategy class", A, setp(["strategy_class"], "vibes"), "strategy_class"),
    ("registry closure mismatch", A, setp(["registry", "closure_sha256"], "0" * 64), "closure_sha256"),
    ("registry major version mismatch", A, setp(["registry", "version"], "2.2.0"), "registry.version"),
    ("bare enum literal", A, setp(["gates", 7, "expr"], "surveillance_stage == none"), "namespaced"),
    ("enum value from the wrong enum", A, setp(["gates", 7, "expr"], "surveillance_stage == surveillance_stage.session"), "not a value"),
    ("gate_only with a ranking", A, setp(["selection_method"], "gate_only"), "gate_only"),
    ("rank_and_gate without ranking", B, pop(["ranking"]), "requires ranking"),
    ("unimplemented data resolution above experimental", A,
     seq(status("shadow"), setp(["strategy_class"], "intraday"), setp(["data_resolution"], "intraday_1m")), "not implemented"),
    ("calibration without declared quantile", B, pop(["params", "band_fno", "calibration", "q"]), "q"),
    ("calibration on the holdout", B, setp(["params", "band_fno", "calibration", "period"], "all"), "period"),
    ("AI inputs declared but not permitted", A, setp(["ai_inputs"], {"permitted": False, "declared_features": ["roce_3y_avg"]}), "ai_inputs"),
    ("retired auditor_event_5y", A, setp(["gates", 5, "expr"], "auditor_event_5y == false"), "auditor_event_5y"),
    ("sleeve terminology", A, setp(["sizing", "params"], {"sleeve_capital": "OPEN", "target_vol_contribution": "OPEN", "max_position_pct": "OPEN"}), "sleeve_capital"),
    ("NaN threshold", A, setp(["retirement", "threshold"], float("nan")), "number"),
    ("boolean where integer expected", A, setp(["cooldown", "trading_days"], True), "integer"),
    ("scope not simulation-only", A, setp(["proposed_execution_rule", "scope"], "live_orders"), "scope"),
    ("penalise on a material input", A, setp(["unknown_overrides", "cfo_pat_3y"], "penalise"), "material"),
    ("waivable gate reading a material input", A,
     seq(setp(["gates", 2, "unknown_blocks"], False)), "material input"),
    ("target_qty not bounded by the hard cap", A,
     setp(["proposed_execution_rule", "target_qty"], "floor(target_value / entry_ref)"), "hard_cap_value"),
    ("revised_target_qty not bounded by the hard cap", A,
     setp(["proposed_execution_rule", "revised_target_qty"], "floor(revised_target_value / entry_ref)"), "hard_cap_value"),
    ("code does not belong to its lineage", A, setp(["lineage", "code"], "momentum"), "lineage"),
    ("lineage missing", A, pop(["lineage"]), "lineage"),
    ("retired as_of_ts-style single cutoff identifier", A,
     setp(["gates", 1, "expr"], "roce_3y_avg >= 0.15 AND as_of_ts > 0"), "unresolved identifier"),
    # ---------------- r5.5: the independent audit of r5.4 (each accepted by the r5.4 linter) ----------------
    ("B2 undefined 'substitute' on a material input", A, setp(["unknown_overrides", "roce_3y_avg"], "substitute"), "substitute"),
    ("B2 'substitute' on momentum's blocking delivery input", B,
     setp(["unknown_overrides", "delivery_pct_20d_avg"], "substitute"), "substitute"),
    ("B2 waivable gate reading material inputs through a composite", A,
     seq(app(["gates"], {"code": "G10", "expr": "quality_composite > 0", "unknown_blocks": False}),
         app(T1 + ["recheck_gates"], "G10")), "material input"),
    ("B2 hard cap written as max(): a floor, not a ceiling", B,
     setp(["proposed_execution_rule", "target_qty"], "max(floor(target_value / entry_ref), floor(hard_cap_value / entry_high))"),
     "hard_cap_value"),
    ("B2 hard cap mentioned but ignored", A,
     setp(["proposed_execution_rule", "target_qty"], "floor(target_value / entry_ref) + floor(0 * hard_cap_value)"), "hard_cap_value"),
    ("B2 hard cap at the reference price, not the worst fill", A,
     setp(["proposed_execution_rule", "target_qty"], "min(floor(target_value / entry_ref), floor(hard_cap_value / entry_ref))"),
     "hard_cap_value"),
    ("B2 entry price read from the next session", B,
     setp(["proposed_execution_rule", "entry_ref"], "close_raw(next_executable_session(signal_date))"), "next_executable_session"),
    ("B2 gate reads a price two sessions back through nesting", B,
     setp(["gates", 2, "expr"], "close_raw(prev_session(prev_session(eval_date))) > 0"), "not permitted"),
    ("B2 open_raw of a non-evaluation date", B, setp(["exit_rules", 0, "expr"], "open_raw(entry_basis) < stop_in_force"), "open_raw"),
    ("A2 weekly exit without a weekday", B, pop(["exit_rules", 2, "weekday"]), "weekday"),
    ("A2 daily exit with a weekday", B, setp(["exit_rules", 1, "weekday"], "fri"), "daily exit"),
    ("A2 invalid on_out_of_domain", A, setp(["exit_rules", 0, "on_out_of_domain"], "ignore"), "on_out_of_domain"),
    ("A3 construction missing", A, pop(["construction"]), "construction"),
    ("A3 rank_and_gate card filling capacity by earliest signal", B,
     setp(["construction", "capacity_order"], "earliest_signal"), "rank"),
    ("A3 max_positions OPEN at shadow", B,
     seq(status("shadow"), setp(["params", "band_fno", "value"], 0.3), setp(["params", "band_cash", "value"], 0.4),
         setp(["sizing", "params"], {"notional_capital": 1e7, "risk_to_stop_pct": 0.005, "max_position_pct": 0.05})),
     "max_positions"),
    ("B7 status written into the card", A, setp(["status"], "production"), "unknown field 'status'"),
    ("A4 lineage deriving from itself", A, setp(["lineage", "derived_from"], ["ltqv"]), "itself"),
    ("C9 governance void event without its threshold", A, pop(["void_parameters"]), "void_parameters"),
    ("C9 void parameter for an unused event", B, setp(["void_parameters"], {"governance_event": {"promoter_pledge_pct": 0.2}}),
     "does not use"),
    ("B8 calibration sampling unstated", B, pop(["params", "band_fno", "calibration", "sampling"]), "sampling"),
    ("H9 cutoff timestamp compared with a number", A,
     setp(["gates", 1, "expr"], "roce_3y_avg >= 0.15 AND disclosure_cutoff_ts > 0"), "compare"),
]


def check_case(name, card, fn, frag):
    c = copy.deepcopy(card)
    fn(c)
    st = c.pop("__status__", "experimental")
    errs = lint(c, REG, SCHEMA, st)
    return bool(errs) and any(frag in e for e in errs), errs


def run(verbose=True):
    failures = []
    for name, card, fn, frag in CASES:
        ok, errs = check_case(name, card, fn, frag)
        if verbose:
            print(f"{'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"   -> {errs[:2]}"))
        if not ok:
            failures.append(name)
    extra = [("placeholder function blocked above experimental (registry copy)", _placeholder_blocked()),
             ("lifecycle, portfolio and run-manifest schemas enforce their rules", _other_schemas_enforce_their_rules()),
             ("impossible dates and times rejected, real ones accepted", _formats_are_real()),
             ("duplicate YAML key rejected", _dup_yaml_rejected()),
             ("duplicate strategy code across cards rejected", _dup_code_rejected()),
             ("A4 unrelated registry edits leave card pins intact; used-entry edits break them", _closure_is_scoped()),
             ("B7 lifecycle records validate, chain, and give each card its status", _lifecycle_records()),
             ("register_card.py stamps the real time and refuses a future or offset-less --at", _register_card_refuses_bad_times()),
             ("real card ltqv_v1 passes", not lint(A, REG, SCHEMA)),
             ("real card mom_v1 passes", not lint(B, REG, SCHEMA))]
    for name, ok in extra:
        if verbose:
            print(f"{'ok  ' if ok else 'FAIL'}  {name}")
        if not ok:
            failures.append(name)
    total = len(CASES) + len(extra)
    if verbose:
        print(f"\n{total - len(failures)}/{total} passed")
    return failures


def _placeholder_blocked():
    reg = copy.deepcopy(REG)
    reg["functions"]["impact_cost"]["status"] = "placeholder"
    c = copy.deepcopy(B)
    c["params"]["band_fno"]["value"], c["params"]["band_cash"]["value"] = 0.25, 0.45
    c["sizing"]["params"].update({"notional_capital": 1e6, "risk_to_stop_pct": 0.005, "max_position_pct": 0.05})
    c["construction"]["max_positions"] = 20
    # the closure pin now differs as well; the placeholder rule must still fire on its own
    errs = lint(c, reg, SCHEMA, "production")
    return any("placeholder" in e for e in errs)


def _closure_is_scoped():
    """Audit A4: r5.4 pinned the whole registry file, so any edit re-versioned every card and, under the
    'changed card needs fresh holdout' rule, would have burned every holdout. Review of r5.5: the closure still
    held every field enum and valuation_transformative_actions, so adding a weekday re-pinned both cards."""
    same = lambda reg, card: closure_sha256(card, reg) == closure_sha256(card, REG)  # noqa: E731
    reg = copy.deepcopy(REG)
    reg["features"]["brand_new_swing_feature"] = {"version": "1.0.0", "type": "num", "series": "raw", "cadence": "daily",
                                                  "default_unknown": "exclude", "formula": "for another strategy"}
    reg["sector_codes"].append("space_tourism")
    reg["deprecated"].append("some_old_name")
    unrelated_ok = same(reg, A) and same(reg, B)
    reg2 = copy.deepcopy(REG)
    reg2["features"]["roce_3y_avg"]["formula"] += " (edited)"
    ltqv_only = not same(reg2, A) and same(reg2, B)
    reg3 = copy.deepcopy(REG)
    reg3["evaluation_semantics"]["exits"] += " (edited)"
    semantics_break_both = not same(reg3, A) and not same(reg3, B)
    # field-value enums: a new value cannot change what an existing card means
    reg4 = copy.deepcopy(REG)
    reg4["enums"]["weekday"].append("sat")
    reg4["enums"]["horizon"].append("decades")
    reg4["enums"]["status"].append("archived")
    field_enums_ok = same(reg4, A) and same(reg4, B)
    # a block read by one card's feature (ey_median_5y depends_on valuation_transformative_actions)
    reg5 = copy.deepcopy(REG)
    reg5["valuation_transformative_actions"]["actions"].append("rights_issue")
    vta_ltqv_only = not same(reg5, A) and same(reg5, B)
    # an enum both cards compare against (surveillance_stage.none) changes both
    reg6 = copy.deepcopy(REG)
    reg6["enums"]["surveillance_stage"].append("esm_stage_1")
    stage_both = not same(reg6, A) and not same(reg6, B)
    # scoring rules reach ranking cards only; muhurat policy reaches every card
    reg7 = copy.deepcopy(REG)
    reg7["cross_sectional_scoring"]["min_contributors"] = 40
    gate_only = copy.deepcopy(B)
    gate_only["selection_method"], gate_only["ranking"] = "gate_only", None
    del gate_only["ranking"]
    scoring_scoped = not same(reg7, A) and not same(reg7, B) and same(reg7, gate_only)
    reg8 = copy.deepcopy(REG)
    reg8["session_policy"]["executable_session_types"].append("muhurat")
    session_both = not same(reg8, A) and not same(reg8, B)
    checks = dict(unrelated_ok=unrelated_ok, ltqv_only=ltqv_only, semantics_break_both=semantics_break_both,
                  field_enums_ok=field_enums_ok, vta_ltqv_only=vta_ltqv_only, stage_both=stage_both,
                  scoring_scoped=scoring_scoped, session_both=session_both)
    if not all(checks.values()):
        print("   closure scope:", {k: v for k, v in checks.items() if not v})
    return all(checks.values())


def _rec(n, at, frm="none", to="experimental", code="mom_v1", sha="a" * 64):
    return {"transition_id": f"{n:04d}", "strategy_code": code, "lineage": "mom", "card_sha256": sha,
            "from_status": frm, "to_status": to, "decided_by": "t", "decided_at": at, "reason": "regression case",
            "evidence": {}, "_file": f"{n:04d}-{code}.json"}


def _lifecycle_records():
    """B7 and the review of r5.5: records order by the instant decided, not the string; ties, future times,
    missing offsets and out-of-file-order records are reported; the shipped records give each card its status."""
    import datetime as _dt
    from speclint import load_transitions, lifecycle_status
    recs, errs = load_transitions(os.path.join(HERE, "lifecycle"))
    if errs:
        print("   lifecycle record errors:", errs[:3])
        return False
    shipped = all(lifecycle_status(c, sha256_file(os.path.join(HERE, "strategies", f"{c}.yaml")), recs)[0:3:2] ==
                  ("experimental", []) for c in ("ltqv_v1", "mom_v1"))
    now = _dt.datetime(2026, 9, 24, 14, 0, tzinfo=_dt.timezone.utc)
    st = lambda rs: lifecycle_status("mom_v1", "a" * 64, rs, now=now)  # noqa: E731
    # 18:00+05:30 is 12:30Z, BEFORE 13:00Z although its string sorts after: the chain is none->experimental->shadow
    mixed = [_rec(1, "2026-09-24T18:00:00+05:30"), _rec(2, "2026-09-24T13:00:00Z", "experimental", "shadow")]
    by_instant = st(mixed)[0] == "shadow" and st(mixed)[2] == []
    # string order would have put 0002 first and reported a broken chain; the reverse filing is itself reported
    swapped = [_rec(1, "2026-09-24T13:00:00Z"), _rec(2, "2026-09-24T18:00:00+05:30", "experimental", "shadow")]
    misfiled = any("filed before" in p for p in st(swapped)[2])
    tie = any("same instant" in p for p in st([_rec(1, "2026-09-24T13:00:00Z"),
                                               _rec(2, "2026-09-24T18:30:00+05:30", "experimental", "shadow")])[2])
    future = any("future" in p for p in st([_rec(1, "2026-09-24T14:06:00Z")])[2])
    near_now_ok = st([_rec(1, "2026-09-24T14:04:00Z")])[2] == []
    naive = any("offset" in p for p in st([_rec(1, "2026-09-24T13:00:00")])[2])
    broken = bool(st([_rec(1, "2026-09-01T10:00:00+05:30", "experimental", "shadow")])[2])
    checks = dict(shipped=shipped, by_instant=by_instant, misfiled=misfiled, tie=tie, future=future,
                  near_now_ok=near_now_ok, naive=naive, broken=broken)
    if not all(checks.values()):
        print("   lifecycle:", {k: v for k, v in checks.items() if not v})
    return all(checks.values())


def _register_card_refuses_bad_times():
    """register_card.py stamps the real time by default and refuses a future or offset-less --at."""
    import subprocess
    import tempfile
    d = tempfile.mkdtemp()
    try:
        k = os.path.join(d, "k")
        shutil.copytree(HERE, k, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "run_all.log"))
        os.makedirs(os.path.join(k, "lifecycle", "transitions"), exist_ok=True)
        for f in os.listdir(os.path.join(k, "lifecycle", "transitions")):
            os.remove(os.path.join(k, "lifecycle", "transitions", f))
        run = lambda *extra: subprocess.run([sys.executable, "register_card.py", "strategies/mom_v1.yaml", "--by", "t",  # noqa: E731
                                             "--reason", "regression case"] + list(extra), cwd=k, capture_output=True,
                                            text=True, encoding="utf-8")
        future = run("--at", "2099-01-01T10:00:00+05:30")
        naive = run("--at", "2026-09-24T10:00:00")
        ok = run()
        recs = os.listdir(os.path.join(k, "lifecycle", "transitions"))
        return future.returncode != 0 and naive.returncode != 0 and ok.returncode == 0 and len(recs) == 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _formats_are_real():
    """Review H8: '2026-99-99' and '99:99' matched the old regex-only format checks."""
    from speclint import schema_errors
    d, t = {"type": "string", "format": "date"}, {"type": "string", "format": "date-time"}
    bad = [schema_errors("2026-99-99", d, d), schema_errors("2026-02-30", d, d),
           schema_errors("2026-01-01T99:99:00+05:30", t, t), schema_errors("2026-13-01T10:00:00Z", t, t)]
    good = [schema_errors("2024-02-29", d, d), schema_errors("2026-09-24T20:00:00+05:30", t, t),
            schema_errors("2026-09-24T14:30:00Z", t, t)]
    return all(bad) and not any(good)


def _other_schemas_enforce_their_rules():
    """The lifecycle, portfolio and run-manifest schemas must reject what their prose forbids."""
    import datetime as _dt
    sch = lambda n: json.load(open(os.path.join(HERE, "schemas", n), encoding="utf-8"))
    from speclint import schema_errors
    h, ts = "a" * 64, "2026-09-21T20:00:00+05:30"
    life = sch("strategy_lifecycle_transition.schema.json")
    decl = {"derived_from": [], "sealed_results_seen": []}
    base = {"transition_id": "t", "strategy_code": "ltqv_v1", "lineage": "ltqv", "card_sha256": h,
            "from_status": "none", "to_status": "experimental", "decided_by": "harsh",
            "decided_at": ts, "reason": "initial registration of the card",
            "evidence": {"linter_report_sha256": h, "holdout_exposure_declaration": decl}}
    checks = [
        ("none->production rejected", bool(schema_errors({**base, "to_status": "production"}, life, life))),
        ("none->experimental accepted", not schema_errors(base, life, life)),
        # audit A4: registration must declare inherited holdout exposure
        ("none->experimental without a holdout-exposure declaration rejected",
         bool(schema_errors({**base, "evidence": {"linter_report_sha256": h}}, life, life))),
        ("experimental->shadow without a validation report rejected",
         bool(schema_errors({**base, "from_status": "experimental", "to_status": "shadow",
                             "evidence": {"backtest_run_ids": ["r"], "holdout_run_id": "h",
                                          "holdout_ledger_entry_id": "e", "golden_case_report_sha256": h,
                                          "linter_report_sha256": h}}, life, life))),
        # review H2: production -> retired needs the retirement metric or data fault, like -> suspended
        ("production->retired with empty evidence rejected",
         bool(schema_errors({**base, "from_status": "production", "to_status": "retired", "evidence": {}}, life, life))),
        ("production->retired with a retirement-metric breach accepted",
         not schema_errors({**base, "from_status": "production", "to_status": "retired",
                            "evidence": {"retirement_metric_breach": "rolling_alpha"}}, life, life)),
        ("production->suspended with empty evidence rejected",
         bool(schema_errors({**base, "from_status": "production", "to_status": "suspended", "evidence": {}}, life, life))),
    ]
    pol = sch("portfolio_policy.schema.json")
    p = yaml.safe_load(open(os.path.join(HERE, "portfolio_policy.yaml"), encoding="utf-8"))
    p2 = copy.deepcopy(p); p2["caps"]["per_stock_pct"] = 5.0
    p3 = copy.deepcopy(p); p3["caps"]["max_open_positions"] = 1.5
    p4 = copy.deepcopy(p); p4["slot_priority"] = ["earliest_signal", "earliest_signal"]
    checks += [("500% per-stock cap rejected", bool(schema_errors(p2, pol, pol))),
               ("fractional position count rejected", bool(schema_errors(p3, pol, pol))),
               ("altered slot priority rejected", bool(schema_errors(p4, pol, pol))),
               ("the shipped policy is valid", not schema_errors(p, pol, pol))]
    run = sch("run_manifest.schema.json")
    ok_run = {"run_id": "r1", "run_type": "backtest", "trading_date": "2026-09-21",
              "disclosure_cutoff_ts": ts, "market_cutoff_ts": ts, "data_snapshot_id": "s",
              "data_snapshot_sha256": h, "package_digest": h,
              "strategy_cards": [{"code": "ltqv_v1", "version": "1", "sha256": h, "status_at_run": "experimental",
                                  "registry_closure_sha256": h, "lifecycle_transition_id": "0001"}],
              "evaluation_semantics_version": "1.0.0",
              "registry_sha256": h, "source_policy_sha256": h, "sector_map_sha256": h,
              "trading_calendar_sha256": h, "market_universe_policy_sha256": h, "cost_schedule_sha256": h,
              "tax_schedule_sha256": h, "corporate_action_policy": "standard_equity_ca_policy_v2",
              "feature_build": {"roce_3y_avg": {"feature_version": "1", "implementation_sha256": h}},
              "simulator_sha256": h, "code_commit": "abc1234", "container_image_digest": "sha256:" + h,
              "dependency_lock_sha256": h,
              "engine_settings": {"threads": 1, "aggregation_order": "isin_then_date", "tie_tolerance": 1e-9},
              "portfolio_policy_sha256": h, "created_at": ts, "holdout_access": "none", "random_seed": 7,
              "price_read_contract": "first_known_panel"}
    checks += [("a complete backtest manifest is accepted", not schema_errors(ok_run, run, run)),
               ("'not-a-date' rejected", bool(schema_errors({**ok_run, "created_at": "yesterday-ish"}, run, run))),
               ("empty feature_build rejected", bool(schema_errors({**ok_run, "feature_build": {}}, run, run))),
               ("backtest without holdout_access rejected",
                bool(schema_errors({k: v for k, v in ok_run.items() if k != "holdout_access"}, run, run))),
               ("sealed holdout without a ledger entry rejected",
                bool(schema_errors({**ok_run, "holdout_access": "sealed_evaluation"}, run, run))),
               ("backtest without a price_read_contract rejected (r5.6)",
                bool(schema_errors({k: v for k, v in ok_run.items() if k != "price_read_contract"}, run, run))),
               ("sealed holdout on the first-known panel rejected (r5.6)",
                bool(schema_errors({**ok_run, "holdout_access": "sealed_evaluation", "holdout_ledger_entry_id": "e1"}, run, run))),
               ("sealed holdout on exact per-decision reads accepted",
                not schema_errors({**ok_run, "holdout_access": "sealed_evaluation", "holdout_ledger_entry_id": "e1",
                                   "price_read_contract": "exact_per_decision"}, run, run))]
    led = sch("holdout_ledger.schema.json")
    entry = {"entry_id": "e1", "card_version": "1", "card_sha256": h, "exposed_from": "2020-01-01",
             "exposed_to": "2022-12-31", "kind": "inherited", "run_id": "r", "recorded_at": ts}
    checks += [("inherited ledger exposure without its source lineage rejected",
                bool(schema_errors({"lineage": "momx", "entries": [entry]}, led, led))),
               ("inherited ledger exposure with its source lineage accepted",
                not schema_errors({"lineage": "momx", "entries": [{**entry, "source_lineage": "mom"}]}, led, led))]
    failed = [n for n, ok in checks if not ok]
    if failed:
        print("   schema-contract failures:", failed)
    return not failed


def _dup_yaml_rejected():
    try:
        yaml.load(io.StringIO("a: 1\na: 2\n"), Loader=StrictLoader)
        return False
    except yaml.constructor.ConstructorError:
        return True


def _dup_code_rejected():
    import tempfile
    d = tempfile.mkdtemp()
    p1, p2 = os.path.join(d, "a.yaml"), os.path.join(d, "b.yaml")
    for p in (p1, p2):
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            yaml.safe_dump(A, fh, sort_keys=False)
    res = lint_paths([p1, p2], REG_PATH, os.path.join(HERE, "schemas", "card.schema.json"))
    return any("duplicate strategy code" in e for e in res[p2])


# ---------------- pytest entry points ----------------
def test_every_regression_case_is_caught():
    assert run(verbose=False) == []


def test_real_cards_pass():
    assert lint(A, REG, SCHEMA) == []
    assert lint(B, REG, SCHEMA) == []


# ---------------- property test: malformed shapes never crash (audit F09/F11) ----------------
WRONG_VALUES = [None, 0, -1, 3.14, float("inf"), True, "", "x", [], [1, "a"], {}, {"k": [None]}]


def fuzz_shapes():
    """Replace every top-level field, and every field one level down, with every wrong-typed value.
    The linter must return a list of errors for each - never raise."""
    crashes, checked = [], 0
    for base in (A, B):
        paths = [[k] for k in base] + [[k, k2] for k, v in base.items() if isinstance(v, dict) for k2 in v]
        for path in paths:
            for bad in WRONG_VALUES:
                c = copy.deepcopy(base)
                at(c, path[:-1])[path[-1]] = bad
                checked += 1
                try:
                    errs = lint(c, REG, SCHEMA)
                    assert isinstance(errs, list)
                except Exception as e:
                    crashes.append((path, repr(bad), f"{type(e).__name__}: {e}"))
    return checked, crashes


def test_malformed_shapes_never_crash():
    checked, crashes = fuzz_shapes()
    assert crashes == [], crashes[:3]


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):   # UTF-8 output whatever the console or pipe (Windows defaults to cp1252)
        _s.reconfigure(encoding="utf-8")
    fails = run()
    n, crashes = fuzz_shapes()
    print(f"shape fuzz: {n} malformed cards, {len(crashes)} crash(es)")
    for c in crashes[:5]:
        print("   CRASH", c)
    sys.exit(1 if (fails or crashes) else 0)
