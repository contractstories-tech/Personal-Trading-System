#!/usr/bin/env python3
"""Mutation harness regressions: worker/process failures are infrastructure errors, never mutant kills."""
import os
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KIT)
import mutation_check as M  # noqa: E402


def _forced_worker_failure(env_name):
    old = os.environ.get(env_name)
    os.environ[env_name] = "1"
    try:
        results, infra = M._run_range("reference_engine", 0, 1)
    finally:
        if old is None:
            os.environ.pop(env_name, None)
        else:
            os.environ[env_name] = old
    return results.get(0) == "infrastructure_error" and len(infra) == 1 and infra[0]["exit_code"] == 7


def worker_crash_is_infrastructure_error():
    # Both a death before any result and a non-zero exit after the final reported result are infrastructure faults.
    return _forced_worker_failure("EOS_MUTATION_SELF_KILL") and _forced_worker_failure("EOS_MUTATION_SELF_KILL_AFTER")


def build_failure_is_infrastructure_error():
    """r5.10: r5.7-r5.9 counted a mutant that could not be BUILT as killed, which hid all 84 reference_engine
    mutants. Reproduce that harness defect with the hook and require infrastructure_error, not a kill."""
    old = os.environ.get("EOS_MUTATION_BREAK_BUILD")
    os.environ["EOS_MUTATION_BREAK_BUILD"] = "1"
    try:
        results, infra = M._run_range("reference_engine", 0, 1)
    finally:
        if old is None:
            os.environ.pop("EOS_MUTATION_BREAK_BUILD", None)
        else:
            os.environ["EOS_MUTATION_BREAK_BUILD"] = old
    return results.get(0) == "infrastructure_error" and infra and infra[0]["exit_code"] == 3 and \
        "could not be built" in infra[0]["detail"]


def every_mutant_builds():
    """Every mutation site of every reference module builds into a module that defines its functions."""
    import importlib
    for name in ("reference_sim", "reference_features", "reference_engine"):
        mod = importlib.import_module(name)
        tree, _, sites = M._load(name)
        for site in sites:
            m = M.build_mutant(mod, tree, site)
            if not callable(getattr(m, site[0].split(".")[0], None)):
                return False
    return True


CHECKS = [("worker crash is infrastructure_error", worker_crash_is_infrastructure_error),
          ("mutant build failure is infrastructure_error, never a kill", build_failure_is_infrastructure_error),
          ("every mutant of every reference module builds", every_mutant_builds)]


def test_worker_crash_is_infrastructure_error():
    assert worker_crash_is_infrastructure_error()


def test_build_failure_is_infrastructure_error():
    assert build_failure_is_infrastructure_error()


def test_every_mutant_builds():
    assert every_mutant_builds()


def main():
    ok = True
    for name, fn in CHECKS:
        r = bool(fn())
        ok &= r
        print(f"{'ok  ' if r else 'FAIL'}  {name}")
    print(f"mutation infrastructure self-test: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):   # UTF-8 output whatever the console or pipe (Windows defaults to cp1252)
        _s.reconfigure(encoding="utf-8")
    sys.exit(main())
