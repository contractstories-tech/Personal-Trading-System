#!/usr/bin/env python3
"""Reference card engine: evaluates a strategy card's OWN expressions under registry evaluation_semantics.

Audit A1: in r5.4 nothing executed a card. The golden cases called reference functions with constants typed
into the code (run_stop(mult=2.5)), so a card with a 5% ROCE gate and a 4x-ATR stop passed every check. This
engine reads gates, exits, filters, ranking, sizing, tranche and stop expressions from the YAML itself, parsed
by speclint's parser, so golden/card_cases.yaml fails when a card's meaning changes. M7/M8/M9 must reproduce it.

Semantics (registry evaluation_semantics 1.0.0; Document 01 s7):
  gates    - input resolution first (fail, exclude, out_of_domain fail, out_of_domain drop, penalise), then the
             expression over known inputs only. Gates never combine unknowns.
  exits    - Kleene three-valued logic; FIRE when TRUE, or when an input read (persist: latest unit) is
             out_of_domain with outcome fail unless the exit says on_out_of_domain: review; UNKNOWN -> REVIEW.
  filters  - Kleene; FALSE leaves candidates and the scoring population; UNKNOWN leaves candidates only.
  numbers  - every feature, runtime value and literal becomes a Decimal; gate, exit and filter inputs are
             quantised to 9 decimal places (ROUND_HALF_EVEN) so floating-point noise from a feature build
             cannot flip a boundary (audit C2).
"""
import datetime as dt
import decimal
import math
import os
from decimal import Decimal as D

import reference_sim as R
from speclint import Parser, load_yaml, tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
decimal.getcontext().prec = 34
Q9 = D("1e-9")
UNK = "UNKNOWN"
NON_KNOWN = ("missing", "stale", "conflicted", "not_applicable")
BANDS = ["high", "medium", "low", "insufficient"]


def num(x, quantise=True):
    if x is None or isinstance(x, bool):
        return x
    v = x if isinstance(x, D) else D(repr(x)) if isinstance(x, float) else D(x)
    return v.quantize(Q9, rounding=decimal.ROUND_HALF_EVEN) if quantise else v


def parse(src):
    return Parser(tokenize(src)).parse()


def load(code, reg=None, params=None, card=None):
    card = card or load_yaml(os.path.join(HERE, "strategies", f"{code}.yaml"))
    return Engine(card, reg or load_yaml(os.path.join(HERE, "registry.yaml")), params)


class Env:
    """Values visible to one evaluation. features: {code: {state, value, outcome}}; units: {unit: [feature
    dicts, oldest first, current last]} for persist; runtime: {name: value}; prices: {(field, date_name): value}."""

    def __init__(self, features=None, runtime=None, prices=None, units=None, composites=None, zs=None):
        self.features, self.runtime = features or {}, runtime or {}
        self.prices, self.units = prices or {}, units or {}
        self.composites, self.zs = composites or {}, zs or {}
        self.read = set()


