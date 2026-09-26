#!/usr/bin/env python3
"""Mutation check for the executable references (audit C1). The planted-defect lists in test_golden.py and
test_features.py are regression tests for defects already found; this checks FIXTURE ADEQUACY instead.

Every comparison, arithmetic operator, and/or, and numeric constant in reference_sim.py,
reference_features.py and reference_engine.py (including Engine methods) is mutated one at a time (< <-> <=, > <-> >=, + <-> -, * <-> /, and <-> or, x1.1 or +1);
the module's golden cases must detect each mutant. A survivor fails the check unless it is listed, with a
reason, in golden/mutation_allowlist.yaml as an equivalent mutant (for example the rounding precision of an
output field). A new survivor therefore means a missing golden case - add the case, do not widen the list.

    python3 mutation_check.py            (a few minutes; exit 0 = no unlisted survivor)
    python3 mutation_check.py --list     prints every survivor with its allowlist status
    python3 mutation_check.py --jobs N   worker processes (default: CPU count)

Cross-platform (r5.6). r5.5 bounded each mutant with signal.SIGALRM, which does not exist on Windows. Mutants now
run in worker processes (this file with --worker) that report one line per mutant; the parent enforces the
per-mutant time limit by watching for that line and kills a worker that stops reporting. A mutant-induced timeout
is a distinct ``timeout`` result and still counts as detected; an unexpected worker exit, malformed worker output or
worker initialisation failure is ``infrastructure_error`` and fails the campaign. No signals, so it runs the same on Windows.
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


def _function_nodes(tree):
    """Functions in mutation scope: all top-level functions, plus Engine methods in reference_engine.py."""
    out = [(n.name, n) for n in tree.body if isinstance(n, ast.FunctionDef)]
    eng = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Engine"), None)
    if eng is not None:
        out += [(f"Engine.{n.name}", n) for n in eng.body if isinstance(n, ast.FunctionDef)]
    return out


def _sites(tree):
    out = []
    for qualname, fn in _function_nodes(tree):
        for i, node in enumerate(ast.walk(fn)):
            if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in SWAP:
                out.append((qualname, i, "cmp", node.lineno))
            elif isinstance(node, ast.BinOp) and type(node.op) in SWAP:
                out.append((qualname, i, "bin", node.lineno))
            elif isinstance(node, ast.BoolOp) and type(node.op) in SWAP:
                out.append((qualname, i, "bool", node.lineno))
            elif isinstance(node, ast.Constant) and type(node.value) in (int, float) and node.value not in (0, 1):
                out.append((qualname, i, "const", node.lineno))
    return out


def _mutate(tree, site):
    qualname, idx, kind, _ = site
    t = copy.deepcopy(tree)
    fn = dict(_function_nodes(t))[qualname]
    node = list(ast.walk(fn))[idx]
    if kind == "cmp":
        node.ops = [SWAP[type(node.ops[0])]() ]
    elif kind in ("bin", "bool"):
        node.op = SWAP[type(node.op)]()
    else:
        node.value = node.value * 1.1 if isinstance(node.value, float) else node.value + 1
    return ast.fix_missing_locations(t)


def _detectors():
    import test_golden as TG
    import test_features as TF
    import test_card_golden as TC
    import test_pipeline as TP
    return {"reference_sim": lambda: any(not TG.close(g, w, t) for _, g, w, t in TG.cases()),
            "reference_features": lambda: any(not TG.close(g, w, 1e-6) for _, g, w in TF.cases()),
            "reference_engine": lambda: bool(TC.run(verbose=False) or TP.run(verbose=False) or
                                             (not TC.engine_enforces_the_cap_whatever_the_card_says()))}


def _load(module_name):
    src = open(os.path.join(HERE, f"{module_name}.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    return tree, src.splitlines(), _sites(tree)


def mutant_namespace(mod):
    """The globals a mutant is built in: the reference module's own, dunders included (r5.10).

    r5.7-r5.9 dropped every ``__``-prefixed name, so ``reference_engine.py`` (which reads ``__file__`` at import)
    raised NameError while being BUILT, and each of its 84 mutants was reported as killed without ever running."""
    ns = dict(mod.__dict__)
    if os.environ.get("EOS_MUTATION_BREAK_BUILD") == "1":      # self-test hook: reproduce the r5.7-r5.9 defect
        ns = {k: v for k, v in ns.items() if not k.startswith("__")}
    return ns


def build_mutant(mod, tree, site):
    m = types.ModuleType("mutant")
    m.__dict__.update(mutant_namespace(mod))
    exec(compile(_mutate(tree, site), mod.__file__, "exec"), m.__dict__)
    return m


def worker(module_name, start, stop):
    """Run mutants and report one explicit semantic outcome per mutant.

    Exceptions raised while a mutant RUNS against the goldens count as ``killed``. A mutant that cannot be BUILT is
    an infrastructure failure, never a kill: the operator swaps here only change function bodies, so building can
    fail only because the harness is broken. The worker then exits with code 3 and the parent reports
    ``infrastructure_error`` with the reason (r5.10).
    """
    detect = _detectors()[module_name]
    mod = __import__(module_name)
    tree, _, sites = _load(module_name)
    originals = {k: getattr(mod, k) for k in dir(mod) if callable(getattr(mod, k)) and not k.startswith("__")}
    for i in range(start, stop):
        if os.environ.get("EOS_MUTATION_SELF_KILL") == "1":
            os._exit(7)
        try:
            m = build_mutant(mod, tree, sites[i])
        except Exception as exc:
            sys.stderr.write(f"mutant {i} of {module_name} could not be built: {type(exc).__name__}: {exc}\n")
            sys.stderr.flush()
            os._exit(3)
        for k in originals:
            if hasattr(m, k):
                setattr(mod, k, getattr(m, k))
        try:
            try:
                caught = detect()
                outcome = "killed" if caught else "survived"
            except BaseException:
                # A mutant that makes the executable reference raise under a previously valid golden is killed.
                outcome = "killed"
        finally:
            for k, v in originals.items():
                setattr(mod, k, v)
        print(f"{TAG} {i} {outcome}", flush=True)
    # Regression hook: prove that a worker which reports its last mutant and then dies is still infrastructure
    # failure, not a clean campaign. Production runs never set this environment variable.
    if os.environ.get("EOS_MUTATION_SELF_KILL_AFTER") == "1":
        os._exit(7)


def _run_range(module_name, start, stop):
    """Drive workers over [start, stop), preserving timeout vs infrastructure failure."""
    results, infra = {}, []
    nxt = start
    while nxt < stop:
        proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--worker", module_name, str(nxt), str(stop)],
                                cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        lines = queue.Queue()
        threading.Thread(target=lambda: ([lines.put(x) for x in proc.stdout], lines.put(None)), daemon=True).start()
        limit = STARTUP_SECONDS + MUTANT_SECONDS
        while True:
            try:
                line = lines.get(timeout=limit)
            except queue.Empty:
                proc.kill(); proc.wait()
                results[nxt] = "timeout"
                nxt += 1
                break
            if line is None:
                proc.wait()
                if nxt < stop:
                    err = proc.stderr.read().strip() if proc.stderr else ""
                    results[nxt] = "infrastructure_error"
                    infra.append({"module": module_name, "index": nxt, "exit_code": proc.returncode,
                                  "detail": err[-500:] or "worker exited before reporting a result"})
                    nxt += 1
                break
            if not line.startswith(TAG):
                continue
            parts = line.split()
            if len(parts) != 3 or parts[2] not in {"killed", "survived"}:
                proc.kill(); proc.wait()
                results[nxt] = "infrastructure_error"
                infra.append({"module": module_name, "index": nxt, "exit_code": proc.returncode,
                              "detail": f"malformed worker output: {line.strip()!r}"})
                nxt += 1
                break
            _, i, outcome = parts
            try:
                i = int(i)
            except ValueError:
                proc.kill(); proc.wait()
                results[nxt] = "infrastructure_error"
                infra.append({"module": module_name, "index": nxt, "exit_code": proc.returncode,
                              "detail": f"malformed mutant index: {line.strip()!r}"})
                nxt += 1
                break
            if i != nxt:
                proc.kill(); proc.wait()
                results[nxt] = "infrastructure_error"
                infra.append({"module": module_name, "index": nxt, "exit_code": proc.returncode,
                              "detail": f"worker reported mutant {i}, expected {nxt}"})
                nxt += 1
                break
            results[i] = outcome
            nxt = i + 1
            limit = MUTANT_SECONDS
            if nxt >= stop:
                proc.wait()
                if proc.returncode != 0:
                    err = proc.stderr.read().strip() if proc.stderr else ""
                    results[i] = "infrastructure_error"
                    infra.append({"module": module_name, "index": i, "exit_code": proc.returncode,
                                  "detail": err[-500:] or "worker exited non-zero after its final result"})
                break
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
    return results, infra


def survivors(module_name, jobs):
    _, lines, sites = _load(module_name)
    n = len(sites)
    size = max(1, -(-n // (jobs * 3)))
    ranges = [(a, min(a + size, n)) for a in range(0, n, size)]
    results, infra = {}, []
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        for r, e in ex.map(lambda ab: _run_range(module_name, *ab), ranges):
            results.update(r); infra += e
    missing = sorted(set(range(n)) - set(results))
    if missing:
        infra.append({"module": module_name, "index": missing[0], "exit_code": None,
                      "detail": f"{len(missing)} mutant(s) did not report"})
        for i in missing:
            results[i] = "infrastructure_error"
    out = [{"module": module_name, "function": sites[i][0], "kind": sites[i][2],
            "line": lines[sites[i][3] - 1].strip()} for i in range(n) if results[i] == "survived"]
    counts = {name: sum(v == name for v in results.values())
              for name in ("killed", "survived", "timeout", "infrastructure_error")}
    return out, n, counts, infra


def main():
    jobs = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else (os.cpu_count() or 2)
    allow = yaml.safe_load(open(os.path.join(HERE, "golden", "mutation_allowlist.yaml"), encoding="utf-8"))["equivalent_mutants"]
    key = lambda d: (d["module"], d["function"], d["kind"], d["line"])  # noqa: E731
    allowed = {}
    for a in allow:
        allowed[key(a)] = allowed.get(key(a), 0) + a.get("count", 1)
    found, total, outcome_counts, infrastructure = [], 0, {}, []
    for module in ("reference_sim", "reference_features", "reference_engine"):
        surv, n, counts, infra = survivors(module, jobs)
        found += surv
        total += n
        infrastructure += infra
        for k, v in counts.items():
            outcome_counts[k] = outcome_counts.get(k, 0) + v
    counts = {}
    for s in found:
        counts[key(s)] = counts.get(key(s), 0) + 1
    unlisted = {k: c - allowed.get(k, 0) for k, c in counts.items() if c > allowed.get(k, 0)}
    stale = [k for k in allowed if k not in counts]
    equivalent = len(found) - sum(unlisted.values())
    detected = outcome_counts.get("killed", 0) + outcome_counts.get("timeout", 0)
    print(f"mutation sites: {total}   killed: {outcome_counts.get('killed', 0)}   timeout: {outcome_counts.get('timeout', 0)}"
          f"   survivors: {len(found)}   equivalent: {equivalent}   unlisted: {sum(unlisted.values())}"
          f"   infrastructure_error: {outcome_counts.get('infrastructure_error', 0)}   detected score {detected / total:.0%}")
    if "--list" in sys.argv:
        for k, c in sorted(counts.items()):
            print(f"  {'allowed ' if k not in unlisted else 'UNLISTED'} x{c} {k[0]}.{k[1]} {k[2]}: {k[3][:90]}")
    for k, c in sorted(unlisted.items()):
        print(f"UNLISTED SURVIVOR x{c}: {k[0]}.{k[1]} {k[2]}: {k[3][:100]}  -> add a golden case")
    for e in infrastructure:
        print(f"INFRASTRUCTURE_ERROR: {e['module']} mutant {e['index']} exit={e['exit_code']}: {e['detail']}")
    for k in stale:
        print(f"note: allowlist entry no longer needed: {k[0]}.{k[1]} {k[2]}: {k[3][:80]}")
    sys.exit(1 if unlisted or infrastructure else 0)


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):   # UTF-8 output whatever the console or pipe (Windows defaults to cp1252)
        _s.reconfigure(encoding="utf-8")
    if sys.argv[1:2] == ["--worker"]:
        worker(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
    else:
        main()
