#!/usr/bin/env python3
"""speclint v4 - strategy-card compiler (Document 01 s8).

Stage 1  closed-schema validation against schemas/card.schema.json (unknown keys are errors;
         malformed shapes produce errors, never crashes).
Stage 2  semantic compilation against registry.yaml: registry pin by the canonical hash of the card's
         registry CLOSURE (the entries it uses, not the whole file), strategy class, data resolution and
         triggers, expression grammar and types, permitted date arguments (no expression can name a future
         session), reference integrity, materiality through composites, a structural hard-cap bound,
         runtime-state assignment, corporate-action completeness, void-event parameters, construction,
         and status-dependent completeness.

A card's status is NOT in the card (r5.5): it is the to_status of the latest lifecycle transition record in
lifecycle/transitions/ whose card_sha256 matches the card file. A card with no record is linted as
experimental and reported as unregistered.

A PASS means a card is WELL-FORMED. It does not mean it is CORRECT: Document 04's golden
cases establish that.

Usage:  python3 speclint.py [--registry registry.yaml] [--schema schemas/card.schema.json] [--closure] card.yaml ...
        --closure prints each card's current registry closure hash (to pin it after a deliberate change)
Exit:   0 = all pass, 1 = violations, 2 = unreadable registry/schema.
"""
import datetime as dt
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
    with open(path, encoding="utf-8") as fh:
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


def node_src(node):
    """Canonical text of a parsed expression node (used to check permitted arguments)."""
    k = node[0]
    if k in ("num", "id"):
        return node[1]
    if k == "call":
        return f"{node[1]}({', '.join(node_src(a) for a in node[2])})"
    if k == "neg":
        return f"-{node_src(node[1])}"
    if k == "not":
        return f"NOT {node_src(node[1])}"
    return f"({node_src(node[2])} {node[1]} {node_src(node[3])})"


class Checker:
    def __init__(self, reg, card):
        self.reg, self.card = reg, card
        self.params = set((card.get("params") or {}).keys())
        self.composites = set((card.get("composites") or {}).keys())
        self.refs, self.calls, self.enums = set(), set(), set()

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
                self.enums.add(ens)
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
            self.calls.add(name)
            if len(args) != len(fn["args"]):
                raise ExprError(f"{name}() takes {len(fn['args'])} args, got {len(args)}")
            allowed = fn.get("allowed_arguments")
            if allowed is not None:
                for a in args:
                    if node_src(a) not in allowed:
                        raise ExprError(f"{name}({node_src(a)}): argument not permitted; only {allowed} "
                                        f"(no expression may name a session after the evaluation)")
            ats = [self.type_of(a) for a in args]
            for want, got in zip(fn["args"], ats):
                ok = (want == got) or (want == "num" and is_num(got)) or (want == "qty" and is_qty(got))
                if not ok:
                    raise ExprError(f"{name}(): expected {want}, got {got}")
            if name in ("min", "max") and all(is_qty(t) for t in ats):
                return "qty"
            return fn["returns"]
        raise ExprError(f"bad node {kind}")


# ------------------------------------------------------------------ registry closure (audit A4)
# Blocks that define what every card's expressions mean. r5.5 also put every field enum (status, weekday,
# horizon ...) and valuation_transformative_actions in every closure, so adding a weekday re-pinned both cards
# (review of r5.5). An enum a card only uses as a field value is checked against the registry on every lint;
# adding a value to it cannot change what the card means, so it is not in the closure (r5.6).
GLOBAL_BLOCKS = ["evaluation_semantics", "window_conventions", "session_policy", "confidence_policy",
                 "cutoff_policy", "security_identity"]
RANKING_BLOCKS = ["cross_sectional_scoring"]      # only for cards that score a population


def card_expressions(card):
    """Every expression string in a card (for closure collection)."""
    out = [g["expr"] for g in card.get("gates", [])] + [x["expr"] for x in card.get("size_dependent_checks", [])]
    out += [x["expr"] for x in card.get("exit_rules", [])] + list(card.get("review_triggers", []))
    out += list(card.get("universe", {}).get("filters", []))
    if "ranking" in card:
        out.append(card["ranking"]["expr"])
    sz = card.get("sizing", {})
    out += [sz[k] for k in ("formula", "revised_formula") if k in sz]
    per = card.get("proposed_execution_rule", {})
    out += [per[k] for k in ("entry_ref", "entry_high", "target_qty", "revised_target_qty") if k in per]
    for t in per.get("tranches", []):
        out += [t["limit"], t["qty"]]
    st = card.get("stop") or {}
    out += [st[k] for k in ("initial", "update") if k in st]
    return out


