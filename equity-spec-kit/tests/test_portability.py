#!/usr/bin/env python3
"""Portability regressions (r5.6). The review of r5.5 ran it on Windows and found three defects the Linux suite
could not see: a directory fsync (eos/store.py), SIGALRM (mutation_check.py) and text files read with the
platform's default encoding (tests/test_release.py and ~50 other open() calls). Each has a check here that fails
on Linux too, so the class of defect cannot come back unnoticed:

  static    every text-mode open() and text-mode subprocess names its encoding; no POSIX-only call (signal
            alarms, fcntl, fsync, os.rename) outside eos/fsio.py, which has a Windows branch for each; no
            'python3' spawned by name (Windows has no python3 on the PATH by default).
  dynamic   every suite runs with -X warn_default_encoding -W error::EncodingWarning, which turns any read or
            write that relies on the default encoding into an error on every OS, and with stdout forced to
            cp1252 (a Windows pipe), so output that cannot be encoded there fails here.
  bytes     every package text file is UTF-8 with LF line endings, and make_manifest.py --verify names a CRLF
            conversion (git core.autocrlf on Windows) instead of just reporting a hash mismatch.

    python3 tests/test_portability.py        exit 0 = all pass
"""
import ast
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLATFORM_MODULE = "eos/fsio.py"
TEXT_EXT = (".py", ".md", ".yaml", ".yml", ".json", ".txt")


def package_files(ext=None):
    for root, dirs, files in os.walk(KIT):
        dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", ".pytest_cache") and not d.startswith("."))
        for f in sorted(files):
            if f == "run_all.log" or f.endswith(".pyc"):
                continue
            rel = os.path.relpath(os.path.join(root, f), KIT).replace(os.sep, "/")
            if ext is None or rel.endswith(ext):
                yield rel


def _const(node):
    return node.value if isinstance(node, ast.Constant) else None


def static_findings():
    found = []
    for rel in package_files(".py"):
        src = open(os.path.join(KIT, rel), encoding="utf-8").read()
        for n in ast.walk(ast.parse(src)):
            where = f"{rel}:{getattr(n, 'lineno', '?')}"
            if isinstance(n, ast.Call):
                name = n.func.id if isinstance(n.func, ast.Name) else (
                    n.func.attr if isinstance(n.func, ast.Attribute) else None)
                kw = {k.arg: k.value for k in n.keywords}
                if isinstance(n.func, ast.Name) and name == "open":
                    mode = _const(n.args[1]) if len(n.args) > 1 else _const(kw.get("mode"))
                    if "encoding" not in kw and not (isinstance(mode, str) and "b" in mode):
                        found.append(f"{where}: text-mode open() without encoding=")
                if name in ("run", "Popen", "check_output", "check_call", "call") and \
                        (_const(kw.get("text")) is True or _const(kw.get("universal_newlines")) is True) and \
                        "encoding" not in kw:
                    found.append(f"{where}: text-mode subprocess without encoding=")
                if name in ("run", "Popen", "check_output", "check_call", "call") and n.args and \
                        isinstance(n.args[0], ast.List) and n.args[0].elts and _const(n.args[0].elts[0]) == "python3":
                    found.append(f"{where}: spawns 'python3' by name; use sys.executable")
                if rel != PLATFORM_MODULE and isinstance(n.func, ast.Attribute) and \
                        isinstance(n.func.value, ast.Name) and (n.func.value.id, name) in \
                        {("signal", "alarm"), ("signal", "setitimer"), ("os", "fsync"), ("os", "rename")}:
                    found.append(f"{where}: {n.func.value.id}.{name} is POSIX-only or unsafe on Windows; "
                                 f"use eos/fsio.py")
            if rel != PLATFORM_MODULE and isinstance(n, ast.Attribute) and n.attr in ("SIGALRM", "O_DIRECTORY"):
                found.append(f"{where}: {n.attr} does not exist on Windows")
            if rel != PLATFORM_MODULE and isinstance(n, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or ""]
                bad = [m for m in mods if m.split(".")[0] in ("fcntl", "msvcrt", "termios", "pwd", "grp")]
                if bad:
                    found.append(f"{where}: imports platform-only module {bad}; keep it inside eos/fsio.py")
    return found


