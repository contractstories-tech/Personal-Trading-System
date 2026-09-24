#!/usr/bin/env python3
"""Mutation check for the executable references (audit C1). The planted-defect lists in test_golden.py and
test_features.py are regression tests for defects already found; this checks FIXTURE ADEQUACY instead.

Every comparison, arithmetic operator, and/or, and numeric constant in reference_sim.py and
reference_features.py is mutated one at a time (< <-> <=, > <-> >=, + <-> -, * <-> /, and <-> or, x1.1 or +1);
the module's golden cases must detect each mutant. A survivor fails the check unless it is listed, with a
reason, in golden/mutation_allowlist.yaml as an equivalent mutant (for example the rounding precision of an
output field). A new survivor therefore means a missing golden case - add the case, do not widen the list.

    python3 mutation_check.py            (a few minutes; exit 0 = no unlisted survivor)
    python3 mutation_check.py --list     prints every survivor with its allowlist status
"""
import ast
import copy
import os
import signal
import sys
import types

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SWAP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Add: ast.Sub, ast.Sub: ast.Add,
        ast.Mult: ast.Div, ast.Div: ast.Mult, ast.And: ast.Or, ast.Or: ast.And}


class _Timeout(Exception):
    pass


def _alarm(*_):
    raise _Timeout()


def _sites(tree):
    out = []
    for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
        for i, node in enumerate(ast.walk(fn)):
            if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in SWAP:
                out.append((fn.name, i, "cmp", node.lineno))
            elif isinstance(node, ast.BinOp) and type(node.op) in SWAP:
                out.append((fn.name, i, "bin", node.lineno))
            elif isinstance(node, ast.BoolOp) and type(node.op) in SWAP:
                out.append((fn.name, i, "bool", node.lineno))
            elif isinstance(node, ast.Constant) and type(node.value) in (int, float) and node.value not in (0, 1):
                out.append((fn.name, i, "const", node.lineno))
    return out


def _mutate(tree, site):
    fn_name, idx, kind, _ = site
    t = copy.deepcopy(tree)
    fn = next(n for n in t.body if isinstance(n, ast.FunctionDef) and n.name == fn_name)
    node = list(ast.walk(fn))[idx]
    if kind == "cmp":
        node.ops = [SWAP[type(node.ops[0])]()]
    elif kind in ("bin", "bool"):
        node.op = SWAP[type(node.op)]()
    else:
        node.value = node.value * 1.1 if isinstance(node.value, float) else node.value + 1
    return ast.fix_missing_locations(t)


def survivors(module_name, detect):
    mod = __import__(module_name)
    src = open(os.path.join(HERE, f"{module_name}.py")).read()
    tree, lines = ast.parse(src), src.splitlines()
    originals = {k: getattr(mod, k) for k in dir(mod) if callable(getattr(mod, k)) and not k.startswith("__")}
    out, sites = [], _sites(tree)
    for site in sites:
        m = types.ModuleType("mutant")
        m.__dict__.update({k: v for k, v in mod.__dict__.items() if k.startswith("__") is False})
        try:
            exec(compile(_mutate(tree, site), "mutant", "exec"), m.__dict__)
        except Exception:
            continue
        for k in originals:
            if hasattr(m, k):
                setattr(mod, k, getattr(m, k))
        signal.alarm(3)
        try:
            caught = detect()
        except BaseException:
            caught = True
        finally:
            signal.alarm(0)
            for k, v in originals.items():
                setattr(mod, k, v)
        if not caught:
            out.append({"module": module_name, "function": site[0], "kind": site[2],
                        "line": lines[site[3] - 1].strip()})
    return out, len(sites)


def main():
    signal.signal(signal.SIGALRM, _alarm)
    import test_golden as TG
    import test_features as TF
    allow = yaml.safe_load(open(os.path.join(HERE, "golden", "mutation_allowlist.yaml")))["equivalent_mutants"]
    key = lambda d: (d["module"], d["function"], d["kind"], d["line"])  # noqa: E731
    allowed = {}
    for a in allow:
        allowed[key(a)] = allowed.get(key(a), 0) + a.get("count", 1)
    found, total = [], 0
    for module, detect in (("reference_sim", lambda: any(not TG.close(g, w, t) for _, g, w, t in TG.cases())),
                           ("reference_features", lambda: any(not TG.close(g, w, 1e-6) for _, g, w in TF.cases()))):
        s, n = survivors(module, detect)
        found += s
        total += n
    counts = {}
    for s in found:
        counts[key(s)] = counts.get(key(s), 0) + 1
    unlisted = {k: c - allowed.get(k, 0) for k, c in counts.items() if c > allowed.get(k, 0)}
    stale = [k for k in allowed if k not in counts]
    print(f"mutation sites: {total}   survivors: {len(found)}   allowlisted equivalent: {len(found) - sum(unlisted.values())}"
          f"   unlisted: {sum(unlisted.values())}   raw score {1 - len(found) / total:.0%}")
    if "--list" in sys.argv:
        for k, c in sorted(counts.items()):
            print(f"  {'allowed ' if k not in unlisted else 'UNLISTED'} x{c} {k[0]}.{k[1]} {k[2]}: {k[3][:90]}")
    for k, c in sorted(unlisted.items()):
        print(f"UNLISTED SURVIVOR x{c}: {k[0]}.{k[1]} {k[2]}: {k[3][:100]}  -> add a golden case")
    for k in stale:
        print(f"note: allowlist entry no longer needed: {k[0]}.{k[1]} {k[2]}: {k[3][:80]}")
    sys.exit(1 if unlisted else 0)


if __name__ == "__main__":
    main()
