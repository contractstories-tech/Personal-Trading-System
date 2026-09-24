# START HERE — Equity Opportunity System

*Living handover document. Updated by Claude at the end of every working session. If this file and anything else disagree about where the project stands, this file wins.*

**Last updated:** 24 September 2026 · **Current release:** r5.4 · **Current phase:** Stage 0 — M2 hardened (r5.4); S1b waits for real NSE sample files

---

## 1. What we are building, and why

An **autonomous personal opportunity-discovery system for Indian listed equities.** It continuously evaluates the market across every validated strategy — long-term, momentum, swing, event and catalyst, intraday and any added later — on each strategy's own schedule. It recommends only when a strategy qualifies a security. It stays silent when nothing qualifies, and never places an order.

What Harsh wants from it, in his own terms:

- Stocks are never bucketed into categories. A strategy is a lens, not a label.
- No compulsion to recommend. Silence is a valid, expected output.
- Very autonomous and methodical: the system does the searching and monitoring; Harsh makes every decision and every trade.
- One opportunity per security, with each qualifying strategy's reasoning shown separately. Agreement between strategies is displayed, never used to size up.

**The end state:** a daily brief that says either "no qualifying opportunities — data healthy", or a few briefs. Each brief states what, why now, horizon, triggering values, supporting evidence, all material counter-evidence, data confidence, strategy status, portfolio fit, entry, invalidation and expiry. Every recommendation is traceable to point-in-time data, a validated strategy and a reproducible run.

## 2. How we got here

The project went through a deliberate sequence. Each step exists because the one before it exposed something.

1. **Concept note → Specification v3/v4.** Established point-in-time data, explicit unknowns, absolute gates, silence, and the AI boundary: AI reads documents, never scores or trades.
2. **Documents 01–03.**
   - 01: architecture and modules.
   - 02: the data contract.
   - 03: two reference strategies — long-term quality/value `ltqv_v1` and momentum `mom_v1` — written as YAML cards.
3. **Adversarial review rounds.** Repeated independent reviews, each verified by running code, never by trusting the documents. They found real defects every round, and the defects moved from architecture, to the data contract, to software-contract detail. That movement is the signal that prose review has reached its useful limit.
4. **r4 — a specification linter.** Cards became compiled rather than read.
5. **r5 — reframe and hardening.** Harsh clarified the product is multi-strategy and autonomous, not a two-strategy research platform. "Sleeves" became strategies; capital buckets became notional measurement capital plus one central allocator; intraday got an architectural home. The linter was rebuilt on a closed schema. Everything became hash-bound in `MANIFEST.json`.
6. **r5.1 — Document 04, the validation protocol,** with executable golden cases. Answers are hand-computed, and planted defects must all be caught.
7. **r5.2 — closing the last structural defects:**
   - two data-domain cutoffs
   - an allocator that takes the largest claim, never the sum
   - material inputs that block rather than waive
   - fills that cannot breach a hard cap
   - the market universe fixed at N = 500
   - a per-lineage holdout ledger
   - exact promotion metrics
   - schemas that enforce what they describe
8. **r5.3 — Stage 0 plan and the first product code.** `docs/Stage-0-Plan.md`, and M2 price ingestion in `eos/`. That covers parsers for both bhavcopy formats and MTO delivery, versioned observations, honest availability, as-of resolution, the look-ahead canary and an atomic warehouse. It is tested on synthetic NSE-shaped files. Verification also found the r5.2 manifest labelled "r5.1", which is now fixed and has a regression test.

9. **Four external reviews of r5.3 (24 Sep).** Each was checked against the package by running code, not by trusting its descriptions.
   - **Review 1** (independent assurance) is accurate. Every claim tested reproduced: the demerger formula contradiction, a crash mid-ingestion that leaves partial state and breaks retry, a two-writer race that creates duplicate version 2s, missing drawdown/Brinson metrics that Doc 04 claims exist, an evidence-free `production → retired`, no loss-vintage expiry in the tax view, a lenient date validator, cutoff identifiers typed as dates, and release drift across the documents.
   - **Review 2** is mostly inaccurate about the package. Seven of its nine findings describe behaviour the package already specifies or implements correctly. Two points have merit: the zero-price rows in real files, and operational friction.
   - **Review 3** could not open the package. It adds one small real gap: whether a muhurat bar counts in rolling windows.
   - **Review 4** is strategic. Its one recommendation that conflicts with a recorded decision (issuing research cards before validation) is rejected.
   - Dispositions are recorded in Issue Log §10.
