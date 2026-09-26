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


def test_worker_crash_is_infrastructure_error():
    assert worker_crash_is_infrastructure_error()


def main():
    ok = worker_crash_is_infrastructure_error()
    print(f"mutation infrastructure self-test: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
