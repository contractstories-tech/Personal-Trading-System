# START HERE — r5.9 handover

*25 September 2026 · non-normative status note; the manifest-bound specifications, registry, cards and schemas control on any conflict*

## Status

- **r5.7 is the last native-Windows/Parquet certified baseline.** A clean Windows 11 / Python 3.12.10 environment installing only declared dependencies ended `ALL PASSED`.
- **r5.8 is the completed price/security-reference correction milestone.** It preserves NSE source identity, valid multi-series observations, versioned MII master state, canonical strategy prices, no-trade states and withdrawal tombstones. It has not yet received the user's native-Windows/Parquet/real-file acceptance.
- **r5.9 is the market-data completion build.** It starts from r5.8 without changing r5.8 in place and adds the next known Stage-0 components that can be implemented without guessing unresolved exchange semantics.

## What r5.9 adds

1. **Primary MTO delivery hardening.** The parser validates the type-10 trade date and declared row count, preserves NSE's reported delivery percentage and cross-checks it arithmetically against traded/deliverable quantities. Mismatches are evidence conflicts, not silently corrected source values.
2. **Independent full-bhav delivery evidence.** `sec_bhavdata_full_DDMMYYYY.csv` is parsed into `delivery_crosscheck_observation`. Missing delivery shown by NSE as `-` remains unavailable, never zero. This source may validate the MTO feed but can never populate or overwrite the primary delivery table.
3. **More MII evidence, not more assumptions.** Raw `PricRg`, `PricRgTp`, `MaxPric`, `MinPric` and `TickSz` fields are retained. They are evidence only until historical effective-date and tick-rounding semantics are proven.
4. **Explicit NSE source catalogue and acquisition helper.** `eos/m2/catalog.py`, `eos/m2/acquire.py` and `fetch_nse.py` know the small allowlisted Stage-0 source set and download bytes without bypassing ingestion/provenance controls.
5. **Coverage reporting.** `coverage_report.py` reports parsed, rejected, receipt-only, captured-unparsed and missing source states date by date.
6. **Prospective price-band capture.** The official price-band list can be landed immutably with source URL/retrieval metadata now. It is deliberately `captured_unparsed`: receipt alone creates no `source_coverage`, no historical band assignment and no `band_close_state`.

## What r5.9 deliberately does not guess

- There is still no universal MII `master_file_date -> effective_session` formula. Unresolved master timing remains fail-closed.
- BE/BZ/right-entitlement semantics are not broadened by assumption.
- The price-band file does not yet drive execution. Actual historical files must establish its layout/date semantics and the exact exchange tick-rounding rule before that is allowed.
- Downloader success against the live NSE website is an external acceptance item because exchange anti-bot/session behaviour can change independently of this package.

## External acceptance still required

When Harsh next has access to the Windows warehouse machine:

```text
fresh Python 3.12 virtual environment outside the package
install only requirements-dev.txt
python run_all.py --require-parquet
```

Then ingest genuine NSE files for a small representative date set: UDiFF, MII security master, MTO and full-bhav delivery; capture the price-band file byte-exact. r5.9 should preserve the r5.8 3,637-observation real-data behavior, parse MTO without synthetic assumptions, keep the full-bhav file validation-only, and report the coverage state explicitly.

## Roadmap after r5.9 acceptance

Validate multi-date master timing and price-band semantics; measure archive depth and publication times; then continue Stage 0 with permanent security lineage/corporate actions, XBRL/fundamental history and remaining surveillance/F&O/share-count inputs before treating multi-year calibration/backtesting as serious strategy evidence.
