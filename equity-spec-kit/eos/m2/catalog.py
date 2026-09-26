"""NSE source catalogue and warehouse coverage reporting (r5.9).

The catalogue is intentionally small and explicit: only sources the platform already knows how to consume or
capture are listed. URL generation is separate from ingestion; downloaded bytes still go through the immutable
raw landing/provenance path before they can affect research state.
"""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass


# NSE's CM bhavcopy moved from the legacy layout (cmDDMONYYYYbhav.csv.zip under /content/historical/EQUITIES/) to
# UDiFF. The first UDiFF-only session is taken as 8 July 2024. UNVERIFIED: it decides only which URL the downloader
# tries first; ingestion accepts either format for any date, and the same content in both is one observation
# (eos/m2/identity.py). Confirm it against the archive during Stage 0 and correct it here if needed.
UDIFF_ONLY_FROM = dt.date(2024, 7, 8)
UDIFF_ONLY_FROM_BASIS = "unverified"


_MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def _fields(day):
    """Template fields. Month names come from a fixed table: strftime('%b') follows the process locale, and a
    non-English Windows locale would produce URLs NSE does not serve (r5.10)."""
    mon = _MONTHS[day.month - 1]
    return dict(YYYY=f"{day.year:04d}", YYYYMMDD=f"{day.year:04d}{day.month:02d}{day.day:02d}",
                DDMMYYYY=f"{day.day:02d}{day.month:02d}{day.year:04d}", DDMMYY=f"{day.day:02d}{day.month:02d}{day.year % 100:02d}",
                MON=mon, ddMONyyyy=f"{day.day:02d}{mon}{day.year:04d}")


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    filename_template: str
    url_template: str
    parsed: bool = True
    static_live_url: bool = False
    content: str = "text"                  # what a genuine file is: 'zip', 'gzip' or 'text' (checked on download)

    def filename(self, day: dt.date) -> str:
        return self.filename_template.format(**_fields(day))

    def url(self, day: dt.date) -> str:
        return self.url_template.format(**_fields(day))


SOURCES = {
    "nse_cm_bhavcopy": SourceSpec(
        "nse_cm_bhavcopy",
        "BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip",
        "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip",
        content="zip",
    ),
    "nse_cm_delivery": SourceSpec(
        "nse_cm_delivery",
        "MTO_{DDMMYYYY}.DAT",
        "https://nsearchives.nseindia.com/archives/equities/mto/MTO_{DDMMYYYY}.DAT",
    ),
    "nse_cm_security_master": SourceSpec(
        "nse_cm_security_master",
        "NSE_CM_security_{DDMMYYYY}.csv.gz",
        "https://nsearchives.nseindia.com/content/cm/NSE_CM_security_{DDMMYYYY}.csv.gz",
        content="gzip",
    ),
    "nse_cm_full_bhav_delivery": SourceSpec(
        "nse_cm_full_bhav_delivery",
        "sec_bhavdata_full_{DDMMYYYY}.csv",
        "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{DDMMYYYY}.csv",
    ),
    # NSE publishes the complete price-band list at a stable URL that always serves TODAY's list. The capture is
    # named with its retrieval date in IST (the date it was captured, NOT a proven effective session), and the
    # downloader refuses any other date (r5.10: r5.9 would label today's list with any past date it was given).
    "nse_cm_price_band": SourceSpec(
        "nse_cm_price_band",
        "sec_list_{DDMMYYYY}.csv",
        "https://nsearchives.nseindia.com/content/equities/sec_list.csv",
        parsed=False,
        static_live_url=True,
    ),
}


LEGACY_BHAVCOPY = SourceSpec(
    "nse_cm_bhavcopy",
    "cm{ddMONyyyy}bhav.csv.zip",
    "https://nsearchives.nseindia.com/content/historical/EQUITIES/{YYYY}/{MON}/cm{ddMONyyyy}bhav.csv.zip",
    content="zip",
)


def source_spec(source_id: str, day: dt.date = None, variant: str = None) -> SourceSpec:
    """The spec for a source on a date. The bhavcopy has two layouts; `variant` ('legacy'/'udiff') overrides the
    date rule, for dates where both were published."""
    try:
        spec = SOURCES[source_id]
    except KeyError as e:
        raise KeyError(f"unknown source {source_id!r}; known: {', '.join(sorted(SOURCES))}") from e
    if variant not in (None, "legacy", "udiff"):
        raise ValueError(f"variant {variant!r}: expected 'legacy' or 'udiff'")
    if source_id == "nse_cm_bhavcopy":
        legacy = variant == "legacy" or (variant is None and day is not None and day < UDIFF_ONLY_FROM)
        return LEGACY_BHAVCOPY if legacy else spec
    if variant is not None:
        raise ValueError(f"{source_id} has one layout; variant applies to nse_cm_bhavcopy only")
    return spec


