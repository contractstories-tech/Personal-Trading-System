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
    for p in problems:
        print("FAIL ", p)
    print(f"release consistency: {'OK' if not problems else f'{len(problems)} problem(s)'}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
