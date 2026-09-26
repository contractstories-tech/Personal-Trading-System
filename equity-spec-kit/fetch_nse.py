#!/usr/bin/env python3
"""Download one catalogued NSE source file without ingesting it.

The downloaded bytes remain ordinary files until passed through the normal ingestion/capture path, which is where
warehouse receipts, provenance and integrity controls are applied.
"""
import argparse
import datetime as dt
import json
import sys

from eos.m2.acquire import fetch
from eos.m2.catalog import SOURCES


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("source_id", choices=sorted(SOURCES))
    ap.add_argument("trade_date", type=dt.date.fromisoformat)
    ap.add_argument("destination")
    ns = ap.parse_args(argv)
    r = fetch(ns.source_id, ns.trade_date, ns.destination)
    print(json.dumps({
        "source_id": r.source_id,
        "trade_date": r.trade_date.isoformat(),
        "path": r.path,
        "source_url": r.source_url,
        "retrieved_at": r.retrieved_at.isoformat(),
        "file_sha256": r.file_sha256,
        "size_bytes": r.size_bytes,
    }, indent=2))
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        _s.reconfigure(encoding="utf-8")
    raise SystemExit(main())
