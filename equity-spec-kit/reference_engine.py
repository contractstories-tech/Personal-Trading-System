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
import re
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


NOT_GIVEN = object()


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
        """evaluation_semantics 1.1.0: one band per card feature that is a penalised input not known OR a
        conflicted input used in ranking - never two bands for one feature. r5.5 counted a conflicted penalised
        input twice and missed a conflicted material ranking input (review of r5.5)."""
        ranking = self.ranking_inputs()
        drops = 0
        for f in self.card["features"]:
            state = features.get(f, {"state": "missing"})["state"]
            if (self.unknown_behaviour(f) == "penalise" and state != "known") or (state == "conflicted" and f in ranking):
                drops += 1
        band = BANDS[min(drops, len(BANDS) - 1)]
        return band, BANDS.index(band) <= BANDS.index(self.reg["confidence_policy"]["publish_minimum"])

    def evaluate(self, features, composites=None, rank=NOT_GIVEN, in_candidates=True):
        """Gates, candidacy and confidence for one security. In a rank_and_gate card pass its rank (None =
        unrankable): an unrankable security is never a candidate (r5.6). Confidence never changes candidacy:
        the model portfolio takes every candidate within capacity; publishable says only whether it is shown."""
        outcomes = {g["code"]: self.gate(g, features, composites) for g in self.card["gates"]}
        blocks = {g["code"]: g["unknown_blocks"] for g in self.card["gates"]}
        gates_ok = all(o == "PASS" or (o == "UNKNOWN" and not blocks[c]) for c, o in outcomes.items())
        ranked = self.card["selection_method"] != "rank_and_gate" or (rank is not NOT_GIVEN and rank is not None)
        if self.card["selection_method"] == "rank_and_gate" and rank is NOT_GIVEN:
            raise ValueError("a rank_and_gate card is evaluated with the security's rank (None if unrankable)")
        candidate = in_candidates and gates_ok and ranked
        if not in_candidates:
            status = "filtered"
        elif not gates_ok:
            worst = [o for o in ("FAIL", "EXCLUDED", "UNKNOWN") if o in outcomes.values()]
            status = {"FAIL": "failed", "EXCLUDED": "excluded", "UNKNOWN": "unknown_blocked"}[worst[0]]
        elif not ranked:
            status = "unrankable"
        else:
            status = "candidate"
        band, publishable = self.confidence(features)
        return {"gates": outcomes, "candidate": candidate, "status": status, "confidence": band,
                "publishable": candidate and publishable}

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
    def _z_terms(self):
        rk = self.card.get("ranking", {}).get("expr", "")
        return {t for t in self.reg["features"] if f"z({t})" in rk}

    def _used_composites(self):
        rk = self.card.get("ranking", {}).get("expr", "")
        return {n: c for n, c in self.card.get("composites", {}).items() if re.search(rf"\b{n}\b", rk)}

    def ranking_inputs(self):
        """Features under z() in the ranking expression, and inputs of the composites it uses."""
        return self._z_terms() | {i["code"] for c in self._used_composites().values() for i in c["inputs"]}

    def _rank_input(self, f, fs):
        """How one ranking input resolves for one security (evaluation_semantics 1.1.0 ranking):
        ('value', v) | ('drop', reason) | ('none', reason)."""
        st = fs.get(f, {"state": "missing"})
        if st["state"] in ("known", "conflicted"):
            return "value", st["value"]
        if st["state"] == "out_of_domain":
            return ("none", f"{f} out_of_domain (fail)") if st.get("outcome") == "fail" else ("drop", f"{f} out_of_domain")
        b = self.unknown_behaviour(f)
        if b in ("fail", "exclude"):
            return "none", f"{f} {st['state']} ({b})"
        return "drop", f"{f} {st['state']} (penalise)"

    def rank_detail(self, population):
        """population: {isin: features}. Returns {isin: {rank, reason}}; rank None = unrankable, with the reason.
        Z-scores (registry cross_sectional_scoring) over the known and conflicted values of the population."""
        isins = sorted(population)
        rk = self.card.get("ranking", {}).get("expr", "")
        comps_def, zterms = self._used_composites(), self._z_terms()
        resolved = {i: {f: self._rank_input(f, population[i]) for f in self.ranking_inputs()} for i in isins}
        zs = {i: {} for i in isins}
        for f in self.ranking_inputs():
            vals = [float(resolved[i][f][1]) if resolved[i][f][0] == "value" else None for i in isins]
            for i, z in zip(isins, R.zscores(vals)):
                zs[i][f] = z
        out = {}
        for i in isins:
            fatal = [r for kind, r in resolved[i].values() if kind == "none"]
            if fatal:
                out[i] = {"rank": None, "reason": "; ".join(sorted(fatal))}
                continue
            comps, reason = {}, None
            for name, c in comps_def.items():
                got = [(-1 if inp["direction"] == "lower_better" else 1) * zs[i][inp["code"]]
                       for inp in c["inputs"] if zs[i].get(inp["code"]) is not None]
                comps[name] = sum(got) / len(got) if len(got) >= c["min_inputs_known"] else None
                if comps[name] is None and reason is None:
                    reason = f"{name}: {len(got)} of {len(c['inputs'])} inputs, needs {c['min_inputs_known']}"
            missing_z = sorted(f for f in zterms if zs[i].get(f) is None)
            if missing_z and reason is None:
                reason = "no z-score for " + ", ".join(missing_z)
            v = self.ev(parse(rk), Env(population[i], composites=comps, zs=zs[i])) if rk else UNK
            out[i] = {"rank": None, "reason": reason or "ranking expression unknown"} if v is UNK else \
                {"rank": v, "reason": None}
        return out

    def rank_scores(self, population):
        return {i: d["rank"] for i, d in self.rank_detail(population).items()}

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
    """Model-portfolio capacity per card construction (capacity_order: rank). candidates: [{isin, rank,
    market_cap, target_value}]. Existing positions are never displaced. New claims are taken in rank order (ranks
    within tol tie and break on higher market cap, then ISIN) while a slot and spendable cash remain; each is
    sized min(target_value, cash). Returns (taken, not_taken). An unrankable security is not a candidate
    (evaluation_semantics 1.1.0): r5.5 admitted it after the ranked claims, so with spare capacity a security the
    card could not score entered the model portfolio. Passing one here is a caller error."""
    unrankable = sorted(c["isin"] for c in candidates if c["rank"] is None)
    if unrankable:
        raise ValueError(f"unrankable securities are not candidates: {unrankable}")
    order = [r for r in R.rank_order([{"isin": c["isin"], "score": float(c["rank"]), "market_cap": c["market_cap"]}
                                      for c in candidates], tol)]
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


