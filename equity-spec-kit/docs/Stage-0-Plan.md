# Stage 0 Plan — Data Reality

*Release r5.9 · 25 September 2026 · living plan; status per slice is kept in START-HERE.md*

Stage 0 proves the data exists, can be parsed, and can be made point-in-time honestly. It closes on Document 02 §17's acceptance list and nothing less. Every verification item there ends as a confirmed fact or a documented limitation.

## 1. Where the work runs

The build environment used for r5.9 has **no PyArrow/network installation path**; the Windows warehouse machine does. The split is therefore:

- **Development happens in chat**, against sample files Harsh uploads.
- **The warehouse lives on Harsh's machine**, which downloads files and runs ingestion.
- **The warehouse machine runs Windows.** It needs Python 3.12 and `python -m pip install -r requirements-dev.txt` (PyYAML 6.0.3, pyarrow 25.0.1, pytest 9.1.1). Keep the kit's files byte-exact: unzip it as delivered, or, in git, keep the repository's `* -text` attribute so line endings are never converted.
- **Warehouse-machine gate:** before any real data is trusted there, `py -3.12 run_all.py --require-parquet` must pass **on that machine**. It runs every contract command, including every M2 case on both codecs through the real Windows primitives (`MoveFileExW` write-through, `msvcrt` locking). Elsewhere those paths are only exercised against an emulation (README, Certification).

## 2. Sources

| Domain | Source | Cost | History needed | Decision |
| --- | --- | --- | --- | --- |
| Daily prices, traded value | NSE CM bhavcopy archive | Free | 16 years (`ltqv_v1`: 7 warm-up + 9 evaluable); 12 for `mom_v1` | Use the archive; measure its depth |
| Delivery | NSE security-wise delivery (MTO) archive | Free | 12 years (momentum delivery gate) | Use the archive; measure its depth — delivery missing means the momentum gate *blocks* |
| Price bands | NSE daily price-band files | Free | Full evaluable window | Measure coverage; uncovered periods are excluded from evidence (Doc 04) |
| Corporate actions | NSE/BSE announcements | Free | 16 years | Primary. Vendor only as a validation source |
| Surveillance (ASM/GSM), F&O eligibility | NSE lists and contract files | Free | From framework start | Verify framework start dates |
| Financial statements | Exchange XBRL; licensed vendor | Free / paid | 16 years ⇒ from about FY 2009-10 | **Open.** How far back exchange XBRL results go decides whether a vendor is needed. No vendor spend until the XBRL prototype has measured this |
| Benchmarks, G-sec | NSE Indices TRI; RBI/FBIL | Free | Full window | Later slice |

**Recommendation:** spend nothing on data until slices S3 and S5 show which gaps the free archives leave. A vendor that cannot show exchange-traceable filing timestamps and restatement history fails the bake-off, whatever its price (Doc 02 §2).

## 3. Layout

```
equity-spec-kit/            one controlling package, hash-bound by MANIFEST.json
  docs/  registry.yaml  strategies/  schemas/  policies/  golden/   the specification
  eos/                      product code
    pit.py  timeutil.py  source_policy.py  store.py  canary.py
    m2/  parsers.py  ingest.py  resolve.py     prices, delivery, MII security master, canonical/no-trade resolution
  tests/                    product tests (fixtures are synthetic until real samples arrive)

warehouse/                  on Harsh's machine, never in the package
  price_observation/p=YYYY-MM-DD/part-NNNNN-<sha>.parquet + _manifest.json
  delivery_observation/…  security_master_observation/…  observation_tombstone/…
  source_coverage/…  ingestion_log/…  data_conflict/…
```

Parts are immutable. The manifest is the only list of what exists. Readers never glob. A snapshot freezes the set of manifests a run may read.

## 4. Order of work