10. **r5.4 — correction release (24 Sep).**
   - **Fixes:** every review finding that needs no real data, each with a test that fails against r5.3.
   - **Warehouse:** ingestion is batch-atomic and crash-recoverable, under one writer lock with per-thread re-entry.
   - **Reads and availability:** two read contracts; per-source availability; strict timestamps.
   - **Schemas and reference:** a real date check in the linter; evidence required for `production → retired`; the demerger ratio defined; tax losses carried by vintage and lapsing.
   - **Documents:** they agree with each other, checked automatically.
   - **Found while fixing, three more defects:** the thread re-entrancy hole in the new lock; a carried short-term loss relabelled as long-term; and a stray `docs/.git` bound into the first build.

Full history, with the disposition of every finding, is in the Issue Log.

## 3. Current state

**Specification:** r5.4. The four reviews of r5.3 are dispositioned in Issue Log §10. Everything not yet fixed is scheduled to the phase where it first matters: **Document 01 §17** is the phase matrix.

**Product code:** Stage 0 slice S1, M2 price ingestion, in `eos/`, hardened in r5.4.

**What S1 has not yet touched:**

- **No real exchange file has been parsed.** The parsers follow the documented layouts and fail loudly on any header they don't recognise.
- **The Parquet codec has not run.** The chat environment has no `pyarrow`.
- **`band_close_state` is deliberately not built** until a real band file settles its semantics.
- **Reissue and deletion semantics (B10)** await real files.

**Package health at r5.4:** all eight commands pass from a clean unzip.

- 92 linter regression cases, plus 1,860 malformed cards with zero crashes
- Both strategy cards compile
- 81 golden cases, with 32 of 32 planted defects caught
- Document 03 matches the YAML
- 38 M2 cases, covering:
  - a crash at every batch boundary, and during recovery
  - a real two-writer race
  - both read contracts
  - 8 of 8 planted read-path defects caught by the canary
  - the Parquet round-trip, which reports SKIP here
- 4 manifest regression cases
- Release consistency across all documents
- Manifest verifies its files, its digest and its release label, and refuses hidden files

## 4. The controlling package

The files bound by `MANIFEST.json` in the latest `equity-spec-kit-rX.Y.zip` are controlling. Everything else is history, including older revisions and any editable copy.

**Current package: `equity-spec-kit-r5.4.zip`**, package digest `67bf137fef310dd1…` (44 files).

**Upload the zip itself to the project**, and remove the older loose files and zips. Until the zip is in the project, each session rebuilds the layout from `MANIFEST.json` and checks every file's hash.

The `.docx` copies of the documents are not updated per release; the `.md` files in the zip control.

At r5.4:

| Artefact | Revision |
| --- | --- |
| Overview | v5.4 |
| Document 01 — Core Platform Architecture | r7 (phase matrix in §17) |
| Document 02 — Data Contract & Canonical Schema | r4 |
| Document 03 — Strategy Pack (card sections generated from YAML) | r6 |
| Document 04 — Validation Protocol | r3 |
| Issue Log & Traceability | r5.4 |
| Stage 0 Plan | r5.4 |
| `policies/source_policy.yaml` | 1.1.0 (per-source availability) |
| `eos/` product code | Stage 0 slice S1, hardened |
| `registry.yaml` | 2.2.0 |
| `strategies/ltqv_v1.yaml`, `strategies/mom_v1.yaml` | 1.0.0-prevalidation.7 |

**Authority order:**

1. The YAML cards are the only executable source of a strategy.
2. `registry.yaml` owns every definition.
3. Document 02 governs data; Document 01 architecture; Document 04 validation.
4. Document 03 explains and is generated. Where prose and YAML disagree, YAML wins.

**Verify before trusting.** Every command must exit 0:

```bash
python3 make_manifest.py --verify
python3 test_speclint.py
python3 speclint.py
python3 test_golden.py
python3 render_cards.py --check docs/Strategy-Pack-Doc-03-r6.md
python3 tests/test_m2.py
python3 tests/test_manifest.py
python3 tests/test_release.py
```

On the machine that holds the warehouse, `python3 tests/test_m2.py --require-parquet` must also pass.

## 5. Decisions already made — do not silently revisit

