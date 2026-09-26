# START HERE — r5.10 handover

*26 September 2026 · non-normative status note; the manifest-bound specifications, registry, cards and schemas control on any conflict*

## Status

- **r5.7 is the last native-Windows/Parquet-certified baseline.** A clean Windows 11 / Python 3.12.10 environment, installing only the declared dependencies, ended `ALL PASSED`.
- **r5.8** corrected real NSE price and security-reference semantics. **r5.9** added delivery evidence, a source catalogue, a downloader, coverage reporting and price-band capture. Neither has had its native-Windows run.
- **r5.10 is an integrity release over r5.9.** It fixes every finding from the reviews of r5.7, r5.8 and r5.9 (Issue Log §17), none of which had reached the Issue Log before. From a clean unzip it passes every contract command, with Parquet, on Linux under CPython 3.11, 3.12 and 3.13.

## What r5.10 fixes

1. **No correction is back-dated across file formats.** An observation is (ISIN, series, date) in legacy and UDiFF alike, and `FinInstrmId` is kept as an attribute. In r5.8–r5.9, a correction arriving in the other format became a "first version" usable on the trade date: look-ahead, followed by a failed canonical read.
2. **Withdrawals need proof.** A row missing from a later file is tombstoned only when the source policy says reissues are complete snapshots (`reissue_semantics`, now `unverified` everywhere) and the file is in the same format. Otherwise the row is kept and the omission logged.
3. **Every landed file has a recorded outcome**, including files that parse but fail a quality check.
4. **MTO and full-bhav delivery are actually compared**, logging mismatches without changing either value.
5. **The downloader:**
   - refuses HTML block pages, wrong file formats, off-NSE hosts (including redirects) and back-dated live captures;
   - paces its requests and never overwrites an earlier download;
   - knows the pre-July-2024 bhavcopy URL layout.
6. **The coverage report** counts weekdays and never creates a warehouse from a mistyped path.
7. **The mutation check really tests the engine.** Since r5.7 no engine mutant had ever run: a mutant that failed to *build* was counted as killed. The 22 real survivors are now closed (21 by new goldens, 1 reviewed equivalent), and a failure to build is an infrastructure error.
8. **Gate-only capacity** breaks equal signal times on market cap, then ISIN. The model never reserves more cash than its maximum position.

## What r5.10 still does not guess

- Whether NSE reissues are complete snapshots (no tombstones until a real reissue shows it).
- The exact date the bhavcopy became UDiFF-only: 8 July 2024 is assumed, and it only chooses which URL to try.
- The MTO header's declared-count field on a real file (a wrong assumption fails loudly).
- The MII effective-session convention, and the price-band layout, date semantics and tick rounding.

## Your acceptance steps

On the Windows warehouse machine:

```text
unzip equity-spec-kit-r5.10.zip into a clean folder; keep the virtual environment OUTSIDE it
py -3.12 -m venv C:\EquitySystem\venv510
C:\EquitySystem\venv510\Scripts\python -m pip install -r requirements-dev.txt
C:\EquitySystem\venv510\Scripts\python run_all.py --require-parquet
```

It must end `ALL PASSED`; if it doesn't, send `run_all.log`. Then re-ingest the untouched 24-Sep UDiFF and MII files, plus MTO, full-bhav and price-band files for a few dates, and run `coverage_report.py`:
- all 3,637 bhavcopy observations should survive;
- ingesting a date in the other format should report every row unchanged;
- MTO/full-bhav mismatches, if any, appear as conflicts.

Try `fetch_nse.py` for one file of each source; live NSE behaviour can only be tested there.

## Roadmap after acceptance

Settle the open items in Issue Log §17's register (reissue semantics, the format cut-over date, the MTO count, MII timing, price bands). Measure archive depth and publication times. Then continue Stage 0 with security lineage and corporate actions, XBRL fundamentals, and the surveillance, F&O and share-count inputs, before any multi-year calibration or backtest counts as evidence.
