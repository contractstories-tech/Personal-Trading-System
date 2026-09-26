#!/usr/bin/env python3
"""Report Stage-0 NSE source coverage for a warehouse without changing it.

Examples:
  python coverage_report.py C:\\EquitySystem\\warehouse 2026-09-01 2026-09-30 --codec parquet
  python coverage_report.py /data/warehouse 2026-09-24 2026-09-24 --source nse_cm_bhavcopy --source nse_cm_delivery
"""
import argparse
import datetime as dt
import os
import sys

from eos.store import Warehouse
from eos.m2.catalog import SOURCES, coverage_matrix, coverage_summary


def days(a, b):
    d = a
    while d <= b:
        yield d
        d += dt.timedelta(days=1)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("warehouse")
    ap.add_argument("start", type=dt.date.fromisoformat)
    ap.add_argument("end", type=dt.date.fromisoformat)
    ap.add_argument("--codec", choices=("jsonl", "parquet"), default="parquet")
    ap.add_argument("--source", action="append", choices=sorted(SOURCES))
    ns = ap.parse_args(argv)
    if ns.end < ns.start:
        ap.error("end must not be before start")
    wh = Warehouse(os.path.abspath(ns.warehouse), codec_name=ns.codec)
    rows = coverage_matrix(wh, list(days(ns.start, ns.end)), ns.source)
    print("trade_date  source                         status                  rows  sha256")
    for r in rows:
        print(f"{r['trade_date']}  {r['source_id']:<30} {r['status']:<23} "
              f"{str(r['rows'] if r['rows'] is not None else '-'):>5}  {(r['file_sha256'] or '-')[:12]}")
    s = coverage_summary(rows)
    share = "-" if s["complete_share"] is None else f"{s['complete_share']:.1%}"
    print(f"\ncoverage cells: {s['cells']}; parsed-complete share: {share}")
    print("by status:", ", ".join(f"{k}={v}" for k, v in s["by_status"].items()) or "none")
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        _s.reconfigure(encoding="utf-8")
    raise SystemExit(main())