def registry_closure(card, reg):
    """The canonical subset of the registry a card depends on. Editing anything outside it (a new feature for
    another strategy, a comment, an unrelated sector code) cannot change what this card means, so it does not
    change the card's pin; editing anything inside it does."""
    chk = Checker(reg, card)
    for src in card_expressions(card):
        try:
            chk.type_of(Parser(tokenize(src)).parse())
        except ExprError:
            pass
    feats = set(card.get("features", []))
    enums = set(chk.enums)                         # enum literals and enum-typed arguments in expressions
    blocks = list(GLOBAL_BLOCKS)
    if card.get("selection_method") == "rank_and_gate" or card.get("composites"):
        blocks += RANKING_BLOCKS
    for f in feats:
        entry = reg["features"].get(f, {})
        t = str(entry.get("type", ""))
        if t.startswith("enum:"):
            enums.add(t[5:])
        blocks += [b for b in entry.get("depends_on", []) if b not in blocks]
    runtime = (chk.refs | set(card.get("ca_state_held", [])) | {"hard_cap_value", "provisional_value_cr"})
    if card.get("stop"):
        runtime |= {"stop_in_force", "stop_prev", "highest_close_since_entry", "atr_pct_at_peak", "atr_pct_at_signal"}
    triggers = {t["trigger"] for t in card.get("evaluation", {}).get("entry_triggers", [])}
    triggers.add(card.get("evaluation", {}).get("risk_trigger", {}).get("trigger"))
    closure = {
        "features": {f: reg["features"][f] for f in sorted(feats) if f in reg["features"]},
        "forensic_flags": reg.get("forensic_flags", {}) if feats & {"forensic_flag_count", "forensic_coverage_pct"} else {},
        "secondary_features": sorted(feats & set(reg.get("secondary_features", []))),
        "functions": {f: reg["functions"][f] for f in sorted(chk.calls) if f in reg["functions"]},
        "runtime": {r: reg["runtime"][r] for r in sorted(runtime) if r in reg["runtime"]},
        "enums": {e: reg["enums"][e] for e in sorted(enums) if e in reg["enums"]},
        "strategy_class": reg["strategy_classes"].get(card.get("strategy_class")),
        "data_resolution": reg["data_resolutions"].get(card.get("data_resolution")),
        "triggers": {t: reg["triggers"][t] for t in sorted(x for x in triggers if x) if t in reg["triggers"]},
        "sizing_method": reg["sizing_methods"].get(card.get("sizing", {}).get("method")),
        "void_events": {v: reg["void_events"][v] for v in sorted(card.get("signal_void_on", [])) if v in reg["void_events"]},
        "corporate_action_policy": reg["corporate_action_policies"].get(card.get("corporate_action_policy")),
        "benchmarks": sorted(b for b in (card.get("benchmark"), card.get("secondary_benchmark")) if b in reg["benchmarks"]),
        "sector_codes": sorted(x for x in card.get("universe", {}).get("exclude_sectors", []) if x in reg["sector_codes"]),
    }
    for b in blocks:
        closure[b] = reg.get(b)
    return closure


