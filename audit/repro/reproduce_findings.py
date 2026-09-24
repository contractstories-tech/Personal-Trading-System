#!/usr/bin/env python3
"""Reproduces every executed finding in audit/Assurance-Report-r5.4.md against an unzipped r5.4 package.

    unzip equity-spec-kit-r5.4.zip -d /tmp/kit
    python3 reproduce_findings.py /tmp/kit/equity-spec-kit-r5.4

Nothing in the package is modified: experiments that need an edited card or document run on a temporary
copy. Section numbers match the finding IDs in the report. Finding A5 (Parquet) needs pyarrow and is
reported as SKIPPED without it.
"""
import copy
import datetime as dt
import itertools
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile

KIT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
os.chdir(KIT)
sys.path.insert(0, KIT)
sys.path.insert(0, os.path.join(KIT, "tests"))

import speclint as L  # noqa: E402
import reference_sim as R  # noqa: E402
import fixtures as F  # noqa: E402
from eos import store  # noqa: E402
from eos.m2 import ingest, resolve  # noqa: E402
from eos.timeutil import at_ist  # noqa: E402

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
REG = L.load_yaml("registry.yaml")
REG_SHA = L.sha256_file("registry.yaml")
SCHEMA = json.load(open("schemas/card.schema.json"))
LT = L.load_yaml("strategies/ltqv_v1.yaml")
MOM = L.load_yaml("strategies/mom_v1.yaml")


def head(t):
    print(f"\n=== {t}")


def lint(name, card):
    errs = L.lint(card, REG, REG_SHA, SCHEMA)
    print(f"  {'ACCEPTED' if not errs else 'rejected'}  {name}" + (f"  {errs[:1]}" if errs else ""))


def run(cmd, cwd, match=None):
    p = subprocess.run([sys.executable] + cmd, cwd=cwd, capture_output=True, text=True)
    lines = p.stdout.strip().splitlines() or [""]
    picked = [x for x in lines if match and match in x] or lines[-1:]
    return " | ".join(x.strip() for x in picked) + f"  (exit {p.returncode})"


# ---------------------------------------------------------------- A1
head("A1  Card semantics are never executed: a materially different card passes every package check")
tmp = tempfile.mkdtemp()
kit2 = os.path.join(tmp, "kit")
shutil.copytree(KIT, kit2)
for f, subs in (("strategies/mom_v1.yaml", [("2.5 * atr_pct_20)\"", "4.0 * atr_pct_20)\""),
                                            ("2.5 * atr_pct_at_peak", "4.0 * atr_pct_at_peak")]),
                ("strategies/ltqv_v1.yaml", [("roce_3y_avg >= 0.15", "roce_3y_avg >= 0.05"),
                                             ("cfo_pat_3y >= 0.70", "cfo_pat_3y >= 0.10")])):
    p = os.path.join(kit2, f)
    s = open(p).read()
    for a, b in subs:
        assert a in s, a
        s = s.replace(a, b)
    open(p, "w").write(s)
sys.path.insert(0, kit2)
doc = os.path.join(kit2, "docs", "Strategy-Pack-Doc-03-r6.md")
text = open(doc).read()
rendered = subprocess.run([sys.executable, "-c", "import render_cards as r; print(r.render(), end='')"],
                          cwd=kit2, capture_output=True, text=True).stdout
open(doc, "w").write(text[:text.index("<!-- generated from strategies/")] + rendered)
print("  edited: mom_v1 stop 2.5 -> 4.0 x ATR; ltqv_v1 G2 ROCE 15% -> 5%; G3 cash conversion 0.70 -> 0.10")
print("  speclint        :", run(["speclint.py"], kit2, "PASS"))
print("  test_speclint   :", run(["test_speclint.py"], kit2, "passed"))
print("  render parity   :", run(["render_cards.py", "--check", "docs/Strategy-Pack-Doc-03-r6.md"], kit2))
print("  test_golden     :", run(["test_golden.py"], kit2, "planted defects caught"))
shutil.rmtree(tmp)