def filename_for(source_id: str, day: dt.date, variant: str = None) -> str:
    return source_spec(source_id, day, variant).filename(day)


def url_for(source_id: str, day: dt.date, variant: str = None) -> str:
    return source_spec(source_id, day, variant).url(day)


def planned_downloads(days, source_ids=None):
    source_ids = list(source_ids or SOURCES)
    return [
        {"trade_date": day, "source_id": sid, "filename": filename_for(sid, day), "url": url_for(sid, day),
         "parsed": source_spec(sid).parsed, "static_live_url": source_spec(sid).static_live_url}
        for day in days for sid in source_ids
    ]


def _snapshot_partitions(wh, table, snapshot=None):
    if snapshot is None:
        return wh.partitions(table)
    prefix = f"{table}/"
    return sorted(k[len(prefix):] for k, parts in snapshot["parts"].items() if k.startswith(prefix) and parts)


def _raw_rows(wh, snapshot=None):
    keys = _snapshot_partitions(wh, "raw_file", snapshot)
    return wh.read("raw_file", keys, snapshot) if keys else []


def _parse_rows(wh, snapshot=None):
    keys = _snapshot_partitions(wh, "raw_parse_event", snapshot)
    return wh.read("raw_parse_event", keys, snapshot) if keys else []


def _base_name(name):
    """A downloaded reissue is saved as <stem>.reissue-<sha12><ext> (acquire.fetch); it covers the same date."""
    import re
    return re.sub(r"\.reissue-[0-9a-f]{12}(?=\.)", "", os.path.basename(name)).lower()


def coverage_matrix(wh, days, source_ids=None, snapshot=None):
    """Return one deterministic row per requested (date, source).

    Parsed sources are complete only when `source_coverage.complete` exists for that trade date. For capture-only
    sources (currently price bands), a dated immutable raw receipt is reported as `captured_unparsed`; that status
    is never promoted to source coverage and therefore cannot influence a strategy.
    """
    source_ids = list(source_ids or SOURCES)
    raw = _raw_rows(wh, snapshot)
    parse = _parse_rows(wh, snapshot)
    cov_keys = set(_snapshot_partitions(wh, "source_coverage", snapshot))
    cov_by = {}
    for d in days:
        key = d.isoformat()
        if key in cov_keys:
            for r in wh.read("source_coverage", [key], snapshot):
                cov_by[(d, r["source_id"])] = r
    parse_by_sha = {}
    for r in parse:
        parse_by_sha.setdefault((r["source_id"], r["file_sha256"]), []).append(r)

    out = []
    for day in days:
        for sid in source_ids:
            spec = source_spec(sid, day)
            cov = cov_by.get((day, sid))
            expected = spec.filename(day)
            names = {expected.lower()} | ({filename_for(sid, day, v).lower() for v in ("legacy", "udiff")}
                                          if sid == "nse_cm_bhavcopy" else set())
            receipts = [r for r in raw if r["source_id"] == sid and _base_name(r["original_name"]) in names]
            # If a manually saved capture kept a static source filename, match it only by the receipt's IST date is
            # deliberately NOT attempted here: that would silently turn receipt time into source effective date.
            if cov is not None:
                status = "parsed_complete" if cov["complete"] else "parsed_incomplete"
            elif receipts:
                statuses = {p["status"] for r in receipts for p in parse_by_sha.get((sid, r["file_sha256"]), [])}
                if "captured_unparsed" in statuses:
                    status = "captured_unparsed"
                elif "rejected" in statuses:
                    status = "parse_rejected"
                elif "parsed" in statuses:
                    status = "parsed_without_coverage"
                else:
                    status = "receipt_only"
            else:
                status = "missing"
            out.append({
                "trade_date": day, "source_id": sid, "status": status,
                "expected_filename": expected, "url": spec.url(day),
                "rows": None if cov is None else cov["rows"],
                "file_sha256": None if cov is None else cov["file_sha256"],
                "availability_inferred": None,
            })
    return out


def coverage_summary(rows):
    total = len(rows)
    by_status = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    return {"cells": total, "by_status": dict(sorted(by_status.items())),
            "complete_share": (by_status.get("parsed_complete", 0) / total) if total else None}
