#!/usr/bin/env python3
"""Package manifest: binds every artefact in the controlling set by sha256.

    python3 make_manifest.py            writes MANIFEST.json
    python3 make_manifest.py --verify   exit 1 if any file differs from MANIFEST.json

Every run manifest (schemas/run_manifest.schema.json) records this package digest.
"""
import hashlib, json, os, platform, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP = {"MANIFEST.json", "__pycache__", ".pytest_cache"}
# The one place the release is set. --verify checks MANIFEST.json and README.md agree with it
# (r5.2 shipped labelled "r5.1" because this string was hardcoded and never verified).
RELEASE = "r5.4"
TEST_COMMAND = ("python3 test_speclint.py && python3 speclint.py && "
                "python3 render_cards.py --check docs/Strategy-Pack-Doc-03-r6.md && python3 test_golden.py && "
                "python3 tests/test_m2.py && python3 tests/test_manifest.py && "
                "python3 tests/test_release.py")


class StrayFileError(SystemExit):
    pass


def files():
    """Every file in the package. A hidden file or directory (.git, .DS_Store, an editor's swap file) is
    refused, never silently bound or silently skipped: r5.4's first build bound a stray docs/.git."""
    stray = []
    for root, dirs, fs in os.walk(HERE):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        stray += [os.path.relpath(os.path.join(root, d), HERE) for d in dirs if d.startswith(".")]
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in sorted(fs):
            if f in SKIP or f.endswith(".pyc"):
                continue
            if f.startswith("."):
                stray.append(os.path.relpath(os.path.join(root, f), HERE))
                continue
            p = os.path.join(root, f)
            yield os.path.relpath(p, HERE).replace(os.sep, "/"), hashlib.sha256(open(p, "rb").read()).hexdigest()
    if stray:
        raise StrayFileError("refusing to bind hidden files or directories - remove them first: " + ", ".join(sorted(stray)))


def build():
    import yaml
    entries = dict(files())
    digest = hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()
    return {"package": "equity-opportunity-spec-kit", "release": RELEASE,
            "package_digest": digest, "files": entries,
            "tested_with": {"python": platform.python_version(), "pyyaml": yaml.__version__},
            "test_command": TEST_COMMAND}


if __name__ == "__main__":
    m = build()
    path = os.path.join(HERE, "MANIFEST.json")
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        old = json.load(open(path))
        diff = sorted(set(old["files"].items()) ^ set(m["files"].items()))
        for d in sorted({k for k, _ in diff}):
            print("MANIFEST MISMATCH:", d)
        # the stored digest is the package's identity in every run manifest, so verify it too
        recomputed = hashlib.sha256(json.dumps(old["files"], sort_keys=True).encode()).hexdigest()
        digest_ok = old.get("package_digest") == recomputed
        if not digest_ok:
            print(f"MANIFEST MISMATCH: package_digest does not match its own file list "
                  f"(stored {str(old.get('package_digest'))[:16]}, recomputed {recomputed[:16]})")
        release_ok = old.get("release") == RELEASE
        if not release_ok:
            print(f"MANIFEST MISMATCH: release is {old.get('release')!r}, this package is {RELEASE!r}")
        readme = open(os.path.join(HERE, "README.md")).readline()
        readme_ok = readme.rstrip().endswith(f"release {RELEASE}")
        if not readme_ok:
            print(f"MANIFEST MISMATCH: README.md heading does not name release {RELEASE}")
        ok = not diff and digest_ok and release_ok and readme_ok
        print("manifest OK" if ok else "manifest verification FAILED")
        sys.exit(0 if ok else 1)
    json.dump(m, open(path, "w"), indent=1, sort_keys=True)
    print(f"MANIFEST.json written: {len(m['files'])} files, package_digest {m['package_digest'][:16]}")
