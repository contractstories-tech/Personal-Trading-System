#!/usr/bin/env python3
"""speclint v3 - strategy-card compiler (Document 01 r5, s8).

Stage 1  closed-schema validation against schemas/card.schema.json (unknown keys are errors;
         malformed shapes produce errors, never crashes).
Stage 2  semantic compilation against registry.yaml: registry pin by sha256, strategy class,
         data resolution and triggers, expression grammar and types, reference integrity,
         runtime-state assignment, corporate-action completeness, status-dependent completeness.

A PASS means a card is WELL-FORMED. It does not mean it is CORRECT: Document 04's golden
cases establish that.

Usage:  python3 speclint.py [--registry registry.yaml] [--schema schemas/card.schema.json] card.yaml ...
Exit:   0 = all pass, 1 = violations, 2 = unreadable registry/schema.
"""
import hashlib, json, math, os, re, sys
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------ strict YAML
class StrictLoader(yaml.SafeLoader):
    pass


def _no_dupes(loader, node, deep=False):
    seen = set()
    for k_node, _ in node.value:
        k = loader.construct_object(k_node, deep=deep)
        if k in seen:
            raise yaml.constructor.ConstructorError(None, None, f"duplicate key '{k}'", k_node.start_mark)
        seen.add(k)
    return loader.construct_mapping(node, deep)


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dupes)


def load_yaml(path):
    with open(path) as fh:
        return yaml.load(fh, Loader=StrictLoader)


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# ------------------------------------------------------------------ JSON Schema subset
def _is_type(v, t):
    if t == "object":
        return isinstance(v, dict)
    if t == "array":
        return isinstance(v, list)
    if t == "string":
        return isinstance(v, str)
    if t == "boolean":
        return isinstance(v, bool)
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool) and not (
            isinstance(v, float) and (math.isnan(v) or math.isinf(v)))
    return False


def _valid_date(v):
    """Shape AND calendar: 2026-99-99 has the right shape and is not a date (review H8)."""
    import datetime as _dt
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return False
    try:
        _dt.date.fromisoformat(v)
        return True
    except ValueError:
        return False


