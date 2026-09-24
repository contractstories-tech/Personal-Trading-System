#!/usr/bin/env python3
"""Runs every contract command with THIS interpreter and prints one line per command (r5.6).

    python run_all.py                     every command; exit 0 = all passed
    python run_all.py --require-parquet   also fail if the Parquet codec could not run (the warehouse machine)
    python run_all.py --quick             skip mutation_check.py (the slowest)
    python run_all.py --pytest            also run the pytest entry points

Same on Windows (py -3.12 run_all.py), Linux and macOS: no shell syntax, no 'python3' on the PATH needed. Each
command's output is kept in run_all.log next to this file, which is what to send back when something fails.
"""
import glob
import os
import platform
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def commands(argv):
    doc03 = sorted(glob.glob(os.path.join(HERE, "docs", "Strategy-Pack-Doc-03-*.md")))
    cmds = [["make_manifest.py", "--verify"], ["test_speclint.py"], ["speclint.py"],
            ["render_cards.py", "--check", os.path.relpath(doc03[-1], HERE) if doc03 else "docs/<Doc 03 missing>"],
            ["test_golden.py"], ["test_features.py"], ["test_card_golden.py"], ["test_pipeline.py"],
            ["tests/test_m2.py"] + (["--require-parquet"] if "--require-parquet" in argv else []),
            ["tests/test_manifest.py"], ["tests/test_release.py"], ["tests/test_portability.py"]]
    if "--quick" not in argv:
        cmds.append(["mutation_check.py"])
    if "--pytest" in argv:
        cmds.append(["-m", "pytest", "-q"])
    return cmds


def versions():
    out = [f"{platform.system()} {platform.release()}", f"Python {platform.python_version()} ({sys.executable})"]
    for mod in ("yaml", "pyarrow", "pytest"):
        try:
            out.append(f"{mod} {__import__(mod).__version__}")
        except ImportError:
            out.append(f"{mod} not installed")
    out.append(f"EOS_PLATFORM={os.environ.get('EOS_PLATFORM', '(unset: native)')}")
    return ", ".join(out)


def main(argv):
    env = dict(os.environ, PYTHONUTF8="0")        # run under the platform's real default encoding, not UTF-8 mode
    failed = []
    with open(os.path.join(HERE, "run_all.log"), "w", encoding="utf-8", newline="\n") as log:
        head = f"environment: {versions()}"
        print(head)
        log.write(head + "\n")
        for c in commands(argv):
            t0 = time.monotonic()
            p = subprocess.run([sys.executable] + c, cwd=HERE, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", env=env)
            secs = time.monotonic() - t0
            tail = (p.stdout.strip().splitlines() or [""])[-1][:100]
            line = f"{'PASS' if p.returncode == 0 else 'FAIL'}  {' '.join(c):58s} {secs:6.1f}s  {tail}"
            print(line, flush=True)
            log.write(f"\n===== {line}\n{p.stdout}\n{p.stderr}\n")
            if p.returncode != 0:
                failed.append(" ".join(c))
    print(f"\n{'ALL PASSED' if not failed else 'FAILED: ' + '; '.join(failed)}   (full output: run_all.log)")
    return 1 if failed else 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):   # UTF-8 output whatever the console or pipe (Windows defaults to cp1252)
        _s.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