# ---------------------------------------------------------------- A3 / B2 linter bypasses
head("B2  Materiality, hard-cap and look-ahead rules can be bypassed at compile time")
c = copy.deepcopy(LT); c["unknown_overrides"]["roce_3y_avg"] = "substitute"
lint("material roce_3y_avg: substitute  ('substitute' is defined nowhere)", c)
c = copy.deepcopy(MOM); c["unknown_overrides"]["delivery_pct_20d_avg"] = "substitute"
lint("momentum delivery (declared blocking): substitute", c)
c = copy.deepcopy(LT)
c["gates"].append({"code": "G10", "expr": "quality_composite > 0", "unknown_blocks": False})
c["proposed_execution_rule"]["tranches"][0]["recheck_gates"].append("G10")
lint("waivable gate reading a composite of material inputs", c)
c = copy.deepcopy(MOM)
c["proposed_execution_rule"]["target_qty"] = "max(floor(target_value / entry_ref), floor(hard_cap_value / entry_high))"
lint("target_qty uses max(): the 'hard cap' becomes a floor", c)
c = copy.deepcopy(LT)
c["proposed_execution_rule"]["target_qty"] = "floor(target_value / entry_ref) + floor(0 * hard_cap_value)"
lint("target_qty mentions hard_cap_value but ignores it", c)
c = copy.deepcopy(MOM); c["proposed_execution_rule"]["entry_ref"] = "close_raw(next_executable_session(signal_date))"
lint("entry_ref = the NEXT session's close", c)
c = copy.deepcopy(MOM); c["gates"][2]["expr"] = "open_raw(next_executable_session(eval_date)) > close_raw(eval_date)"
lint("gate reads tomorrow's open", c)

# ---------------------------------------------------------------- B3 read contracts
head("B3a point_in_time_panel silently drops a bar that was first published after its own day's cutoff")
D1, D2, D3 = dt.date(2026, 9, 16), dt.date(2026, 9, 17), dt.date(2026, 9, 18)


def wh_env():
    d = tempfile.mkdtemp()
    return d, store.Warehouse(os.path.join(d, "wh"), "jsonl")


d, wh = wh_env()
for day, hhmm in ((D1, "22:40"), (D2, "23:30"), (D3, "22:40")):
    ingest.ingest_bhavcopy(wh, F.legacy(os.path.join(d, f"b{day}.csv"), day), at_ist(day, hhmm), mode="live",
                           now=at_ist(day, hhmm))
live = sorted({str(r["trade_date"]) for r in resolve.history_known_as_of(wh, D3)})
panel = sorted({str(r["trade_date"]) for r in resolve.point_in_time_panel(wh, D1, D3)})
print(f"  D2's file published 23:30 (cutoff 23:00).  Live decision on D3 had: {live}")
print(f"  panel used for the D1..D3 decision sequence gives:             {panel}")
shutil.rmtree(d)

head("B3b 'backfill' mode back-dates a file that was actually received after the cutoff")
d, wh = wh_env()
ingest.ingest_bhavcopy(wh, F.legacy(os.path.join(d, "b1.csv"), D1), at_ist(D1, "23:45"), mode="backfill")
rows = resolve.history_known_as_of(wh, D1)
print(f"  received 23:45 IST; usable_from = {rows[0]['usable_from'].astimezone(IST).time()} IST; "
      f"rows visible to the D1 23:00 run: {len(rows)}")
shutil.rmtree(d)

# ---------------------------------------------------------------- B4 parquet naive timestamps
head("B4  The production Parquet codec accepts naive timestamps the JSONL test codec refuses")
for name in ("jsonl", "parquet"):
    d = tempfile.mkdtemp()
    try:
        w = store.Warehouse(os.path.join(d, "wh"), name)
    except store.StoreError as e:
        print(f"  {name:8} SKIPPED ({e})")
        continue
    row = {"file_sha256": "x", "source_id": "s", "trade_date": D1, "received_at": dt.datetime(2026, 9, 16, 22, 30),
           "rows_new": 1, "rows_changed": 0, "rows_unchanged": 0, "mode": "backfill"}
    try:
        w.append("ingestion_log", "2026-09-16", [row])
        back = w.read("ingestion_log")[0]["received_at"]
        print(f"  {name:8} ACCEPTED naive 22:30 -> stored {back.isoformat()} = {back.astimezone(IST).isoformat()} IST")
    except store.StoreError as e:
        print(f"  {name:8} refused: {e}")
    shutil.rmtree(d)

