#!/usr/bin/env python3
"""Registers a card version as experimental: lints it, stores the linter report, and writes the
none -> experimental lifecycle transition record (schemas/strategy_lifecycle_transition.schema.json).

    python3 register_card.py strategies/mom_v1.yaml --by harsh --reason "..." [--derived-from mom] [--seen ltqv]

A card's status lives only in these records (Document 01 s10); the card file carries none. Any edit to a card
changes its hash, so the edited version must be registered again before any run can use it. Later transitions
(experimental -> shadow, and so on) are written by M17 with the evidence their edge requires.
"""
import argparse, datetime as dt, hashlib, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from speclint import (FUTURE_TOLERANCE, decided_instant, lifecycle_status, load_transitions, load_yaml,  # noqa: E402
                      sha256_file)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("card")
    ap.add_argument("--by", required=True)
    ap.add_argument("--reason", required=True)
    ap.add_argument("--derived-from", nargs="*", default=[])
    ap.add_argument("--seen", nargs="*", default=[], help="lineages whose sealed holdout results the author has seen")
    ap.add_argument("--at", default=None, help="RFC 3339 timestamp with offset, not in the future; default: now")
    a = ap.parse_args()
    card = load_yaml(a.card)
    code, sha = card["code"], sha256_file(a.card)
    if sorted(a.derived_from) != sorted(card["lineage"]["derived_from"]):
        sys.exit(f"--derived-from {a.derived_from} does not match the card's lineage.derived_from {card['lineage']['derived_from']}")
    recs, errs = load_transitions(os.path.join(HERE, "lifecycle"))
    if errs:
        sys.exit(f"existing lifecycle records are invalid: {errs[:3]}")
    if lifecycle_status(code, sha, recs)[0] is not None:
        sys.exit(f"{code} at {sha[:12]} is already registered")
    out = subprocess.run([sys.executable, os.path.join(HERE, "speclint.py"), a.card], capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        sys.exit("the card does not pass the linter:\n" + out.stdout)
    for sub in ("reports", "transitions"):
        os.makedirs(os.path.join(HERE, "lifecycle", sub), exist_ok=True)
    report = os.path.join(HERE, "lifecycle", "reports", f"{code}-{card['version']}.lint.txt")
    open(report, "w", encoding="utf-8", newline="\n").write(out.stdout)
    n = len([f for f in os.listdir(os.path.join(HERE, "lifecycle", "transitions")) if f.endswith(".json")]) + 1
    now = dt.datetime.now(dt.timezone.utc)
    at = a.at or now.astimezone(dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat(timespec="seconds")
    try:   # the record's time is when the decision was made: never hand-typed into the future (review of r5.5)
        t = decided_instant({"decided_at": at, "_file": "(new)"})
    except ValueError as e:
        sys.exit(str(e))
    if t > now + FUTURE_TOLERANCE:
        sys.exit(f"--at {at} is in the future")
    rec = {"transition_id": f"{n:04d}-{code}-{card['version']}", "strategy_code": code, "lineage": card["lineage"]["code"],
           "card_sha256": sha, "from_status": "none", "to_status": "experimental", "decided_by": a.by, "decided_at": at,
           "reason": a.reason,
           "evidence": {"linter_report_sha256": hashlib.sha256(open(report, "rb").read()).hexdigest(),
                        "holdout_exposure_declaration": {"derived_from": a.derived_from, "sealed_results_seen": a.seen}}}
    path = os.path.join(HERE, "lifecycle", "transitions", f"{rec['transition_id']}.json")
    json.dump(rec, open(path, "w", encoding="utf-8", newline="\n"), indent=1)
    open(path, "a", encoding="utf-8", newline="\n").write("\n")
    print(f"registered {code} {card['version']} ({sha[:12]}) as experimental: {os.path.relpath(path, HERE)}")


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):   # UTF-8 output whatever the console or pipe (Windows defaults to cp1252)
        _s.reconfigure(encoding="utf-8")
    main()