class Engine:
    def __init__(self, card, reg, params=None):
        """params: values for OPEN / CALIBRATE parameters (a run supplies them; the card never guesses them)."""
        self.card, self.reg = card, reg
        self.params = {k: v["value"] for k, v in card.get("params", {}).items()}
        self.params.update(card["sizing"]["params"])
        self.params.update(params or {})

    # ---------------------------------------------------------------- input behaviour
    def unknown_behaviour(self, f):
        return self.card["unknown_overrides"].get(f, self.reg["features"].get(f, {}).get("default_unknown", "exclude"))

    def inputs_of(self, node):
        """Features an expression reads, composites expanded into their inputs."""
        out = set()

        def walk(n):
            k = n[0]
            if k == "id":
                name = n[1]
                if name in self.reg["features"]:
                    out.add(name)
                elif name in self.card.get("composites", {}):
                    out.update(i["code"] for i in self.card["composites"][name]["inputs"])
            elif k == "call":
                for a in n[2]:
                    walk(a)
            elif k in ("neg", "not"):
                walk(n[1])
            elif k in ("cmp", "arith", "bool"):
                walk(n[2]); walk(n[3])
        walk(node)
        return out

    # ---------------------------------------------------------------- expression evaluation (Kleene)
    def ev(self, node, env):
        k = node[0]
        if k == "num":
            return D(node[1])
        if k == "id":
            return self._ident(node[1], env)
        if k == "neg":
            v = self.ev(node[1], env)
            return UNK if v is UNK else -v
        if k == "not":
            v = self.ev(node[1], env)
            return UNK if v is UNK else (not v)
        if k == "bool":
            a, b = self.ev(node[2], env), self.ev(node[3], env)
            if node[1] == "AND":
                if a is False or b is False:
                    return False
                return True if (a is True and b is True) else UNK
            if a is True or b is True:
                return True
            return False if (a is False and b is False) else UNK
        if k == "cmp":
            a, b = self.ev(node[2], env), self.ev(node[3], env)
            if a is UNK or b is UNK:
                return UNK
            return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b, "==": a == b, "!=": a != b}[node[1]]
        if k == "arith":
            a, b = self.ev(node[2], env), self.ev(node[3], env)
            if a is UNK or b is UNK:
                return UNK
            if node[1] == "/":
                return UNK if b == 0 else a / b
            return {"+": a + b, "-": a - b, "*": a * b}[node[1]]
        if k == "call":
            return self._call(node[1], node[2], env)
        raise ValueError(node)

    def _ident(self, name, env):
        if "." in name:                                   # namespaced enum literal
            return name.split(".", 1)[1]
        if name in ("true", "false"):
            return name == "true"
        if name in self.reg["features"]:
            env.read.add(name)
            f = env.features.get(name, {"state": "missing"})
            if f["state"] != "known":
                return UNK
            v = f["value"]
            return v if isinstance(v, (bool, str)) else num(v)
        if name in env.composites:
            v = env.composites[name]
            return UNK if v is None else num(v)
        if name in env.runtime:
            v = env.runtime[name]
            return UNK if v is None else (v if isinstance(v, (bool, str, dt.date)) else num(v, quantise=False))
        if name in self.params:
            v = self.params[name]
            if v in ("OPEN", "CALIBRATE"):
                raise ValueError(f"{name} is {v}: set it before running the card")
            return num(v, quantise=False)
        raise KeyError(f"no value for '{name}'")

    def _date_name(self, node):
        if node[0] == "id":
            return node[1]
        return f"prev_session({node[2][0][1]})"

    def _call(self, fn, args, env):
        if fn == "persist":
            n = int(self.ev(args[1], env))
            unit = args[2][1].split(".", 1)[1]
            hist = env.units.get(unit, [])
            if len(hist) < n:
                return UNK
            vals = []
            for snap in hist[-n:]:
                sub = Env(snap, env.runtime, env.prices, env.units, env.composites, env.zs)
                vals.append(self.ev(args[0], sub))
                env.read |= sub.read
            if any(v is UNK for v in vals):
                return UNK
            return all(vals)
        if fn in ("close_raw", "open_raw"):
            key = ("close" if fn == "close_raw" else "open", self._date_name(args[0]))
            v = env.prices.get(key)
            return UNK if v is None else num(v, quantise=False)
        if fn == "z":
            v = env.zs.get(args[0][1])
            return UNK if v is None else num(v)
        a = [self.ev(x, env) for x in args]
        if any(x is UNK for x in a):
            return UNK
        if fn == "min":
            return min(a)
        if fn == "max":
            return max(a)
        if fn == "if":
            return a[1] if a[0] else a[2]
        if fn == "floor":
            return D(math.floor(a[0]))
        if fn == "impact_cost":
            return num(R.impact_cost(float(a[0]), float(a[1])))
        raise KeyError(fn)

    # ---------------------------------------------------------------- gates, candidacy, confidence
    def gate(self, g, features, composites=None):
        node = parse(g["expr"])
        reads = self.inputs_of(node)
        states = {f: features.get(f, {"state": "missing"}) for f in reads}
        nk = {f: s for f, s in states.items() if s["state"] in NON_KNOWN}
        if any(self.unknown_behaviour(f) == "fail" for f in nk):
            return "FAIL"
        if any(self.unknown_behaviour(f) == "exclude" for f in nk):
            return "EXCLUDED"
        ood = {f: s for f, s in states.items() if s["state"] == "out_of_domain"}
        if any(s.get("outcome") == "fail" for s in ood.values()):
            return "FAIL"
        if ood or nk:                                     # drop, or a penalised secondary input
            return "UNKNOWN"
        comps = composites or {}
        if any(c in comps and comps[c] is None for c in self.card.get("composites", {}) if c in g["expr"]):
            return "UNKNOWN"
        v = self.ev(node, Env(features, composites=comps))
        return "UNKNOWN" if v is UNK else ("PASS" if v else "FAIL")

    def confidence(self, features):
        drops = sum(1 for f in self.card["features"] if self.unknown_behaviour(f) == "penalise"
                    and features.get(f, {"state": "missing"})["state"] != "known")
        drops += sum(1 for f in self.card["features"] if features.get(f, {}).get("state") == "conflicted"
                     and self.unknown_behaviour(f) == "penalise")
        band = BANDS[min(drops, len(BANDS) - 1)]
        return band, BANDS.index(band) <= BANDS.index(self.reg["confidence_policy"]["publish_minimum"])

    def evaluate(self, features, composites=None):
        outcomes = {g["code"]: self.gate(g, features, composites) for g in self.card["gates"]}
        blocks = {g["code"]: g["unknown_blocks"] for g in self.card["gates"]}
        candidate = all(o == "PASS" or (o == "UNKNOWN" and not blocks[c]) for c, o in outcomes.items())
        band, publishable = self.confidence(features)
        return {"gates": outcomes, "candidate": candidate, "confidence": band, "publishable": candidate and publishable}

    # ---------------------------------------------------------------- filters and exits
    def filter(self, expr, features):
        v = self.ev(parse(expr), Env(features))
        return v                                           # True, False or UNKNOWN

    def filter_membership(self, features):
        """(in_candidates, in_scoring_population) under evaluation_semantics.universe_filters."""
        vals = [self.filter(f, features) for f in self.card["universe"]["filters"]]
        if any(v is False for v in vals):
            return False, False
        if any(v is UNK for v in vals):
            return False, True
        return True, True

    def exit(self, x, features, runtime=None, units=None, prices=None):
        env = Env(features, runtime, prices, units)
        v = self.ev(parse(x["expr"]), env)
        if v is True:
            return "FIRE"
        latest = features
        failed = [f for f in env.read if latest.get(f, {}).get("state") == "out_of_domain"
                  and latest[f].get("outcome") == "fail"]
        if failed and x.get("on_out_of_domain", "fire") == "fire":
            return "FIRE"
        return "REVIEW" if (v is UNK or failed) else "NO"

    # ---------------------------------------------------------------- scoring and ranking
    def rank_scores(self, population):
        """population: {isin: features}. Z-scores per registry cross_sectional_scoring; composites; ranking."""
        isins = sorted(population)
        zs = {i: {} for i in isins}
        wanted = {i["code"] for c in self.card.get("composites", {}).values() for i in c["inputs"]}
        rk = self.card.get("ranking", {}).get("expr", "")
        wanted |= {t for t in self.reg["features"] if f"z({t})" in rk}
        for f in wanted:
            vals = [population[i].get(f, {}).get("value") if population[i].get(f, {}).get("state") == "known" else None
                    for i in isins]
            for i, z in zip(isins, R.zscores(vals)):
                zs[i][f] = z
        out = {}
        for i in isins:
            comps = {}
            for name, c in self.card.get("composites", {}).items():
                got = [(-1 if inp["direction"] == "lower_better" else 1) * zs[i][inp["code"]]
                       for inp in c["inputs"] if zs[i].get(inp["code"]) is not None]
                comps[name] = sum(got) / len(got) if len(got) >= c["min_inputs_known"] else None
            v = self.ev(parse(rk), Env(population[i], composites=comps, zs=zs[i])) if rk else UNK
            out[i] = None if v is UNK else v
        return out

    # ---------------------------------------------------------------- sizing, quantities, tranches, stop
    def quantities(self, runtime, prices, features=None):
        """target_value, entry_ref, entry_high and target_qty from the card, then the engine's own cap invariant
        (belt and braces for audit B2): qty <= floor(hard_cap_value / entry_high) whatever the card says."""
        env = Env(features, runtime=dict(runtime), prices=prices)
        if "target_value" not in env.runtime:
            env.runtime["target_value"] = self.ev(parse(self.card["sizing"]["formula"]), env)
        per = self.card["proposed_execution_rule"]
        env.runtime["entry_ref"] = self.ev(parse(per["entry_ref"]), env)
        env.runtime["entry_high"] = self.ev(parse(per["entry_high"]), env)
        q = int(self.ev(parse(per["target_qty"]), env))
        cap = int(math.floor(env.runtime["hard_cap_value"] / env.runtime["entry_high"]))
        return {"target_value": env.runtime["target_value"], "entry_ref": env.runtime["entry_ref"],
                "entry_high": env.runtime["entry_high"], "target_qty": min(q, cap), "cap_enforced": q > cap}

    def tranche_quantities(self, runtime, prices, t2=None, t3=None):
        """ltqv-style tranches through the card's expressions. t2/t3: {revised_target_value, prior_close, attempts}."""
        base = self.quantities(runtime, prices)
        per = self.card["proposed_execution_rule"]
        tr = per["tranches"]
        env = Env(runtime={**runtime, **base, "current_earmark_qty": 0}, prices=prices)
        env.runtime["tranche_weight"] = tr[0]["weight"]
        q1 = int(self.ev(parse(tr[0]["qty"]), env))
        out, earmark = [q1], q1
        for t, spec in zip(tr[1:], (t2, t3)):
            if spec is None or not any(spec["attempts"]):
                out.append(0)
                return {"quantities": out + [0] * (len(tr) - len(out)), "earmark": earmark,
                        "cancelled_after": t["n"]}
            e = Env(runtime={**env.runtime, "revised_target_value": spec["revised_target_value"],
                             "current_earmark_qty": earmark, "tranche_weight": t["weight"]},
                    prices={**prices, ("close", "prev_session(eval_date)"): spec["prior_close"]})
            e.runtime["tranche_limit"] = self.ev(parse(t["limit"]), e)
            e.runtime["revised_target_qty"] = self.ev(parse(per["revised_target_qty"]), e)
            q = int(self.ev(parse(t["qty"]), e))
            earmark += q
            out.append(q)
        return {"quantities": out, "earmark": earmark, "cancelled_after": None}

    def run_stop(self, entry_fill, atr_at_signal, sessions):
        """The card's stop.initial / stop.update and its stop-testing exits, test-then-update, from the fill
        session (Doc 01 s11). Returns the same shape as reference_sim.run_stop."""
        st = self.card["stop"]
        stop_exits = [x for x in self.card["exit_rules"] if "stop_in_force" in x["expr"]]
        rt = {"entry_basis": num(entry_fill, False), "atr_pct_at_signal": num(atr_at_signal, False)}
        rt["stop_in_force"] = self.ev(parse(st["initial"]), Env(runtime=rt))
        rt["highest_close_since_entry"], rt["atr_pct_at_peak"] = num(entry_fill, False), num(atr_at_signal, False)
        tested = []
        for i, s in enumerate(sessions):
            tested.append(float(round(rt["stop_in_force"], 4)))
            prices = {("close", "eval_date"): s["close"]}
            if any(self.exit(x, {}, rt, prices=prices) == "FIRE" for x in stop_exits):
                return {"stops_tested": tested, "exit_session": i}
            c = num(s["close"], False)
            if c > rt["highest_close_since_entry"]:
                rt["highest_close_since_entry"], rt["atr_pct_at_peak"] = c, num(s["atr_pct"], False)
            rt["stop_prev"] = rt["stop_in_force"]
            rt["stop_in_force"] = self.ev(parse(st["update"]), Env(runtime=rt))
        return {"stops_tested": tested, "exit_session": None}

    def size_checks(self, features, provisional_value_cr):
        env_f = features
        res = {}
        for c in self.card.get("size_dependent_checks", []):
            v = self.ev(parse(c["expr"]), Env(env_f, runtime={"provisional_value_cr": provisional_value_cr}))
            res[c["code"]] = "UNKNOWN" if v is UNK else ("PASS" if v else "FAIL")
        return res