# ---------------------------------------------------------------- B6 ROCE
head("B6  ROCE definition (registry roce_3y_avg / roce_hy_ttm; reference_sim.roce)")
print("  operating loss (EBIT -20), cash-rich, CE <= 5% TA :", R.roce(-20, 500, 0, 0, 490, 520, prior_ce=10))
print("  EBIT 30, CE 150 now, prior-year CE -140           :", R.roce(30, 400, 0, 0, 250, 1000, prior_ce=-140))
print("  EBIT 30, CE 150 now, prior-year CE -200           :", R.roce(30, 400, 0, 0, 250, 1000, prior_ce=-200))

# ---------------------------------------------------------------- C-level numeric probes
head("C4  Rights entitlement: Doc 02 / registry say max(0, P_ex - S); reference_sim uses TERP - S")
ref = R.rights_value(100, 1, 4, 80, 120)["value"]
for p_ex in (112, 104, 100):
    print(f"  P_ex {p_ex}: per the prose {max(0, p_ex - 80) * 25:7.2f}   per the reference {ref:7.2f}")

head("C5  Momentum: sized on ATR at signal, initial stop on ATR at fill -> risk budget exceeded")
N, risk, ref_px, atr_sig, atr_fill = 1_000_000, 0.01, 100.0, 0.02, 0.026
hi = ref_px * 1.03
qty = min(math.floor(N * risk / (2.5 * atr_sig) / ref_px), math.floor(N * risk / (hi * 2.5 * atr_sig)))
taken = qty * hi * 2.5 * atr_fill
print(f"  qty {qty} at worst fill {hi}: budget {N * risk:.0f}, risk at initial stop {taken:.0f} ({taken / (N * risk):.2f}x)")

head("C6  Gate boundary outcome depends on summation order (features are DOUBLE; card thresholds are exact)")
vals = [x / 100 for x in range(1, 60)]
for T in (0.70, 1.0, 2.5, 6.0):
    for a, b in itertools.product(vals, repeat=2):
        c3 = round(3 * T - a - b, 2)
        if c3 <= 0:
            continue
        m1, m2 = (a + b + c3) / 3, (c3 + b + a) / 3
        if (m1 >= T) != (m2 >= T):
            print(f"  3-year mean of [{a}, {b}, {c3}] vs {T}: order A {m1!r} "
                  f"{'PASS' if m1 >= T else 'FAIL'}; order B {m2!r} {'PASS' if m2 >= T else 'FAIL'}")
            break

# ---------------------------------------------------------------- B7 promotion statistics
head("B7  Probability that a zero-alpha strategy passes the sign-based promotion tests (Doc 04 s12)")
random.seed(7)


def passes(te, design=72, hold=36, rho=0.1):
    sd, prev, x = te / 12 ** 0.5, 0.0, []
    for _ in range(design + hold):
        prev = rho * prev + random.gauss(0, sd * (1 - rho ** 2) ** 0.5)
        x.append(prev)
    windows = [sum(x[i:i + 36]) for i in range(len(x) - 35)]
    return sum(x[:design]) > 0 and sum(x[design:]) > 0 and sum(w > 0 for w in windows) / len(windows) >= 0.60


for te in (0.05, 0.08, 0.12):
    p = sum(passes(te) for _ in range(20000)) / 20000
    print(f"  tracking error {te:.0%}: P(design alpha > 0, holdout alpha > 0, >= 60% windows positive) = {p:.2f}")

print("\nDone. Mutation analysis: python3 mutation_analysis.py", KIT)
