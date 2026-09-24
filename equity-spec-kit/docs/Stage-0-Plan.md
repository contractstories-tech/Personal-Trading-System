# Stage 0 Plan — Data Reality

*Release r5.4 · 24 September 2026 · living plan; status per slice is kept in START-HERE.md*

Stage 0 proves the data exists, can be parsed, and can be made point-in-time honestly. It closes on Document 02 §17's acceptance list and nothing less. Every verification item there ends as a confirmed fact or a documented limitation.

## 1. Where the work runs

The chat environment has **no internet and no `pyarrow`**. The split is therefore:

- **Development happens in chat**, against sample files Harsh uploads.
- **The warehouse lives on Harsh's machine**, which downloads files and runs ingestion.
- **What that machine needs:** Python 3.12, `PyYAML==6.0.3`, and `pyarrow`. Install `pyarrow` once and report its version so it can be pinned.
- **Warehouse-machine gate:** before any real data is trusted there, `python3 tests/test_m2.py --require-parquet` must pass on that machine.

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
    m2/  parsers.py  ingest.py  resolve.py
  tests/                    product tests (fixtures are synthetic until real samples arrive)

warehouse/                  on Harsh's machine, never in the package
  price_observation/p=YYYY-MM-DD/part-NNNNN-<sha>.parquet + _manifest.json
  delivery_observation/…  source_coverage/…  ingestion_log/…  data_conflict/…
```

Parts are immutable. The manifest is the only list of what exists. Readers never glob. A snapshot freezes the set of manifests a run may read.

## 4. Order of work

| Slice | Scope | Done when |
| --- | --- | --- |
| **S1 — M2 prices** (r5.3, hardened r5.4) | Parsers for both bhavcopy formats and MTO delivery; versioned observations; per-source availability; two read contracts; canary; batch-atomic, locked warehouse | ✅ on synthetic data (counts in README); crash at every batch boundary and a two-writer race tested |
| **S1b — M2 on real files** | Harden the parsers on batch 1; band file and `band_close_state`; reissue semantics and tombstones if needed (B10); zero-price or zero-volume rows; Parquet on the warehouse machine; first archive-depth and publication-time readings | Batch 1 parses exactly; `--require-parquet` passes; S0.6–S0.8 and B10 closed |
| S2 — M1 security master | Trading calendar (muhurat, special pre-open, and whether a muhurat bar counts in rolling windows); ISIN identity and aliases, including symbol reuse across decades; corporate actions, with the special-dividend threshold settled (H1); share counts; adjusted and total-return series | Continuous series across a split, a bonus, a rights issue and a demerger, stub valued |
| S3 — XBRL prototype | Same three securities in 2015, 2019 and 2024 filings; duration normalisation; restatements | Doc 02 §17 XBRL items pass; depth of free XBRL history measured |
| S4 — Coverage report | Surveillance and F&O start dates; band, delivery and rights-entitlement depth; auditor-change and related-party archives | Every §17 verification item confirmed or a documented limitation |
| S5 — Vendor bake-off | Only if S3 shows the gap: 30–50 securities, timestamps and restatement history | Pass/fail per vendor recorded |
| Close | The next Document 02 revision, carrying every remaining Stage 0 correction; one registry and card-schema re-pin (H9, B7, S0.10) | Doc 02 §17 acceptance |

## 5. Files to download — batch 1 (needed now, for S1b)

Download from NSE's website (nseindia.com → All Reports → Equities, choosing the date). **Keep each file exactly as downloaded, zipped if it came zipped.** Never open and re-save a file in Excel: Excel rewrites dates, drops trailing columns and changes number formats, so the parser would be tested against Excel's output rather than NSE's.

| # | File | Dates | Why |
| --- | --- | --- | --- |
| 1 | CM bhavcopy, **old format** (`cmDDMONYYYYbhav.csv`) | The last three trading days before NSE switched format in early July 2024 | Legacy parser, back-to-back days |
| 2 | CM bhavcopy, **new format** (`BhavCopy_NSE_CM_…_YYYYMMDD_…csv`) | The first three trading days after the switch, and three recent days (e.g. 16–18 Sep 2026) | UDiFF parser, both ends of its history |
| 3 | Both formats for **one same date**, if NSE ever published both | Any overlap date | Proves the two parsers agree on real data |
| 4 | Security-wise delivery (`MTO_DDMMYYYY.DAT`) | Every date in 1 and 2 | Delivery parser and symbol-to-ISIN mapping |
| 5 | Price-band file (`sec_list` or its current name), plus any band-hitters report | The same dates | Settles S0.7 |
| 6 | Full bhavcopy with delivery (`sec_bhavdata_full_DDMMYYYY.csv`) | One of the dates | A second delivery source to cross-check against |
| 7 | CM bhavcopy | One day each in 2010 and 2015 | Oldest format variants; first read on archive depth |
| 8 | CM bhavcopy | The Diwali 2024 Muhurat session (confirm the date on NSE's holiday list) | Session-type handling |

Expect about 25–30 small files. Upload them to this project or to a chat.

## 6. Batch 2 (later, for S2)

Bhavcopies around, and the exchange announcements for, one each of: a split, a bonus, a rights issue with traded entitlements (2020 or later), and a demerger with a special pre-open session. The actual events are chosen at S2 from the corporate-action archive, not from memory.

## 7. Decisions this plan asks of Harsh

1. **Inferred availability of backfilled exchange files at 22:30 IST on the trade date** (S0.4). Adopted as the default; object if you disagree.
2. **Registry re-pins batched into one at Stage 0 close** (S0.10, H9, B7). Adopted as the default. Document 02 text that is known to be wrong is corrected when found (r4 at r5.4).
3. **No data vendor spend until S3/S5.**
4. **The warehouse machine,** set up per §1.

## 8. Known limitations carried

- **Pre-capture corrections are lost (S0.5).** Archives hold only corrected files, so corrections made before live capture began cannot be recovered.
- **Parsers are unproven on real data (S0.6).** They fail loudly rather than guess.
- **`band_close_state` is not built (S0.7).**