def _valid_datetime(v):
    import datetime as _dt
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})", v):
        return False
    try:
        return _dt.datetime.fromisoformat(v.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def schema_errors(v, s, root, path="card"):
    """Validates the JSON Schema subset used by card.schema.json. Returns a list of errors."""
    if "$ref" in s:
        s = root["$defs"][s["$ref"].split("/")[-1]]
    if "oneOf" in s:
        ok = [sub for sub in s["oneOf"] if not schema_errors(v, sub, root, path)]
        return [] if len(ok) == 1 else [f"{path}: must match exactly one allowed form"]
    E = []
    for sub in s.get("allOf", []):
        E += schema_errors(v, sub, root, path)
    if "if" in s:
        if not schema_errors(v, s["if"], root, path):
            if "then" in s:
                E += schema_errors(v, s["then"], root, path)
        elif "else" in s:
            E += schema_errors(v, s["else"], root, path)
    if "const" in s and v != s["const"]:
        return [f"{path}: must be {s['const']!r}"]
    if "type" in s and not _is_type(v, s["type"]):
        return [f"{path}: must be {s['type']}, got {type(v).__name__}"]
    if "enum" in s and v not in s["enum"]:
        E.append(f"{path}: {v!r} not one of {s['enum']}")
    if _is_type(v, "number"):
        if "minimum" in s and v < s["minimum"]:
            E.append(f"{path}: {v} below minimum {s['minimum']}")
        if "maximum" in s and v > s["maximum"]:
            E.append(f"{path}: {v} above maximum {s['maximum']}")
        if "exclusiveMinimum" in s and v <= s["exclusiveMinimum"]:
            E.append(f"{path}: {v} must be > {s['exclusiveMinimum']}")
    if isinstance(v, str):
        if "minLength" in s and len(v.strip()) < s["minLength"]:
            E.append(f"{path}: must be at least {s['minLength']} characters")
        if "pattern" in s and not re.search(s["pattern"], v):
            E.append(f"{path}: {v!r} does not match {s['pattern']}")
        if s.get("format") == "date-time" and not _valid_datetime(v):
            E.append(f"{path}: {v!r} is not an RFC 3339 date-time with offset")
        if s.get("format") == "date" and not _valid_date(v):
            E.append(f"{path}: {v!r} is not a date")
    if isinstance(v, list):
        if "minItems" in s and len(v) < s["minItems"]:
            E.append(f"{path}: needs at least {s['minItems']} item(s)")
        if s.get("uniqueItems") and len({json.dumps(x, sort_keys=True, default=str) for x in v}) != len(v):
            E.append(f"{path}: items must be unique")
        if "items" in s:
            for i, item in enumerate(v):
                E += schema_errors(item, s["items"], root, f"{path}[{i}]")
    if isinstance(v, dict):
        if "minProperties" in s and len(v) < s["minProperties"]:
            E.append(f"{path}: needs at least {s['minProperties']} entr(y/ies)")
        props = s.get("properties", {})
        for r in s.get("required", []):
            if r not in v:
                E.append(f"{path}: missing required '{r}'")
        addl = s.get("additionalProperties", True)
        for k, val in v.items():
            if k in props:
                E += schema_errors(val, props[k], root, f"{path}.{k}")
            elif addl is False:
                E.append(f"{path}: unknown field '{k}' (closed schema)")
            elif isinstance(addl, dict):
                E += schema_errors(val, addl, root, f"{path}.{k}")
    return E


# ------------------------------------------------------------------ expressions
TOKEN = re.compile(r"\s*(?:(\d+\.\d+|\d+)|(<=|>=|==|!=|<|>|\+|-|\*|/|\(|\)|,)|([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?))")
KEYWORDS = {"AND", "OR", "NOT"}


class ExprError(Exception):
    pass


def tokenize(src):
    pos, out, src = 0, [], str(src)
    while pos < len(src):
        if src[pos:].strip() == "":
            break
        m = TOKEN.match(src, pos)
        if not m or m.end() == pos:
            raise ExprError(f"cannot parse near '{src[pos:pos + 15]}'")
        num, op, ident = m.groups()
        out.append(("num", num) if num else ("op", op) if op else ("id", ident))
        pos = m.end()
    return out


class Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self, kind=None, val=None):
        k, v = self.peek()
        if k is None or (kind and k != kind) or (val and v != val):
            raise ExprError(f"expected {val or kind}, got {v}")
        self.i += 1
        return v

    def parse(self):
        n = self.p_or()
        if self.i != len(self.t):
            raise ExprError(f"unexpected trailing '{self.peek()[1]}'")
        return n

    def p_or(self):
        n = self.p_and()
        while self.peek() == ("id", "OR"):
            self.take(); n = ("bool", "OR", n, self.p_and())
        return n

    def p_and(self):
        n = self.p_not()
        while self.peek() == ("id", "AND"):
            self.take(); n = ("bool", "AND", n, self.p_not())
        return n

    def p_not(self):
        if self.peek() == ("id", "NOT"):
            self.take(); return ("not", self.p_not())
        return self.p_cmp()

    def p_cmp(self):
        n = self.p_add()
        k, v = self.peek()
        if k == "op" and v in ("<", "<=", ">", ">=", "==", "!="):
            self.take(); n = ("cmp", v, n, self.p_add())
        return n

    def p_add(self):
        n = self.p_mul()
        while self.peek()[0] == "op" and self.peek()[1] in "+-":
            op = self.take(); n = ("arith", op, n, self.p_mul())
        return n

    def p_mul(self):
        n = self.p_unary()
        while self.peek()[0] == "op" and self.peek()[1] in "*/":
            op = self.take(); n = ("arith", op, n, self.p_unary())
        return n

    def p_unary(self):
        if self.peek() == ("op", "-"):
            self.take(); return ("neg", self.p_unary())
        return self.p_primary()

    def p_primary(self):
        k, v = self.peek()
        if k == "num":
            self.take(); return ("num", v)
        if k == "op" and v == "(":
            self.take(); n = self.p_or(); self.take("op", ")"); return n
        if k == "id":
            self.take()
            if self.peek() == ("op", "("):
                self.take(); args = []
                if self.peek() != ("op", ")"):
                    args.append(self.p_or())
                    while self.peek() == ("op", ","):
                        self.take(); args.append(self.p_or())
                self.take("op", ")")
                return ("call", v, args)
            return ("id", v)
        raise ExprError(f"unexpected '{v}'")


