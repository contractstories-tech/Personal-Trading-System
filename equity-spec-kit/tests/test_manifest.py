#!/usr/bin/env python3
"""Regression for the r5.2 release-label defect: MANIFEST.json said 'r5.1' and --verify passed.
Each case copies the package, plants one inconsistency, and requires --verify to fail."""
import json, os, shutil, subprocess, sys, tempfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def verify(d):
    return subprocess.run([sys.executable, "make_manifest.py", "--verify"], cwd=d, capture_output=True, text=True)


def copy():
    d = tempfile.mkdtemp()
    shutil.copytree(KIT, os.path.join(d, "k"), ignore=shutil.ignore_patterns("__pycache__"))
    return os.path.join(d, "k")


def main():
    fails = 0
    k = copy()
    subprocess.run([sys.executable, "make_manifest.py"], cwd=k, capture_output=True)
    base = verify(k)
    cases = [("freshly written manifest verifies", base.returncode == 0)]

    m = json.load(open(os.path.join(k, "MANIFEST.json")))
    m["release"] = "r5.1"   # the r5.2 defect: files and digest intact, label wrong
    json.dump(m, open(os.path.join(k, "MANIFEST.json"), "w"), indent=1, sort_keys=True)
    cases.append(("stale release label fails --verify", verify(k).returncode == 1))

    k2 = copy()
    subprocess.run([sys.executable, "make_manifest.py"], cwd=k2, capture_output=True)
    src = open(os.path.join(k2, "make_manifest.py")).read()
    rel = src.split('RELEASE = "')[1].split('"')[0]
    open(os.path.join(k2, "README.md"), "a").close()
    lines = open(os.path.join(k2, "README.md")).read().split("\n", 1)
    open(os.path.join(k2, "README.md"), "w").write(lines[0].replace(rel, "r0.0") + "\n" + lines[1])
    subprocess.run([sys.executable, "make_manifest.py"], cwd=k2, capture_output=True)  # re-hash: only the label is wrong
    cases.append(("README naming another release fails --verify", verify(k2).returncode == 1))

    k3 = copy()
    os.makedirs(os.path.join(k3, "docs", ".git"))
    open(os.path.join(k3, "docs", ".git", "HEAD"), "w").write("ref: refs/heads/main\n")
    w = subprocess.run([sys.executable, "make_manifest.py"], cwd=k3, capture_output=True, text=True)
    v = verify(k3)
    cases.append(("a stray hidden directory is refused by build and verify",
                  w.returncode != 0 and v.returncode != 0 and ".git" in (w.stderr + w.stdout)))

    for name, ok in cases:
        print(("ok    " if ok else "FAIL  ") + name)
        fails += not ok
    print(f"\n{len(cases) - fails}/{len(cases)} passed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