def closure_sha256(card, reg):
    body = json.dumps(registry_closure(card, reg), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def _is_cap_floor(a, limits):
    """floor(hard_cap_value / <limit>)"""
    return (a[0] == "call" and a[1] == "floor" and len(a[2]) == 1 and a[2][0][0] == "arith" and a[2][0][1] == "/"
            and a[2][0][2] == ("id", "hard_cap_value") and a[2][0][3][0] == "id" and a[2][0][3][1] in limits)


def _caps_quantity(node, limits=("entry_high", "tranche_limit")):
    """True iff node is min(...) with floor(hard_cap_value / <limit>) in its chain of min() arguments, so the
    quantity can never exceed the cap at the worst permitted fill (audit B2: r5.4 tested a substring)."""
    if node[0] != "call" or node[1] != "min":
        return False
    return any(_is_cap_floor(a, limits) or _caps_quantity(a, limits) for a in node[2])


# ------------------------------------------------------------------ semantic stage
def lint(card, reg, schema, status="experimental"):
    """status comes from the card's lifecycle record (lint_paths), never from the card."""
    if not isinstance(card, dict):
        return ["card: must be a mapping"]
    E = schema_errors(card, schema, schema)
    if E:
        return sorted(set(E))          # semantic stage only runs on a well-shaped card
    err = E.append
    en = reg["enums"]
    feats, flags, runtime = reg["features"], reg.get("forensic_flags", {}), reg["runtime"]
    declared = card["features"]
    dset = set(declared)

    # lineage: a card's code must belong to its lineage (holdout exposure is tracked per lineage)
    lin = card["lineage"]["code"]
    if not card["code"].startswith(lin + "_v"):
        err(f"code '{card['code']}' does not belong to lineage '{lin}'")
    if lin in card["lineage"]["derived_from"]:
        err(f"lineage '{lin}' cannot derive from itself")

    # materiality: a material input may never be penalised, and never feed a waivable gate
    secondary = set(reg.get("secondary_features", []))
    for f, b in card["unknown_overrides"].items():
        if b == "penalise" and f not in secondary:
            err(f"unknown_override '{f}: penalise' - '{f}' is material; its absence must block or exclude")

    # materiality reaches ranking (r5.6): a composite may tolerate missing SECONDARY inputs only
    for name, comp in card.get("composites", {}).items():
        material = [i["code"] for i in comp["inputs"] if i["code"] not in secondary]
        if comp["min_inputs_known"] < len(material):
            err(f"composite '{name}': min_inputs_known {comp['min_inputs_known']} would rank a security with a material "
                f"input missing ({', '.join(material)} are material); it must be at least {len(material)}")
        if comp["min_inputs_known"] > len(comp["inputs"]):
            err(f"composite '{name}': min_inputs_known {comp['min_inputs_known']} exceeds its {len(comp['inputs'])} inputs")
    for f in declared:
        for b in feats.get(f, {}).get("depends_on", []):
            if b not in reg:
                err(f"registry feature '{f}' depends_on unknown registry block '{b}'")

    # registry pin: the closure, not the file
    if card["registry"]["version"].split(".")[0] != str(reg["registry_version"]).split(".")[0]:
        err(f"registry.version {card['registry']['version']} is not compatible with registry {reg['registry_version']}")
    want = closure_sha256(card, reg)
    if card["registry"]["closure_sha256"] != want:
        err(f"registry.closure_sha256 does not match: an entry this card uses has changed (current closure {want}); "
            f"re-validate the card, and version it if its meaning changed")
    if status not in en["status"]:
        err(f"status '{status}' not registered")

    # identity and vocabularies
    for field, enum in (("trade_direction", "trade_direction"), ("horizon", "horizon"),
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
                if cal["sampling"] not in en["calibration_sampling"]:
                    err(f"param '{p}': calibration sampling '{cal['sampling']}' not registered")

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
        if x["cadence"] == "weekly" and x.get("weekday") not in en["weekday"]:
            err(f"exit {x['code']}: a weekly exit must name its weekday (evaluation_semantics.weekly)")
        if x["cadence"] == "daily" and "weekday" in x:
            err(f"exit {x['code']}: a daily exit takes no weekday")
        if x.get("on_out_of_domain", "fire") not in en["on_out_of_domain"]:
            err(f"exit {x['code']}: on_out_of_domain '{x['on_out_of_domain']}' invalid")
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

    # construction (audit A3): capacity is part of the hypothesis
    con = card["construction"]
    if con["capacity_order"] not in en["capacity_order"]:
        err(f"construction.capacity_order '{con['capacity_order']}' not registered")
    elif card["selection_method"] == "gate_only" and con["capacity_order"] == "rank":
        err("construction.capacity_order rank needs a ranking; a gate_only card uses earliest_signal")
    elif card["selection_method"] == "rank_and_gate" and con["capacity_order"] != "rank":
        err("construction.capacity_order: a rank_and_gate card fills scarce capacity by its rank")
    if con["residual_cash"] not in en["residual_cash"]:
        err(f"construction.residual_cash '{con['residual_cash']}' not registered")

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
    vp = card.get("void_parameters", {})
    for v in card["signal_void_on"]:
        if v not in reg["void_events"]:
            err(f"signal_void_on '{v}' is not a registered void event")
            continue
        need = set(reg["void_events"][v].get("parameters", []))
        have = set(vp.get(v, {}))
        if need - have:
            err(f"void_parameters.{v} missing {sorted(need - have)} (audit C9: thresholds are declared, never borrowed by gate number)")
        if have - need:
            err(f"void_parameters.{v} has {sorted(have - need)}, which the event does not take")
    for v in vp:
        if v not in card["signal_void_on"]:
            err(f"void_parameters.{v} given for an event the card does not use")

    # hard cap: quantities must be bounded so an allowed higher fill cannot breach the cap - structurally
    for key in ("target_qty", "revised_target_qty"):
        if key in per:
            try:
                ok = _caps_quantity(Parser(tokenize(per[key])).parse())
            except (ExprError, IndexError, TypeError):
                ok = False
            if not ok:
                err(f"proposed_execution_rule.{key} must be min(..., floor(hard_cap_value / entry_high or tranche_limit), ...) "
                    f"so it is bounded by hard_cap_value at the worst permitted fill")

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
    # a gate that waives on unknown may read only secondary features - including through a composite
    comps = card["composites"]
    for g in card["gates"]:
        if g["unknown_blocks"] is False:
            gchk = Checker(reg, card)
            try:
                gchk.type_of(Parser(tokenize(g["expr"])).parse())
            except ExprError:
                continue
            reads = set(gchk.refs)
            for cn in gchk.refs & set(comps):
                reads |= {i["code"] for i in comps[cn]["inputs"]}
            material = sorted(r for r in reads if r in feats and r not in secondary)
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
        if card["construction"]["max_positions"] == "OPEN":
            err(f"construction.max_positions still OPEN at status {status}")
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


# ------------------------------------------------------------------ lifecycle status (M17 is the only authority)
EVIDENCE_FILES = {
    "linter_report_sha256": "linter_report_path",
    "golden_case_report_sha256": "golden_case_report_path",
    "validation_report_sha256": "validation_report_path",
}


def evidence_file_errors(rec, lifecycle_dir):
    """Verify every hash-bearing lifecycle evidence reference against the exact file on disk."""
    out = []
    base = os.path.realpath(lifecycle_dir)
    ev = rec.get("evidence", {})
    for sha_key, path_key in EVIDENCE_FILES.items():
        if sha_key not in ev:
            continue
        rel = ev.get(path_key)
        if not rel:
            out.append(f"lifecycle/{rec.get('_file', '?')}: {sha_key} has no {path_key}")
            continue
        if os.path.isabs(rel):
            out.append(f"lifecycle/{rec.get('_file', '?')}: {path_key} must be relative to the lifecycle directory")
            continue
        path = os.path.realpath(os.path.join(base, *str(rel).replace('\\', '/').split('/')))
        try:
            if os.path.commonpath([base, path]) != base:
                out.append(f"lifecycle/{rec.get('_file', '?')}: {path_key} escapes the lifecycle directory")
                continue
        except ValueError:
            out.append(f"lifecycle/{rec.get('_file', '?')}: {path_key} is outside the lifecycle directory")
            continue
        if not os.path.isfile(path):
            out.append(f"lifecycle/{rec.get('_file', '?')}: evidence file {rel!r} is missing")
            continue
        try:
            got = sha256_file(path)
        except OSError as exc:
            out.append(f"lifecycle/{rec.get('_file', '?')}: evidence file {rel!r} is unreadable: {exc}")
            continue
        if got != ev[sha_key]:
            out.append(f"lifecycle/{rec.get('_file', '?')}: evidence file {rel!r} sha256 {got} does not match recorded {ev[sha_key]}")
    return out

def load_transitions(lifecycle_dir):
    """Every transition record, validated against its schema. Returns (records, errors)."""
    tdir = os.path.join(lifecycle_dir, "transitions")
    sch = json.load(open(os.path.join(HERE, "schemas", "strategy_lifecycle_transition.schema.json"), encoding="utf-8"))
    recs, errs = [], []
    if not os.path.isdir(tdir):
        return recs, errs
    for f in sorted(os.listdir(tdir)):
        if not f.endswith(".json"):
            continue
        rec = json.load(open(os.path.join(tdir, f), encoding="utf-8"))
        e = schema_errors(rec, sch, sch, f"lifecycle/{f}")
        if e:
            errs += e
            continue
        bound = {**rec, "_file": f}
        file_errs = evidence_file_errors(bound, lifecycle_dir)
        if file_errs:
            errs += file_errs
            continue
        recs.append(bound)
    return recs, errs


FUTURE_TOLERANCE = dt.timedelta(minutes=5)


def decided_instant(rec):
    """decided_at as an aware UTC instant. r5.5 ordered records by the decided_at STRING, so
    2026-09-24T18:00:00+05:30 sorted after 2026-09-24T13:00:00Z although it is 30 minutes earlier (review of
    r5.5). A timestamp without an offset is refused: it names no instant."""
    s = str(rec["decided_at"])
    try:
        t = dt.datetime.fromisoformat(s[:-1] + "+00:00" if s.endswith("Z") else s)
    except ValueError:
        raise ValueError(f"lifecycle/{rec.get('_file', '?')}: decided_at {s!r} is not an RFC 3339 timestamp") from None
    if t.tzinfo is None:
        raise ValueError(f"lifecycle/{rec.get('_file', '?')}: decided_at {s!r} has no UTC offset")
    return t.astimezone(dt.timezone.utc)


def lifecycle_status(code, card_sha, records, now=None):
    """Resolve status in transition-ledger order and require strictly increasing decision instants.

    File/ledger order is authoritative for the chain. Timestamps validate chronology; they never reorder history.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    problems, chain = [], []
    for r in records:
        if r["strategy_code"] != code or r["card_sha256"] != card_sha:
            continue
        try:
            t = decided_instant(r)
        except ValueError as e:
            problems.append(str(e))
            continue
        if t > now + FUTURE_TOLERANCE:
            problems.append(f"lifecycle/{r['_file']}: decided_at {r['decided_at']} is in the future")
        chain.append((t, r))
    for (t1, r1), (t2, r2) in zip(chain, chain[1:]):
        if t2 <= t1:
            relation = "same instant as" if t2 == t1 else "earlier than"
            problems.append(f"lifecycle/{r2['_file']}: decided_at {r2['decided_at']} is {relation} prior transition {r1['_file']} ({r1['decided_at']})")
    prev = "none"
    for _, r in chain:
        if r["from_status"] != prev:
            problems.append(f"lifecycle/{r['_file']}: from_status {r['from_status']} but the card was {prev}")
        prev = r["to_status"]
    if not chain:
        return None, None, problems
    return chain[-1][1]["to_status"], chain[-1][1]["_file"], problems


def lint_paths(card_paths, registry_path, schema_path, lifecycle_dir=None):
    reg = load_yaml(registry_path)
    schema = json.load(open(schema_path, encoding="utf-8"))
    records, rec_errs = load_transitions(lifecycle_dir or os.path.join(HERE, "lifecycle"))
    results, codes, statuses = {}, {}, {}
    for p in card_paths:
        try:
            card = load_yaml(p)
            code = card.get("code") if isinstance(card, dict) else None
            status, rec, chain_errs = lifecycle_status(code, sha256_file(p), records)
            errs = lint(card, reg, schema, status or "experimental") + chain_errs + rec_errs
            statuses[p] = (status or "unregistered - linted as experimental", rec)
        except Exception as e:  # unreadable YAML, duplicate keys
            errs, code = [f"unreadable: {e}"], None
        if code:
            if code in codes:
                errs = errs + [f"duplicate strategy code '{code}' (also in {codes[code]})"]
            codes[code] = p
        results[p] = errs
    lint_paths.statuses = statuses
    return results


def main(argv):
    reg_path = os.path.join(HERE, "registry.yaml")
    schema_path = os.path.join(HERE, "schemas", "card.schema.json")
    cards, it, show_closure = [], iter(argv[1:]), False
    for a in it:
        if a == "--registry":
            reg_path = next(it)
        elif a == "--schema":
            schema_path = next(it)
        elif a == "--closure":
            show_closure = True
        else:
            cards.append(a)
    if not cards:
        sdir = os.path.join(HERE, "strategies")
        cards = sorted(os.path.join(sdir, f) for f in os.listdir(sdir) if f.endswith(".yaml"))
    if show_closure:
        reg = load_yaml(reg_path)
        for p in cards:
            print(f"{os.path.relpath(p)}: closure_sha256 {closure_sha256(load_yaml(p), reg)}")
        return 0
    try:
        results = lint_paths(cards, reg_path, schema_path)
    except Exception as e:
        print(f"cannot load registry or schema: {e}")
        return 2
    bad = False
    for p, errs in results.items():
        st, rec = lint_paths.statuses.get(p, ("?", None))
        where = f"status {st}" + (f", lifecycle/{rec}" if rec else "")
        print(f"{os.path.relpath(p)}: {'PASS' if not errs else f'{len(errs)} violation(s)'} ({where})")
        for e in errs:
            print(f"  - {e}")
        bad |= bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):   # UTF-8 output whatever the console or pipe (Windows defaults to cp1252)
        _s.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv))
