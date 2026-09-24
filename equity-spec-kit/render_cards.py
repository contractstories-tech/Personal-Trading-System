#!/usr/bin/env python3
"""Generates Document 03's card sections from the YAML cards, and checks parity.

The YAML is the ONLY executable source of a strategy. Document 03 carries a generated
rendering stamped with each card's sha256. `--check <doc.md>` fails if any rendered block
in the document differs from its YAML (compared as parsed data, so whitespace is ignored).

    python3 render_cards.py > cards_rendered.md
    python3 render_cards.py --check Strategy-Pack.md
"""
import hashlib, os, re, sys
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
SDIR = os.path.join(HERE, "strategies")


def cards():
    for f in sorted(os.listdir(SDIR)):
        if f.endswith(".yaml"):
            p = os.path.join(SDIR, f)
            raw = open(p, "rb").read()
            yield f, raw.decode(), hashlib.sha256(raw).hexdigest()


def render():
    out = []
    for f, text, h in cards():
        out.append(f"<!-- generated from strategies/{f} sha256:{h} -->\n```yaml\n{text.rstrip()}\n```\n")
    return "\n".join(out)


def check(doc_path):
    doc = open(doc_path, encoding="utf-8").read()
    blocks = re.findall(r"<!-- generated from strategies/(\S+) sha256:([0-9a-f]{64}) -->\s*```yaml\n(.*?)```", doc, re.S)
    problems, seen = [], set()
    truth = {f: (text, h) for f, text, h in cards()}
    for f, h, body in blocks:
        seen.add(f)
        if f not in truth:
            problems.append(f"{f}: rendered in document but no such card")
            continue
        text, real_h = truth[f]
        if h != real_h:
            problems.append(f"{f}: stamped hash {h[:12]} is stale; card is now {real_h[:12]}")
        if yaml.safe_load(body) != yaml.safe_load(text):
            problems.append(f"{f}: rendered content differs from the YAML card")
    for f in truth:
        if f not in seen:
            problems.append(f"{f}: card not rendered in document")
    for p in problems:
        print("PARITY FAIL:", p)
    print("parity OK" if not problems else f"{len(problems)} parity failure(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        sys.exit(check(sys.argv[2]))
    print(render())