# ---------------------------------------------------------------- construction and scale (audit A3)
def construct(candidates, held, max_positions, cash, tol=1e-9):
    """Model-portfolio capacity per card construction (capacity_order: rank). candidates: [{isin, rank (None =
    missing), market_cap, target_value}]. Existing positions are never displaced. New claims are taken in rank
    order (missing ranks last; ranks within tol tie and break on higher market cap, then ISIN) while a slot and
    spendable cash remain; each is sized min(target_value, cash). Returns (taken, not_taken)."""
    ranked = [c for c in candidates if c["rank"] is not None]
    order = [r for r in R.rank_order([{"isin": c["isin"], "score": float(c["rank"]), "market_cap": c["market_cap"]}
                                      for c in ranked], tol)]
    order += [c["isin"] for c in sorted((c for c in candidates if c["rank"] is None), key=lambda c: (-c["market_cap"], c["isin"]))]
    by = {c["isin"]: c for c in candidates}
    slots, taken, rest = max_positions - len(held), [], []
    for i in order:
        if i in held:
            continue
        if slots > 0 and cash > 0:
            size = min(by[i]["target_value"], cash)
            taken.append((i, size))
            cash -= size
            slots -= 1
        else:
            rest.append(i)
    return taken, rest


def actual_target(target_value, notional_capital, total_capital, headroom):
    """Doc 01 s9: a claim sized on measurement capital becomes a weight; the actual target is that weight of
    your total capital, capped by the allocator's headroom."""
    return min(D(str(target_value)) / D(str(notional_capital)) * D(str(total_capital)), D(str(headroom)))


def weekly_sessions(calendar, weekday):
    """calendar: [(date, is_executable)] - muhurat and holidays are not executable. One session per ISO week:
    the last executable session on or before the named weekday; weeks with none are skipped."""
    wd = ["mon", "tue", "wed", "thu", "fri"].index(weekday)
    weeks = {}
    for d, ok in calendar:
        if ok and d.weekday() <= wd:
            key = d.isocalendar()[:2]
            weeks[key] = max(weeks.get(key, d), d)
    return sorted(weeks.values())