NUMERIC = {"num", "qty", "int"}


def is_num(t):
    return t in NUMERIC


def is_qty(t):
    return t in ("qty", "int")


class Checker:
    def __init__(self, reg, card):
        self.reg, self.card = reg, card
        self.params = set((card.get("params") or {}).keys())
        self.composites = set((card.get("composites") or {}).keys())
        self.refs = set()

    def type_of(self, node):
        kind = node[0]
        if kind == "num":
            return "num" if "." in node[1] else "int"
        if kind == "id":
            name = node[1]
            if "." in name:                               # namespaced enum literal
                ens, val = name.split(".", 1)
                if ens not in self.reg["enums"]:
                    raise ExprError(f"unknown enum '{ens}'")
                if val not in [str(x) for x in self.reg["enums"][ens]]:
                    raise ExprError(f"'{val}' is not a value of enum {ens}")
                return f"enum:{ens}"
            self.refs.add(name)
            if name in ("true", "false"):
                return "bool"
            if name in KEYWORDS:
                raise ExprError(f"misplaced keyword {name}")
            f = self.reg["features"].get(name)
            if f:
                return f.get("type", "num")
            r = self.reg["runtime"].get(name)
            if r:
                return r["type"]
            if name in self.params or name in self.composites:
                return "num"
            if name in self.reg["functions"]:
                raise ExprError(f"function '{name}' used without arguments")
            for ens, vals in self.reg["enums"].items():
                if name in [str(x) for x in vals]:
                    raise ExprError(f"enum literal '{name}' must be namespaced as {ens}.{name}")
            raise ExprError(f"unresolved identifier '{name}'")
        if kind == "neg":
            t = self.type_of(node[1])
            if not is_num(t):
                raise ExprError("unary minus on non-number")
            return "num"
        if kind == "arith":
            a, b = self.type_of(node[2]), self.type_of(node[3])
            if not (is_num(a) and is_num(b)):
                raise ExprError(f"arithmetic on {a}, {b}")
            if node[1] in "+-" and is_qty(a) and is_qty(b):
                return "qty" if "qty" in (a, b) else "int"
            return "num"
        if kind == "cmp":
            a, b = self.type_of(node[2]), self.type_of(node[3])
            if is_num(a) and is_num(b):
                return "bool"
            if node[1] in ("==", "!=") and a == b:
                return "bool"
            raise ExprError(f"cannot compare {a} {node[1]} {b}")
        if kind == "bool":
            for sub in node[2:]:
                if self.type_of(sub) != "bool":
                    raise ExprError(f"{node[1]} needs boolean operands")
            return "bool"
        if kind == "not":
            if self.type_of(node[1]) != "bool":
                raise ExprError("NOT needs a boolean")
            return "bool"
        if kind == "call":
            name, args = node[1], node[2]
            fn = self.reg["functions"].get(name)
            if fn is None:
                raise ExprError(f"unknown function '{name}'")
            if len(args) != len(fn["args"]):
                raise ExprError(f"{name}() takes {len(fn['args'])} args, got {len(args)}")
            ats = [self.type_of(a) for a in args]
            for want, got in zip(fn["args"], ats):
                ok = (want == got) or (want == "num" and is_num(got)) or (want == "qty" and is_qty(got))
                if not ok:
                    raise ExprError(f"{name}(): expected {want}, got {got}")
            if name in ("min", "max") and all(is_qty(t) for t in ats):
                return "qty"
            return fn["returns"]
        raise ExprError(f"bad node {kind}")


