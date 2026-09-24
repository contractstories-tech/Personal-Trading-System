#!/usr/bin/env python3
"""Mechanical mutation analysis of reference_sim.py against the supplied golden cases.

The package's own "32/32 planted defects caught" figure measures hand-written re-implementations of
defects already found in review. This script instead applies small operator and constant mutations
to every function in reference_sim.py, one at a time, and reports which ones no golden case detects.

    python3 mutation_analysis.py /path/to/equity-spec-kit-r5.4

Mutations: < <-> <=, > <-> >=, + <-> -, * <-> /, and <-> or, and numeric constants (x1.1 for floats,
+1 for integers other than 0 and 1). Some survivors are equivalent mutants (rounding precision,
epsilons); read the survivor list rather than the score alone. Runtime: a few minutes.
"""
import ast
import collections
import copy
import os
import signal
import sys
import types

KIT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
os.chdir(KIT)
sys.path.insert(0, KIT)
import reference_sim as R  # noqa: E402
import test_golden as TG  # noqa: E402

SWAP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Add: ast.Sub, ast.Sub: ast.Add,
        ast.Mult: ast.Div, ast.Div: ast.Mult, ast.And: ast.Or, ast.Or: ast.And}


class Timeout(Exception):
    pass


def _alarm(*_):
    raise Timeout()


signal.signal(signal.SIGALRM, _alarm)


def sites(tree):
    """Every mutable node, identified by its position in a deterministic walk."""
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


def mutate(tree, site):
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


def detected():
    signal.alarm(2)
    try:
        return any(not TG.close(got, want, tol) for _, got, want, tol in TG.cases())
    except BaseException:          # a crash or a hang counts as detected, generously
        return True
    finally:
        signal.alarm(0)


def main():
    src = open("reference_sim.py").read()
    tree = ast.parse(src)
    lines = src.splitlines()
    originals = {k: getattr(R, k) for k in dir(R) if callable(getattr(R, k)) and not k.startswith("__")}
    survivors, killed = [], 0
    all_sites = sites(tree)
    for site in all_sites:
        mod = types.ModuleType("mutant")
        try:
            exec(compile(mutate(tree, site), "mutant", "exec"), mod.__dict__)
        except Exception:
            killed += 1
            continue
        for k in originals:
            if hasattr(mod, k):
                setattr(R, k, getattr(mod, k))
        # functions that call each other inside the mutant module must see the mutant too
        caught = detected()
        for k, v in originals.items():
            setattr(R, k, v)
        if caught:
            killed += 1
        else:
            survivors.append(site)
    n = len(all_sites)
    print(f"mutation sites: {n}   killed: {killed}   survived: {len(survivors)}  (raw score {killed / n:.0%})")
    print("survivors by function:", dict(collections.Counter(s[0] for s in survivors)))
    for fn, _, kind, ln in survivors:
        print(f"  {fn:18} {kind:5} L{ln}: {lines[ln - 1].strip()[:100]}")


if __name__ == "__main__":
    main()