| Slice | Scope | Done when |
| --- | --- | --- |
| **S1 — M2 prices** (r5.3, hardened through r5.9) | Legacy + UDiFF prices, MTO delivery, raw/provenance/integrity controls, source identity, multi-series observations, point-in-time corrections/tombstones, source/canonical price views and explicit no-trade states | ✅ on synthetic/real-derived goldens. r5.7 is native-Windows/Parquet certified. r5.9 build: 66 M2 cases × POSIX/Windows-sim JSONL = 132/132, plus 3/3 source-catalogue/acquisition checks; native-Windows/Parquet and genuine delivery/price-band file acceptance still required. |
| **S1b — current MII reference + real files** | r5.8 pulled the daily MII reference slice forward. r5.9 hardens MTO, adds `sec_bhavdata_full` validation evidence, explicit source catalogue/downloader and coverage report, and starts immutable price-band capture without assigning unproven band semantics. Continue with actual multi-date files, archive depth and publication-time readings | 24-Sep real-file behaviour is represented by goldens; actual r5.8 24-Sep re-ingest preserves 3,637 source rows; multi-date UDiFF/MII sample clean; `--require-parquet` passes; effective-session limitations documented rather than guessed |
| S2 — M1 long-run security lineage and corporate actions | Trading calendar with `session_type`; permanent `security_lineage` across ISIN changes/symbol reuse; corporate actions; share counts; adjusted/total-return series. The narrow daily MII reference ingest is no longer deferred to S2. | Continuous series across a split with an ISIN change, a bonus, a rights issue and a demerger, stub valued |
| S3 — XBRL prototype | Same three securities in 2015, 2019 and 2024 filings; duration normalisation; restatements | Doc 02 §17 XBRL items pass; depth of free XBRL history measured |
| S4 — Coverage report | Surveillance and F&O start dates; band, delivery and rights-entitlement depth; auditor-change and related-party archives; **share-count history depth for the top-500 universe** (it gates both strategies) | Every §17 verification item confirmed or a documented limitation |
| S5 — Vendor bake-off | Only if S3 shows the gap: 30–50 securities, timestamps and restatement history | Pass/fail per vendor recorded |
| Close | The next Document 02 revision, carrying every remaining Stage 0 correction (the registry re-pin of H9, B7 and S0.10 was done in r5.5) | Doc 02 §17 acceptance |

## 5. Files to download — batch 1 (needed now, for S1b)

Download from NSE's website (nseindia.com → All Reports → Equities, choosing the date). **Keep each file exactly as downloaded, zipped if it came zipped.** Never open and re-save a file in Excel: Excel rewrites dates, drops trailing columns and changes number formats, so the parser would be tested against Excel's output rather than NSE's.

| # | File | Dates | Why |
| --- | --- | --- | --- |
| 1 | CM bhavcopy, **old format** (`cmDDMONYYYYbhav.csv`) | The last three trading days before NSE switched format in early July 2024 | Legacy parser, back-to-back days |
| 2 | CM bhavcopy, **new format** (`BhavCopy_NSE_CM_…_YYYYMMDD_…csv`) | The first three trading days after the switch, and three recent days (e.g. 16–18 Sep 2026) | UDiFF parser, both ends of its history |
| 3 | Both formats for **one same date**, if NSE ever published both | Any overlap date | Proves the two parsers agree on real data |
| 4 | CM MII Security File (`NSE_CM_security_DDMMYYYY.csv.gz`, **NSE Listed securities**) | Each recent UDiFF date selected in 2, plus dates immediately around at least two known symbol/listing/status transitions | Source-token reconciliation, company-equity classification and master effective-session evidence |
| 5 | Security-wise delivery (`MTO_DDMMYYYY.DAT`) | Every date in 1 and 2 | Delivery parser and symbol-to-ISIN/source mapping |
| 6 | Price-band file (`sec_list` or its current name), plus any band-hitters report | The same dates | Settles S0.7 |
| 7 | Full bhavcopy with delivery (`sec_bhavdata_full_DDMMYYYY.csv`) | One of the dates | A second delivery source to cross-check against |
| 8 | CM bhavcopy | One day each in 2010 and 2015 | Oldest format variants; first read on archive depth |
| 9 | CM bhavcopy | The Diwali 2024 Muhurat session (confirm the date on NSE's holiday list) | Session-type handling |

Expect about 30–35 small files. The objective is representative semantics, not an exhaustive edge-case collection. Upload them to this project or to a chat.

## 6. Batch 2 (later, for S2)

Bhavcopies around, and the exchange announcements for, one each of: a split, a bonus, a rights issue with traded entitlements (2020 or later), and a demerger with a special pre-open session. The actual events are chosen at S2 from the corporate-action archive, not from memory.

## 7. Decisions this plan asks of Harsh

1. **Inferred availability of backfilled exchange files at 22:30 IST on the trade date** (S0.4). Adopted as the default; object if you disagree.
2. **Registry re-pins.** Done in r5.5. Cards now pin only the registry entries they use, so later registry edits re-pin only the cards they touch.
3. **No data vendor spend until S3/S5.**
4. **The warehouse machine,** set up per §1.

## 8. Known limitations carried

- **Pre-capture corrections are lost (S0.5).** Archives hold only corrected files, so corrections made before live capture began cannot be recovered.
- **Real-file breadth remains limited (S0.6).** Current UDiFF and MII layouts have been exercised and encoded as regressions, but a modest multi-date sample around format/listing/status transitions is still required before broad backfill.
- **`band_close_state` is not built (S0.7).**