# ------------------------------------------------------------------ semantic stage
def lint(card, reg, reg_sha, schema):
    if not isinstance(card, dict):
        return ["card: must be a mapping"]
    E = schema_errors(card, schema, schema)
    if E:
        return sorted(set(E))          # semantic stage only runs on a well-shaped card
    err = E.append
    en = reg["enums"]
    feats, flags, runtime = reg["features"], reg.get("forensic_flags", {}), reg["runtime"]
    status = card["status"]
    declared = card["features"]
    dset = set(declared)

    # lineage: a card's code must belong to its lineage (holdout exposure is tracked per lineage)
    if not card["code"].startswith(card["lineage"] + "_v"):
        err(f"code '{card['code']}' does not belong to lineage '{card['lineage']}'")

    # materiality: a material input may never be penalised, and never feed a waivable gate
    secondary = set(reg.get("secondary_features", []))
    for f, b in card["unknown_overrides"].items():
        if b == "penalise" and f not in secondary:
            err(f"unknown_override '{f}: penalise' - '{f}' is material; its absence must block or exclude")

    # registry pin
    if card["registry"]["version"] != reg["registry_version"]:
        err(f"registry.version {card['registry']['version']} != registry {reg['registry_version']}")
    if card["registry"]["sha256"] != reg_sha:
        err("registry.sha256 does not match the registry file: re-validate the card against the changed registry")

    # identity and vocabularies
    for field, enum in (("status", "status"), ("trade_direction", "trade_direction"), ("horizon", "horizon"),
                        ("selection_method", "selection_method")):
        if card[field] not in en[enum]:
            err(f"{field} '{card[field]}' not registered")
    sc = reg["strategy_classes"].get(card["strategy_class"])
    if sc is None:
        err(f"strategy_class '{card['strategy_class']}' not registered")
    else:
        if card["data_resolution"] not in sc["data_resolutions"]:
            err(f"data_resolution '{card['data_resolution']}' not allowed for class {card['strategy_class']}")
        for trig in card["evaluation"]["entry_triggers"] + [card["evaluation"]["risk_trigger"]]:
            t = trig["trigger"]
            if t not in reg["triggers"]:
                err(f"trigger '{t}' not registered")
                continue
            if t not in sc["triggers"]:
                err(f"trigger '{t}' not allowed for class {card['strategy_class']}")
            need = set(reg["triggers"][t]["params"])
            have = set(trig) - {"trigger"}
            if need - have:
                err(f"trigger '{t}' missing params {sorted(need - have)}")
            if have - need:
                err(f"trigger '{t}' has params {sorted(have - need)} it does not take")
            if "weekday" in trig and trig["weekday"] not in en["weekday"]:
                err(f"weekday '{trig['weekday']}' invalid")
    dr = reg["data_resolutions"].get(card["data_resolution"])
    if dr is None:
        err(f"data_resolution '{card['data_resolution']}' not registered")
    elif not dr["implemented"] and status != "experimental":
        err(f"data_resolution '{card['data_resolution']}' is not implemented; card cannot pass experimental")

    # selection method
    if card["selection_method"] == "gate_only" and "ranking" in card:
        err("selection_method gate_only must not define ranking")
    if card["selection_method"] == "rank_and_gate" and "ranking" not in card:
        err("selection_method rank_and_gate requires ranking")

    # universe
    if card["universe"]["base"] not in en["universe_base"]:
        err(f"universe.base '{card['universe']['base']}' not registered")
    for s in card["universe"]["exclude_sectors"]:
        if s not in reg["sector_codes"]:
            err(f"exclude_sectors '{s}' is not a registered sector code")

    # features and overrides
    for f in declared:
        if f not in feats and f not in flags:
            err(f"feature '{f}' not in registry")
    for f, b in card["unknown_overrides"].items():
        if f not in dset:
            err(f"unknown_override for undeclared feature '{f}'")
        if b not in en["unknown_behaviour"]:
            err(f"unknown_override '{f}: {b}' invalid")

    def research_only(f):
        return feats.get(f, {}).get("status") == "research_only"

    # params
    for p, spec in card["params"].items():
        if spec["value"] == "CALIBRATE":
            cal = spec.get("calibration")
            if not cal:
                err(f"param '{p}' is CALIBRATE with no calibration rule")
            else:
                if cal["statistic"] not in en["calibration_statistic"]:
                    err(f"param '{p}': calibration statistic invalid")
                if cal["feature"] not in dset:
                    err(f"param '{p}': calibration feature '{cal['feature']}' not declared")
                for pf in cal["population"]:
                    if feats.get(pf, {}).get("type") != "bool" or pf not in dset:
                        err(f"param '{p}': population key '{pf}' must be a declared boolean feature")

    # composites
    for cname, c in card["composites"].items():
        codes = [i["code"] for i in c["inputs"]]
        if len(codes) != len(set(codes)):
            err(f"composite {cname}: duplicate input")
        for inp in c["inputs"]:
            if inp["code"] not in dset:
                err(f"composite {cname}: input '{inp['code']}' not declared")
            if inp["direction"] not in en["direction"]:
                err(f"composite {cname}: input '{inp['code']}' direction invalid")
            if research_only(inp["code"]):
                err(f"composite {cname}: research_only feature '{inp['code']}' drives selection")
        if c["min_inputs_known"] > len(c["inputs"]):
            err(f"composite {cname}: min_inputs_known exceeds inputs")

    exprs = []

    def add(where, src, want):
        exprs.append((where, src, want))

    def codes(section, want="bool"):
        seen = []
        for item in card.get(section, []):
            if item["code"] in seen:
                err(f"{section}: duplicate code '{item['code']}'")
            seen.append(item["code"])
            add(f"{section}.{item['code']}", item["expr"], want)
        return set(seen)

    gate_codes = codes("gates")
    codes("size_dependent_checks")
    exit_codes = codes("exit_rules")
    for x in card["exit_rules"]:
        if x["cadence"] not in en["exit_cadence"]:
            err(f"exit {x['code']}: cadence '{x['cadence']}' invalid")
    if "ranking" in card:
        add("ranking", card["ranking"]["expr"], "num")
    for f in card["universe"]["filters"]:
        add("universe.filter", f, "bool")
    for t in card["review_triggers"]:
        add("review_trigger", t, "bool")

    # sizing
    s = card["sizing"]
    methods = reg["sizing_methods"]
    if s["method"] not in methods:
        err(f"sizing.method '{s['method']}' not registered")
    else:
        need, have = set(methods[s["method"]]["params"]), set(s["params"])
        if need - have:
            err(f"sizing: missing params {sorted(need - have)}")
        if have - need:
            err(f"sizing: params {sorted(have - need)} do not belong to {s['method']}")
    add("sizing.formula", s["formula"], "num")
    if "revised_formula" in s:
        add("sizing.revised_formula", s["revised_formula"], "num")

    # proposed execution rule
    per = card["proposed_execution_rule"]
    add("per.entry_ref", per["entry_ref"], "num")
    add("per.entry_high", per["entry_high"], "num")
    add("per.target_qty", per["target_qty"], "qty")
    if "revised_target_qty" in per:
        add("per.revised_target_qty", per["revised_target_qty"], "qty")
    if per["on_exhausted"] not in en["on_exhausted"]:
        err(f"on_exhausted '{per['on_exhausted']}' invalid")
    if per["exit_execution"] not in en["exit_execution"]:
        err(f"exit_execution '{per['exit_execution']}' invalid")
    tr = per["tranches"]
    if [t["n"] for t in tr] != list(range(1, len(tr) + 1)):
        err("tranches must be numbered 1..N in order")
    wsum = sum(t["weight"] for t in tr)
    if not math.isclose(wsum, 1.0, abs_tol=1e-6):
        err(f"tranche weights sum to {wsum:.4f}, not 1")
    for t in tr:
        n = t["n"]
        if t["attempt_policy"] not in en["attempt_policy"]:
            err(f"tranche {n}: attempt_policy invalid")
        if t["recheck_failure"] not in en["recheck_failure"]:
            err(f"tranche {n}: recheck_failure invalid")
        if t["attempt_policy"] == "retry_window":
            for k in ("first_attempt_sessions_after_tranche_1", "retry_sessions"):
                if k not in t:
                    err(f"tranche {n}: retry_window needs {k}")
        if n == 1 and t["attempt_policy"] == "retry_window":
            err("tranche 1 cannot use retry_window")
        if n > 1 and "first_attempt_sessions_after_tranche_1" in t and tr[n - 2].get("first_attempt_sessions_after_tranche_1", 0) \
                + tr[n - 2].get("retry_sessions", 0) >= t["first_attempt_sessions_after_tranche_1"] and n > 2:
            err(f"tranche {n}: retry window of tranche {n-1} overlaps tranche {n}")
        for g in t["recheck_gates"]:
            if g not in gate_codes:
                err(f"tranche {n}: recheck_gates references unknown gate '{g}'")
        add(f"tranche{n}.limit", t["limit"], "num")
        add(f"tranche{n}.qty", t["qty"], "qty")
    if tr and tr[0]["attempt_policy"] == "every_session_until_ttl" and set(tr[0]["recheck_gates"]) != gate_codes:
        err("tranche 1 retries across new data, so it must recheck every gate on every attempt")
    if tr and tr[0]["attempt_policy"] == "single_session" and card["lifecycle"]["signal_ttl"]["value"] > 1 \
            and set(tr[0]["recheck_gates"]) != gate_codes and per["on_exhausted"] != "void_signal":
        err("a single-session tranche 1 that can outlive new data must recheck every gate")

    # stop
    st = card.get("stop")
    if st is not None:
        add("stop.initial", st["initial"], "num")
        add("stop.update", st["update"], "num")

    # cooldown, lifecycle, void events
    for x in card["cooldown"]["applies_after"]:
        if x not in exit_codes:
            err(f"cooldown.applies_after references unknown exit '{x}'")
    if card["lifecycle"]["signal_ttl"]["unit"] not in en["ttl_unit"]:
        err("lifecycle.signal_ttl.unit invalid")
    for v in card["signal_void_on"]:
        if v not in reg["void_events"]:
            err(f"signal_void_on '{v}' is not a registered void event")

    # hard cap: quantities must be bounded so an allowed higher fill cannot breach the cap
    for key in ("target_qty", "revised_target_qty"):
        if key in per and "hard_cap_value" not in per[key]:
            err(f"proposed_execution_rule.{key} must be bounded by hard_cap_value")

    # typecheck expressions
    chk = Checker(reg, card)
    for where, src, want in exprs:
        try:
            got = chk.type_of(Parser(tokenize(src)).parse())
        except ExprError as e:
            err(f"{where}: {e}")
            continue
        if want == "qty" and not is_qty(got):
            err(f"{where}: must yield integer shares (qty), yields {got}")
        elif want == "num" and not is_num(got):
            err(f"{where}: must be numeric, is {got}")
        elif want == "bool" and got != "bool":
            err(f"{where}: must be boolean, is {got}")

    # references: declaration, research-only, runtime-state assignment
    for r in chk.refs:
        if (r in feats or r in flags) and r not in dset:
            err(f"feature '{r}' used but not declared in card")
        if research_only(r):
            err(f"research_only feature '{r}' used in executable logic")
        rt = runtime.get(r)
        if rt and rt["owner"] == "derived":
            field = rt["card_field"]
            if field.startswith("tranches"):
                continue
            sect, key = field.split(".")
            if key not in card.get(sect, {}):
                err(f"runtime '{r}' is used but never assigned: card must define {field}")
        if rt and rt["owner"] == "stateful" and r in (
                "stop_in_force", "stop_prev", "highest_close_since_entry", "atr_pct_at_peak") and st is None:
            err(f"'{r}' is stop state but the card defines no stop")
    # a gate that waives on unknown may read only secondary features
    for g in card["gates"]:
        if g["unknown_blocks"] is False:
            gchk = Checker(reg, card)
            try:
                gchk.type_of(Parser(tokenize(g["expr"])).parse())
            except ExprError:
                continue
            material = sorted(r for r in gchk.refs if r in feats and r not in secondary)
            if material:
                err(f"gate {g['code']} waives on unknown but reads material input(s) {material}")
    if st is not None and "stop_in_force" not in chk.refs:
        err("stop defined but no exit rule tests stop_in_force (dead stop)")

    # corporate actions
    if card["corporate_action_policy"] not in reg["corporate_action_policies"]:
        err(f"corporate_action_policy '{card['corporate_action_policy']}' not registered")
    held = set(card["ca_state_held"])
    for h in held:
        if not runtime.get(h, {}).get("ca_state"):
            err(f"ca_state_held '{h}' is not a CA-state runtime value")
    for r in chk.refs:
        if runtime.get(r, {}).get("ca_state") and r not in held:
            err(f"'{r}' is CA-sensitive state but missing from ca_state_held")
    if "current_earmark_qty" not in held:
        err("ca_state_held must include current_earmark_qty")

    # benchmarks, AI inputs, validation
    for key in ("benchmark", "secondary_benchmark"):
        if key in card and card[key] not in reg["benchmarks"]:
            err(f"{key} '{card[key]}' not in benchmark registry")
    ai = card["ai_inputs"]
    if not ai["permitted"] and ai.get("declared_features"):
        err("ai_inputs.permitted is false but declared_features is non-empty")
    for f in ai.get("declared_features", []):
        if not feats.get(f, {}).get("ai_derived"):
            err(f"ai_inputs: '{f}' is not a registered AI-derived feature")
    v = card["validation"]
    if v["holdout_years"] >= v["evaluable_years"]:
        err("validation.holdout_years must be less than evaluable_years")

    # status-dependent completeness
    if status != "experimental":
        for p, val in card["sizing"]["params"].items():
            if val == "OPEN":
                err(f"sizing param '{p}' still OPEN at status {status}")
        for p, spec in card["params"].items():
            if spec["value"] == "CALIBRATE":
                err(f"param '{p}' still CALIBRATE at status {status}")
        for fn, spec in reg["functions"].items():
            if spec.get("status") == "placeholder":
                for where, src, _ in exprs:
                    if re.search(rf"\b{fn}\s*\(", str(src)):
                        err(f"{where}: placeholder function {fn}() not allowed at status {status}")

    # retired identifiers anywhere
    dep = set(reg["deprecated"])

    def walk(node):
        if isinstance(node, dict):
            for k, val in node.items():
                yield str(k); yield from walk(val)
        elif isinstance(node, list):
            for val in node:
                yield from walk(val)
        elif node is not None:
            yield str(node)
    for text in walk(card):
        for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text):
            if tok in dep:
                err(f"retired identifier '{tok}' present")
    return sorted(set(E))


