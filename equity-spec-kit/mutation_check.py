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
    python3 mutation_check.py --jobs N   worker processes (default: CPU count)

Cross-platform (r5.6). r5.5 bounded each mutant with signal.SIGALRM, which does not exist on Windows. Mutants now
run in worker processes (this file with --worker) that report one line per mutant; the parent enforces the
per-mutant time limit by watching for that line and kills a worker that stops reporting. A mutant that hangs
counts as detected, as before, and the worker is restarted after it. No signals, so it runs the same on Windows.
"""
import ast
import copy
import os
import queue
import subprocess
import sys
import threading
import types
from concurrent.futures import ThreadPoolExecutor

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SWAP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Add: ast.Sub, ast.Sub: ast.Add,
        ast.Mult: ast.Div, ast.Div: ast.Mult, ast.And: ast.Or, ast.Or: ast.And}


MUTANT_SECONDS = 10     # a mutant that has not finished its golden cases by then counts as detected
STARTUP_SECONDS = 120   # a worker's imports and golden-file loading
TAG = "@@mutant"


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


def _detectors():
    import test_golden as TG
    import test_features as TF
    return {"reference_sim": lambda: any(not TG.close(g, w, t) for _, g, w, t in TG.cases()),
            "reference_features": lambda: any(not TG.close(g, w, 1e-6) for _, g, w in TF.cases())}


def _load(module_name):
    src = open(os.path.join(HERE, f"{module_name}.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    return tree, src.splitlines(), _sites(tree)


def worker(module_name, start, stop):
    """Runs mutants start..stop-1 of one module in this process; prints '@@mutant <index> <caught 0|1>' as each
    finishes. Any exception from a mutant, including one raised while building it, counts as detected."""
    detect = _detectors()[module_name]
    mod = __import__(module_name)
    tree, _, sites = _load(module_name)
    originals = {k: getattr(mod, k) for k in dir(mod) if callable(getattr(mod, k)) and not k.startswith("__")}
    for i in range(start, stop):
        m = types.ModuleType("mutant")
        m.__dict__.update({k: v for k, v in mod.__dict__.items() if k.startswith("__") is False})
        try:
            exec(compile(_mutate(tree, sites[i]), "mutant", "exec"), m.__dict__)
        except Exception:
            print(f"{TAG} {i} 1", flush=True)
            continue
        for k in originals:
            if hasattr(m, k):
                setattr(mod, k, getattr(m, k))
        try:
            caught = detect()
        except BaseException:
            caught = True
        finally:
            for k, v in originals.items():
                setattr(mod, k, v)
        print(f"{TAG} {i} {int(bool(caught))}", flush=True)


def _run_range(module_name, start, stop):
    """Drives workers over [start, stop): returns {index: caught}. A worker silent for MUTANT_SECONDS is killed,
    the mutant it was running is recorded as detected (it hung), and a new worker resumes after it."""
    results = {}
    nxt = start
    while nxt < stop:
        proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--worker", module_name, str(nxt), str(stop)],
                                cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        lines = queue.Queue()
        threading.Thread(target=lambda: ([lines.put(x) for x in proc.stdout], lines.put(None)), daemon=True).start()
        limit = STARTUP_SECONDS + MUTANT_SECONDS
        while True:
            try:
                line = lines.get(timeout=limit)
            except queue.Empty:
                proc.kill()
                proc.wait()
                results[nxt] = True        # hung: detected
                nxt += 1
                break
            if line is None:               # worker exited
                proc.wait()
                if nxt < stop:             # it died on this mutant (e.g. a crash outside Python): detected
                    results[nxt] = True
                    nxt += 1
                break
            if line.startswith(TAG):
                _, i, caught = line.split()
                results[int(i)] = caught == "1"
                nxt = int(i) + 1
                limit = MUTANT_SECONDS
                if nxt >= stop:
                    proc.wait()
                    break
        proc.stdout.close()
    return results


def survivors(module_name, jobs):
    _, lines, sites = _load(module_name)
    n = len(sites)
    size = max(1, -(-n // (jobs * 3)))
    ranges = [(a, min(a + size, n)) for a in range(0, n, size)]
    results = {}
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        for r in ex.map(lambda ab: _run_range(module_name, *ab), ranges):
            results.update(r)
    assert sorted(results) == list(range(n)), "every mutant must report"
    out = [{"module": module_name, "function": sites[i][0], "kind": sites[i][2],
            "line": lines[sites[i][3] - 1].strip()} for i in range(n) if not results[i]]
    return out, n


def main():
    jobs = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else (os.cpu_count() or 2)
    allow = yaml.safe_load(open(os.path.join(HERE, "golden", "mutation_allowlist.yaml"), encoding="utf-8"))["equivalent_mutants"]
    key = lambda d: (d["module"], d["function"], d["kind"], d["line"])  # noqa: E731
    allowed = {}
    for a in allow:
        allowed[key(a)] = allowed.get(key(a), 0) + a.get("count", 1)
    found, total = [], 0
    for module in ("reference_sim", "reference_features"):
        s, n = survivors(module, jobs)
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
    for _s in (sys.stdout, sys.stderr):   # UTF-8 output whatever the console or pipe (Windows defaults to cp1252)
        _s.reconfigure(encoding="utf-8")
    if sys.argv[1:2] == ["--worker"]:
        worker(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
    else:
        main()