def byte_findings():
    found = []
    for rel in package_files(TEXT_EXT):
        raw = open(os.path.join(KIT, rel), "rb").read()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as e:
            found.append(f"{rel}: not UTF-8 ({e})")
        if b"\r" in raw:
            found.append(f"{rel}: CR/CRLF line endings; the package is LF-only so its hashes are platform-independent")
        if raw.startswith(b"\xef\xbb\xbf"):
            found.append(f"{rel}: UTF-8 byte-order mark")
    return found


def crlf_is_named_by_verify():
    d = tempfile.mkdtemp()
    try:
        k = os.path.join(d, "k")
        shutil.copytree(KIT, k, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "run_all.log"))
        p = os.path.join(k, "registry.yaml")
        raw = open(p, "rb").read()
        with open(p, "wb") as f:
            f.write(raw.replace(b"\n", b"\r\n"))
        r = subprocess.run([sys.executable, "make_manifest.py", "--verify"], cwd=k, capture_output=True, text=True,
                           encoding="utf-8")
        return r.returncode == 1 and "registry.yaml" in r.stdout and "CRLF" in r.stdout
    finally:
        shutil.rmtree(d, ignore_errors=True)


SUITES = [["make_manifest.py", "--verify"], ["test_speclint.py"], ["speclint.py"], ["test_golden.py"],
          ["test_features.py"], ["test_card_golden.py"], ["test_pipeline.py"], ["tests/test_m2.py"],
          ["tests/test_release.py"], ["tests/test_manifest.py"], ["mutation_check.py", "--worker", "reference_sim", "0", "5"]]


def _run_strict(cmd):
    env = dict(os.environ, PYTHONIOENCODING="cp1252:strict", PYTHONUTF8="0")
    p = subprocess.run([sys.executable, "-X", "warn_default_encoding", "-W", "error::EncodingWarning"] + cmd, cwd=KIT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return cmd, p


def dynamic_findings():
    import glob
    doc03 = sorted(glob.glob(os.path.join(KIT, "docs", "Strategy-Pack-Doc-03-*.md")))
    suites = SUITES + [["render_cards.py", "--check", os.path.relpath(doc03[-1], KIT)]]
    found = []
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 2) as ex:
        for cmd, p in ex.map(_run_strict, suites):
            if p.returncode != 0:
                err = [x for x in (p.stderr + p.stdout).splitlines() if "Error" in x or "Warning" in x][-3:]
                found.append(f"{' '.join(cmd)} fails under strict encoding: {' | '.join(err) or p.stdout[-300:]}")
    return found


def main():
    if sys.version_info < (3, 10):
        print("NOT RUN: EncodingWarning needs Python 3.10+")
        return 1
    fails = 0
    for name, found in (("static", static_findings()), ("bytes", byte_findings()),
                        ("crlf", [] if crlf_is_named_by_verify() else
                         ["make_manifest.py --verify does not name a CRLF conversion"]),
                        ("dynamic", dynamic_findings())):
        for f in found:
            print(f"FAIL  [{name}] {f}")
        print(f"{'ok  ' if not found else 'FAIL'}  {name}: {len(found)} finding(s)")
        fails += bool(found)
    print(f"\n{4 - fails}/4 portability checks passed")
    return fails


def test_portability_static():
    assert static_findings() == []


def test_portability_bytes():
    assert byte_findings() == [] and crlf_is_named_by_verify()


def test_portability_dynamic():
    assert dynamic_findings() == []


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):   # UTF-8 output whatever the console or pipe (Windows defaults to cp1252)
        _s.reconfigure(encoding="utf-8")
    sys.exit(1 if main() else 0)