def lint_paths(card_paths, registry_path, schema_path):
    reg = load_yaml(registry_path)
    reg_sha = sha256_file(registry_path)
    schema = json.load(open(schema_path))
    results, codes = {}, {}
    for p in card_paths:
        try:
            card = load_yaml(p)
            errs = lint(card, reg, reg_sha, schema)
            code = card.get("code") if isinstance(card, dict) else None
        except Exception as e:  # unreadable YAML, duplicate keys
            errs, code = [f"unreadable: {e}"], None
        if code:
            if code in codes:
                errs = errs + [f"duplicate strategy code '{code}' (also in {codes[code]})"]
            codes[code] = p
        results[p] = errs
    return results


def main(argv):
    reg_path = os.path.join(HERE, "registry.yaml")
    schema_path = os.path.join(HERE, "schemas", "card.schema.json")
    cards, it = [], iter(argv[1:])
    for a in it:
        if a == "--registry":
            reg_path = next(it)
        elif a == "--schema":
            schema_path = next(it)
        else:
            cards.append(a)
    if not cards:
        sdir = os.path.join(HERE, "strategies")
        cards = sorted(os.path.join(sdir, f) for f in os.listdir(sdir) if f.endswith(".yaml"))
    try:
        results = lint_paths(cards, reg_path, schema_path)
    except Exception as e:
        print(f"cannot load registry or schema: {e}")
        return 2
    bad = False
    for p, errs in results.items():
        print(f"{os.path.relpath(p)}: {'PASS' if not errs else f'{len(errs)} violation(s)'}")
        for e in errs:
            print(f"  - {e}")
        bad |= bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