def executable(session_type, reg):
    """registry session_policy: only these session types are evaluated, executed and counted as units."""
    if session_type not in reg["enums"]["session_type"]:
        raise ValueError(f"unknown session_type {session_type!r}")
    return session_type in reg["session_policy"]["executable_session_types"]


def weekly_sessions(calendar, weekday, reg):
    """calendar: [(date, session_type)] as in trading_calendar. One session per ISO week: the last executable
    session (session_policy: a muhurat session trades but is not executable) on or before the named weekday;
    weeks with none are skipped."""
    wd = reg["enums"]["weekday"].index(weekday)
    weeks = {}
    for d, st in calendar:
        if executable(st, reg) and d.weekday() <= wd:
            key = d.isocalendar()[:2]
            weeks[key] = max(weeks.get(key, d), d)
    return sorted(weeks.values())


# ---------------------------------------------------------------- one evaluation, universe to published claims (r5.6)
def run_pipeline(card, reg, params, population, held=(), cash=None, max_positions=None):
    """One rank_and_gate evaluation of one card, end to end, as Doc 01 s7-s9 order it (review of r5.5: r5.5 had
    goldens for each stage but none for the chain, so a population could pass every unit case and still produce
    the wrong claims). population: {isin: {"features": {...}, "sector": code, "market_eligible": bool,
    "market_cap": number, "close": signal-date close}}. Returns {isin: record} and the model portfolio's entries.

      1. universe       market-eligible and not in the card's excluded sectors, else not_in_universe
      2. filters        FALSE -> filtered (out of candidates and scoring population); UNKNOWN -> filter_unknown
                        (out of candidates, still scored)
      3. ranking        rank_detail over the scoring population (evaluation_semantics.ranking)
      4. gates          evaluate(): failed / excluded / unknown_blocked / unrankable / candidate, and confidence
      5. size checks    at model size (target_value from the card's sizing): a failure is size_check_failed
      6. capacity       construct(): held positions first, then rank order, while a slot and cash remain;
                        a candidate not taken is no_capacity
      7. quantities     through the card, with the model's hard_cap_value = min(notional_capital x
                        max_position_pct, the cash construct allotted), so the worst permitted fill never
                        overdraws the model's cash
      8. publication    a taken claim is published when its confidence is at least publish_minimum; below it,
                        the claim is recorded and the model portfolio still holds it
    """
    e = Engine(card, reg, params)
    p = e.params
    universe = {i: s for i, s in population.items()
                if s["market_eligible"] and s["sector"] not in card["universe"]["exclude_sectors"]}
    out = {i: {"status": "not_in_universe"} for i in population if i not in universe}
    member = {i: e.filter_membership(s["features"]) for i, s in universe.items()}
    scoring = {i: universe[i]["features"] for i, (_, scored) in member.items() if scored}
    ranks = e.rank_detail(scoring) if card["selection_method"] == "rank_and_gate" else {}
    candidates = []
    for i, s in sorted(universe.items()):
        in_cand, scored = member[i]
        if not scored:
            out[i] = {"status": "filtered"}
            continue
        r = e.evaluate(s["features"], rank=ranks.get(i, {}).get("rank"), in_candidates=in_cand)
        rec = {"status": "filter_unknown" if r["status"] == "filtered" else r["status"], "gates": r["gates"],
               "confidence": r["confidence"], "rank": ranks.get(i, {}).get("rank"),
               "rank_reason": ranks.get(i, {}).get("reason")}
        out[i] = rec
        if not r["candidate"]:
            continue
        runtime = {"hard_cap_value": num(p["notional_capital"]) * num(p["max_position_pct"])}
        if "atr_pct_20" in s["features"]:
            runtime["atr_pct_at_signal"] = num(s["features"]["atr_pct_20"]["value"])
        env = Env(s["features"], runtime=runtime)
        target_value = e.ev(parse(card["sizing"]["formula"]), env)
        checks = e.size_checks(s["features"], target_value / D(10) ** 7)
        if any(v != "PASS" for v in checks.values()):
            rec.update(status="size_check_failed", size_checks=checks)
            continue
        rec.update(target_value=target_value, publishable=r["publishable"])
        candidates.append({"isin": i, "rank": rec["rank"], "market_cap": s["market_cap"], "target_value": target_value,
                           "runtime": runtime})
    taken, _ = construct(candidates, set(held), max_positions, D(str(cash)))
    by = {c["isin"]: c for c in candidates}
    for c in candidates:
        out[c["isin"]]["status"] = "no_capacity"
        out[c["isin"]]["model_publishable"] = out[c["isin"]].pop("publishable")
    entries = []
    for i, allotted in taken:
        c = by[i]
        runtime = dict(c["runtime"], target_value=allotted, hard_cap_value=min(c["runtime"]["hard_cap_value"], allotted))
        prices = {("close", "signal_date"): population[i]["close"]}
        q = e.quantities(runtime, prices, population[i]["features"])
        rec = out[i]
        rec.update(status="taken", allotted=float(allotted), target_qty=q["target_qty"])
        if len(card["proposed_execution_rule"]["tranches"]) > 1:
            rec["tranche_1_qty"] = e.tranche_quantities(runtime, prices)["quantities"][0]
        rec["published"] = bool(rec.pop("model_publishable"))
        entries.append([i, q["target_qty"]])
    return out, entries