| Decision | Why |
| --- | --- |
| Market-eligible universe = point-in-time top 500 by market cap | Broad search; each strategy's liquidity gates screen thin names |
| Scarce capacity: existing holdings → earliest signal → larger market cap → ISIN | Deterministic, with no invented cross-strategy score |
| Security size = largest live claim, never the sum | Agreement between strategies must not double exposure |
| Material inputs block when unknown; only secondary inputs may be penalised (one confidence band) | Otherwise a strategy silently becomes a different strategy wherever data is missing |
| `ltqv_v1` has no audit-opinion gate in v1 | Its data doesn't exist yet; waiving it would validate a strategy without the check. It returns as a new version |
| Momentum delivery gate blocks when data is missing | Delivery is part of the momentum hypothesis |
| Delivery bands pre-registered at the 25th percentile, design period only | Fixed before looking, so it can't be fitted |
| Tax is a view, never a gate; promotion judged after costs, before tax | Tax rule changes shouldn't invalidate an economically sound strategy |
| Quantities capped at the worst permitted fill | A higher fill can never breach the position or risk limit |
| Two cutoff domains: disclosures 20:00, exchange end-of-day files 23:00 | One scalar cutoff cannot express the policy |
| Holdout exposure tracked per strategy lineage | Renaming a version can't make seen data unseen |
| No order path. Any broker credential must be read-only at the broker, or none is mounted | Research and recommendation only; execution stays manual |
| Intraday is architecturally reserved, built later | Needs its own data contract, fills and validation class |
| Backfilled exchange files: a row's **first** version is inferred available at its source's own time — currently 22:30 IST for both bhavcopy and delivery, marked `unverified`. Later versions are available only when actually received *(default adopted 23 Sep; made per-source 24 Sep)* | Archives carry no publication time. The time must fall before the 23:00 cutoff, and a correction must never be back-dated |
| Delivery is stored as its own versioned table, joined in the resolved price view | Separate source, arrival time, corrections and coverage (Issue S0.3) |
| **Registry and card-schema re-pins** are batched into one at Stage 0 close (H9, B7, S0.10). Document text known to be wrong is corrected when found, as Doc 02 r4 was *(adopted 23 Sep; refined 24 Sep)* | Avoids re-pinning cards every slice, without leaving a governing document wrong |
| Each Document 07-class control is due at the phase where its absence first contaminates something (Document 01 §17), not all "before shadow" | Review 1 §6: several controls are needed much earlier |
| Two read contracts: `history_known_as_of(E)` for one decision; `point_in_time_panel` for a decision sequence | Review 1 B8 |
| Hidden files are never bound into the package | Issue R5.12 |
| No data-vendor spend until the XBRL prototype and the coverage report show the gaps in the free archives | The free exchange archives are already the primary source for everything exchange-originated |
| Thresholds are compared in exact arithmetic, never floating point | Issue S0.2 |
| The append-only trial log and lineage holdout enforcement are built **before the first calibration or backtest run** *(written into Document 01 §17 at r5.4 after Harsh's go-ahead; reversible if he objects)* | Exposure cannot be un-seen, so a log built later cannot record the trials that ran before it (B4) |
| Lifecycle status leaves the immutable card; M17 is its only authority *(accepted; implemented at the Stage 0 re-pin)* | A status-only change currently alters the card's hash (B7) |

## 6. What is open

**Harsh's values** (nothing proceeds to shadow use until set):

- Every `OPEN` in `portfolio_policy.yaml`: total capital, caps per stock / sector / promoter group, maximum positions, minimum position, drawdown limit and response, cash floor, trim tolerance.
- Each card's sizing values: notional capital, target volatility contribution or risk-to-stop, maximum position.
- Broker profile and actual charges — reconciled against one real contract note.

**Harsh's actions for Stage 0:**

- Download batch 1 of NSE sample files (Stage 0 Plan §5; about 25–30 files) and upload them unaltered. Never re-save them in Excel.
- Set up the warehouse machine: Python 3.12, `PyYAML==6.0.3` and `pyarrow`. Report the `pyarrow` version so it can be pinned.
- Upload `equity-spec-kit-r5.4.zip` itself to the project.
- Object, if you wish, to the two defaults adopted on 23 Sep (§5).
- Confirm or reverse the trial-log gate written into Document 01 §17 (§5).
- Decide whether `mom_v1` goes end-to-end through validation before the XBRL-heavy `ltqv_v1` work.

**Facts only Stage 0 can establish:**

- Surveillance framework start dates.
- Depth of the F&O, price-band and delivery archives.
- Whether rights-entitlement prices from 2020 were retained.
- The auditor-change disclosure archive, and related-party filings.
- Vendor point-in-time integrity.
- Current exchange-charge rate and stamp-duty sides.
- The FY 2024-25 tax straddle.
- How the Ind AS transition affects `ltqv_v1`'s evaluable window.
- How far back exchange XBRL financial results go. This decides whether a vendor is needed for `ltqv_v1`'s 16 years.
- Real NSE file layouts (S0.6), price-band file semantics (S0.7), and Parquet on the warehouse machine (S0.8).

## 7. Roadmap

| Stage | What | Gate before moving on |
| --- | --- | --- |
| **0 — Data reality** | Exchange-file ingestion, XBRL parser prototype, security master (M1), price ingester (M2), look-ahead canary, source-coverage report, vendor bake-off | Document 02 §17 acceptance |
| 1 — Point-in-time core | M3–M6, run manifests, orchestrator (M16) | PIT golden cases pass on real data |
| 2 — Strategy engines | M7–M9, backtest lab (M14), lifecycle registry (M17) | Production engine passes every golden case unmodified |
| 3 — Surfaces | Opportunity store, briefs and notifications, portfolio state (M15) | Lifecycle, reconciliation and non-execution tests |
| 4 — Shadow | Strategies run live without recommending | Promotion evidence per Document 04 |
| 5 — AI research | Change detector and AI extraction (M11–M12) | Document 05 |
| 6 — Intraday | Intraday data and engines | Intraday data contract and validation class |

Supporting documents still to write: Document 07 (build, release and operations — before shadow use), Document 05 (AI evidence — before M12), Document 06 (presentation — before the dashboard).

## 8. The immediate next step

**S1b: M2 on real files.** It starts when batch 1 is uploaded (Stage 0 Plan §5).

1. Run every batch-1 file through the parsers. Correct each parser to the real layout, and turn each real file into a fixture with hand-checked values. Every correction gets a test that would have caught it.
2. Settle the price-band file's semantics, then build `band_close_state` with golden cases.
3. Settle reissue semantics, adding tombstones if a reissue is a complete snapshot (B10).
4. Decide how zero-price and zero-volume rows are handled. Today's OHLC check would reject a whole file containing one.
5. Take the first readings of archive depth and publication times. Those readings move `inferred_basis` from `unverified` to `measured` where live capture allows.
6. On the warehouse machine, install and pin `pyarrow`, and get `tests/test_m2.py --require-parquet` passing. **Warehouse data is not trusted until then.**

**If batch 1 is delayed,** S2 can start on synthetic data: the trading calendar (including whether a muhurat bar counts in rolling windows), the corporate-action arithmetic, and the special-dividend threshold (H1).

**Later gates** are in Document 01 §17 and Issue Log §11. The next big one: before the first calibration run, build the trial log, holdout enforcement, drawdown and Brinson–Fachler (with cash as a segment), the run-manifest validator, and the simulation identity.

Each slice ends with passing tests, an updated package, and an updated START-HERE.

## 9. Working agreement

1. Structural review of Documents 01–03 is closed. New findings go into the Issue Log, resolved with a regression or golden case, not another design round.
2. Every fix needs a test that would have caught it.
3. Claims about the package are verified by running it, never by reading the changelog.
4. Rules that matter live in the registry, a schema or a card expression — never only in prose.
5. A registry change re-pins every card, by version and SHA-256, and bumps card versions.
6. A strategy's status changes only through a lifecycle transition record with the evidence its schema requires.
7. Harsh's reviewers' feedback is assessed on merit and verified against the code. Agreement is never assumed, and disagreement is stated plainly.
8. **At the end of every working session, Claude updates this file:** state, decisions, open items, next step, and the date.

## 10. Revision history of this file

| Date | Release | Change |
| --- | --- | --- |
| 23 Sep 2026 | r5.2 | Created as the living handover at the end of the specification phase |
| 24 Sep 2026 | r5.4 | Correction release: review findings that need no real data fixed with tests; three defects found while fixing; documents made consistent and checked automatically |
| 24 Sep 2026 | r5.3 | Four external reviews assessed and verified against the package; r5.4 correction scope set; two gate changes proposed |
| 23 Sep 2026 | r5.3 | Stage 0 plan; slice S1 (M2) built and tested on synthetic data; manifest release-label defect fixed; three defaults adopted; batch-1 download list issued |
