#!/usr/bin/env python3
"""Release consistency (review 1, section 6): the documents must agree with each other and with the files.

  - every 'Document 0N rX' / 'Doc 0N rX' reference names the revision actually packaged
    (the Issue Log is exempt below its first heading: history legitimately cites old revisions)
  - each document's filename revision equals the revision in its own title
  - README lists every packaged document and nothing that is not packaged
  - the Overview names the current release, and the Issue Log's title includes it
"""
import os, re, sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(KIT, "docs")
sys.path.insert(0, KIT)
from make_manifest import RELEASE  # noqa: E402

REF = re.compile(r"\b(?:Document|Doc)\s+0([1-7])\s+r(\d+)\b")
NUM = {"Core-Platform-Architecture-Doc-01": "1", "Data-Contract-Doc-02": "2", "Strategy-Pack-Doc-03": "3",
       "Validation-Protocol-Doc-04": "4"}


def packaged():
    out = {}
    for f in os.listdir(DOCS):
        for stem, n in NUM.items():
            m = re.fullmatch(re.escape(stem) + r"-r(\d+)\.md", f)
            if m:
                out[n] = (m.group(1), f)
    return out


def release_lines(present):
    """r5.5 (audit D1): every document's subtitle names the current release (r5.4 shipped Doc 03 saying r5.2)."""
    out = []
    for f in sorted(present):
        if f.startswith("Issue-Log"):
            continue
        lines = open(os.path.join(DOCS, f)).read().split("\n", 4)
        m = re.search(r"Release (r\d+\.\d+)", "\n".join(lines[:4]))
        if not m or m.group(1) != RELEASE:
            out.append(f"{f}: release line says {m.group(1) if m else 'nothing'}, the package is {RELEASE}")
    return out


def _headings(text):
    return {m.group(1) for m in re.finditer(r"^#{2,3} (\d+)\.", text, re.M)}


SEC = re.compile(r"\b(?:Document|Doc)\s+0([1-4])(?:\s+r\d+)?\s*(?:§|s)(\d+)\b")


def section_references(pk):
    """r5.5 (audit D1): every 'Document 0N §M' / 'Doc 0N sM' names a heading that exists - in every document and
    in the registry (r5.4's registry cited 'Doc 02 s14' after the section had become s13)."""
    heads = {n: _headings(open(os.path.join(DOCS, f)).read()) for n, (_, f) in pk.items()}
    out = []
    sources = [(f, open(os.path.join(DOCS, f)).read()) for f in sorted(os.listdir(DOCS)) if f.endswith(".md")]
    sources.append(("registry.yaml", open(os.path.join(KIT, "registry.yaml")).read()))
    for name, text in sources:
        if name.startswith("Issue-Log"):
            text = text.split("\n## 12.", 1)[-1] if "\n## 12." in text else text.split("\n## ", 1)[0]
        for m in SEC.finditer(text):
            n, sec = m.group(1), m.group(2)
            if n in heads and sec not in heads[n]:
                out.append(f"{name}: '{m.group(0)}' names no section {sec} in Document 0{n}")
    return out


def main():
    problems = []
    pk = packaged()
    for f in sorted(os.listdir(DOCS)):
        if not f.endswith(".md"):
            continue
        text = open(os.path.join(DOCS, f)).read()
        if f.startswith("Issue-Log"):
            text = text.split("\n## ", 1)[0]
        for m in REF.finditer(text):
            n, r = m.group(1), m.group(2)
            if n in pk and pk[n][0] != r:
                problems.append(f"{f}: cites '{m.group(0)}', packaged is r{pk[n][0]}")
    for n, (r, f) in pk.items():
        title = open(os.path.join(DOCS, f)).readline()
        if not re.search(rf"\bDocument 0{n} r{r}\b", title):
            problems.append(f"{f}: title does not say 'Document 0{n} r{r}'")
    readme = open(os.path.join(KIT, "README.md")).read()
    listed = set(re.findall(r"docs/([\w.\-]+\.md)", readme))
    present = {f for f in os.listdir(DOCS) if f.endswith(".md")}
    problems += [f"README lists docs/{f}, which is not packaged" for f in sorted(listed - present)]
    problems += [f"docs/{f} is packaged but not listed in README" for f in sorted(present - listed)]
    ov = [f for f in present if f.startswith("Overview-Spec-")]
    rel = RELEASE[1:]
    if len(ov) != 1 or f"Release {RELEASE}" not in open(os.path.join(DOCS, ov[0])).read().split("\n", 3)[2]:
        problems.append(f"the Overview must be the single current spec and say 'Release {RELEASE}'")
    if len(ov) == 1 and ov[0] != f"Overview-Spec-v{rel.replace('.', '-')}.md":
        problems.append(f"Overview filename {ov[0]} does not match release {RELEASE}")
    il = [f for f in present if f.startswith("Issue-Log")]
    if len(il) != 1 or RELEASE not in open(os.path.join(DOCS, il[0])).readline():
        problems.append(f"the Issue Log title must include {RELEASE}")
    problems += release_lines(present) + section_references(pk)
    for p in problems:
        print("FAIL ", p)
    print(f"release consistency: {'OK' if not problems else f'{len(problems)} problem(s)'}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
