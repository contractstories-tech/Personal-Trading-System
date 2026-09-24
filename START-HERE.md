# START HERE — Equity Opportunity System

*Living handover document, updated by Claude at the end of every working session. It records where the project stands: status, decisions, open items and the next step. It sits outside the controlling package and controls nothing in it. On what the system is and does, the files bound by the package's `MANIFEST.json` control. If this file disagrees with them, the package is right and this file is out of date.*

**Last updated:** 24 September 2026 · **Current release:** r5.6 · **Current phase:** Stage 0. The review of r5.5 (run on Windows) is resolved in r5.6. **Next: run r5.6 on the Windows warehouse machine.** S1b waits for real NSE sample files

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

11. **Independent audit of r5.4 (24 Sep).** The audit reproduced every finding by execution. Its central finding was that nothing executed a card: a card with a 5% ROCE gate and a 4× ATR stop passed every check. Other findings:
   - undefined evaluation semantics;
   - undefined model-portfolio capacity, with personal values leaking into strategy measurement;
   - whole-registry pinning;
   - ISIN changes;
   - linter bypasses;
   - two point-in-time holes in the read path;
   - a Parquet-only store defect;
   - the fundamentals assembly;
   - ROCE edge cases;
   - a sign-only promotion rule;
   - prose-only features.

   Report and reproduction scripts: `audit/`.
12. **r5.5 — every audit finding resolved in the package, each with a test that fails against r5.4.**
   - **A reference card engine** runs each card's own expressions against hand-computed card-level cases. Planted card edits, including the audit's demonstration, are each caught.
   - **Normative, versioned evaluation semantics** live in the registry.
   - **Each card's `construction`** is part of its hypothesis; the allocator converts claims to weights of your capital.
   - **Cards pin only the registry entries they use.** Status lives in lifecycle records outside the card, which is your planned B7, done now together with H9 and S0.10.
   - **A reference implementation of every card-read feature**, with golden cases.
   - **A trial-scaled promotion hurdle.**
   - **A codec-independent store**, a lossless point-in-time panel, a backfill guard and row quarantine.
   - **A mutation check** on fixture adequacy.

13. **Review of r5.5, run on Windows (24 Sep).** Eleven of twelve pytest entry points passed on Windows. It found three Windows defects the Linux suite could not see: a directory fsync that makes every warehouse write fail on Windows, `SIGALRM` in the mutation check, and text read in the platform's default encoding. Its other findings:
   - muhurat semantics;
   - an unrankable security reaching the model portfolio;
   - confidence counting the wrong inputs;
   - no end-to-end goldens;
   - closures too broad;
   - lifecycle times compared as strings, including a future timestamp Claude had typed into the r5.5 records;
   - a stale lock after a crash;
   - no raw landing layer;
   - the panel presented as equal evidence;
   - a zero-variance crash;
   - authority wording;
   - unbound audit scripts.

   All were verified against r5.5 and all have merit.
14. **r5.6 — every finding of that review resolved, each with a test that fails on r5.5** (Issue Log §13).
   - **Warehouse:** per-platform durability (`MoveFileExW` write-through on Windows), an OS writer lock a crash releases, and write-once raw landing.
   - **Portability:** explicit UTF-8 throughout; a signal-free mutation check; pinned dev dependencies; one cross-platform `run_all.py`; portability regressions.
   - **Semantics:** evaluation semantics 1.1.0 (unrankable is never a candidate, confidence once per feature, a publication rule) and a muhurat session policy.
   - **Evidence and records:** end-to-end pipeline goldens; narrower closures; lifecycle ordered by instant; a degenerate promotion statistic that never passes; exact reads as the evidential standard.

Full history, with the disposition of every finding, is in the Issue Log.

## 3. Current state

**Specification:** r5.6. The review of r5.5 is dispositioned in Issue Log §13, and the audit of r5.4 in §12. Everything not yet fixed is scheduled to the phase where it first matters: **Document 01 §17** is the phase matrix.

**Product code:** Stage 0 slice S1, M2 price ingestion, in `eos/`. It was hardened in r5.4, made codec-independent in r5.5, and given in r5.6 per-platform durability, a crash-safe OS writer lock and write-once raw landing. Its full suite passes on Linux on both codecs, and on the Windows code paths under emulation.

**Executable references:**

- `reference_sim.py`: simulation, tax, corporate actions, promotion statistics.
- `reference_features.py`: every feature a card reads.
- `reference_engine.py`: what a card means, and `run_pipeline`, what a whole evaluation produces.

The production M5–M7 and M14 must reproduce them.

**What S1 has not yet touched:**

- **Nothing has run on Windows yet.** The warehouse machine runs Windows. r5.6's Windows paths (`MoveFileExW`, `msvcrt` locking) have run only against an emulation on Linux. `py -3.12 run_all.py --require-parquet` on that machine is the next gate.
- **No real exchange file has been parsed.** The parsers follow the documented layouts. They fail loudly on any header they don't recognise, and quarantine a defective row.
- **`band_close_state` is deliberately not built** until a real band file settles its semantics.
- **Reissue and deletion semantics (B10)**, and how a genuine no-trade row is stored, await real files.

**Package health at r5.6:** every command in the README's execution contract passes on Linux, under CPython 3.11.15 and 3.12.3, with the pinned dependencies (README, Certification).

- `test_speclint.py`: 118 cases, 2,004 malformed cards and no crash.
- `speclint.py`: both cards compile, as `experimental` per their lifecycle records.
- `test_golden.py`: 146 golden cases; 42 of 42 planted defects caught.
- `test_features.py`: 152 feature cases; 14 of 14 planted defects caught; every card-read feature covered.
- `test_card_golden.py`: 68 card cases; 12 of 12 planted card edits caught.
- `test_pipeline.py`: 4 end-to-end cases; 7 of 7 planted defects caught.
- `tests/test_m2.py`: 50 cases × 2 codecs × 2 platform paths (POSIX, Windows emulated) = 200 runs.
- `tests/test_portability.py`: 4 checks (static, bytes, CRLF naming, every suite under strict encoding).
- `mutation_check.py`: 589 mutation sites in `reference_sim.py` and `reference_features.py`, 87% killed, every survivor a reviewed equivalent.

## 4. The controlling package

The files bound by `MANIFEST.json` in the latest `equity-spec-kit-rX.Y.zip` are controlling. Everything else is history, including older revisions and any editable copy.

**Current package: `equity-spec-kit-r5.6.zip`** (digest in its `MANIFEST.json`). In the working repository, `equity-spec-kit/` is the same package, unzipped.

**Upload the zip itself to the project**, and remove the older loose files and zips.

The `.docx` copies of the documents are not updated per release; the `.md` files in the zip control.

At r5.6:

| Artefact | Revision |
| --- | --- |
| Overview | v5.6 |
| Document 01 — Core Platform Architecture | r9 (evaluation semantics §7; phase matrix §17) |
| Document 02 — Data Contract & Canonical Schema | r6 (session policy §3; read contracts §6; raw landing and durability §12) |
| Document 03 — Strategy Pack (card sections generated from YAML) | r8 |
| Document 04 — Validation Protocol | r5 |
| Issue Log & Traceability | r5.6 |
| Stage 0 Plan | r5.6 |
| `policies/source_policy.yaml` | 1.2.0 (backfill guard, quarantine limit) |
| `registry.yaml` | 3.1.0 (evaluation semantics 1.1.0, session policy 1.0.0; every entry versioned) |
| `strategies/ltqv_v1.yaml`, `strategies/mom_v1.yaml` | 1.0.0-prevalidation.9, schema v6, registered `experimental` by the r5.6 build at the real time |
| `eos/` product code | Stage 0 slice S1 |

**Authority order** (all inside the package; this file and `audit/` are outside it and control nothing):

1. The YAML cards are the only executable source of a strategy; their meaning is fixed by `reference_engine.py` and the card-level goldens.
2. `registry.yaml` owns every definition and the evaluation semantics.
3. Lifecycle records own every status.
4. Document 02 governs data; Document 01 architecture; Document 04 validation.
5. Document 03 explains and is generated. Where prose and YAML disagree, YAML wins.

**Verify before trusting.** `python run_all.py` runs every command in the README's execution contract; all must exit 0.

On the machine that holds the warehouse (Windows), `py -3.12 run_all.py --require-parquet` must also pass. Until it does, the Windows paths are untested on Windows.

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
| **Cards pin their registry closure**, not the whole file. A registry edit re-pins only the cards whose entries it touches *(r5.5; replaces the batched re-pin, which was done in r5.5)* | A registry edit must not re-version, and so burn the holdout of, an unrelated strategy |
| Each Document 07-class control is due at the phase where its absence first contaminates something (Document 01 §17), not all "before shadow" | Review 1 §6: several controls are needed much earlier |
| Two read contracts: `history_known_as_of(E)` for one decision; `point_in_time_panel` for a decision sequence | Review 1 B8 |
| Hidden files are never bound into the package | Issue R5.12 |
| No data-vendor spend until the XBRL prototype and the coverage report show the gaps in the free archives | The free exchange archives are already the primary source for everything exchange-originated |
| Thresholds are compared in exact arithmetic, never floating point | Issue S0.2 |
| The append-only trial log and lineage holdout enforcement are built **before the first calibration or backtest run** *(written into Document 01 §17 at r5.4 after Harsh's go-ahead; reversible if he objects)* | Exposure cannot be un-seen, so a log built later cannot record the trials that ran before it (B4) |
| Lifecycle status lives only in lifecycle records; the card carries none *(implemented r5.5)* | A status change must not alter the card's hash (B7) |
| **A card's sizing and construction are hypothesis parameters**, pre-registered before the first design evaluation; your values live only in `portfolio_policy.yaml` *(r5.5, audit A3)* | Personal settings must never change a strategy's measured results |
| **Exits fire when a thesis input turns out-of-domain in the failing direction**, using Kleene logic otherwise *(r5.5, audit A2; per-exit `on_out_of_domain: review` available)* | A collapsing holding must be sold, not held behind a review flag |
| **Promotion needs a Newey–West t above a hurdle that rises with logged trials**, and a holdout consistent with design *(r5.5, audit B7)* | Sign-only tests passed about 1 in 5 zero-alpha strategies |
| **Gate, exit, filter and flag inputs are quantised to 9 dp, then compared in Decimal** *(r5.5, audit C2)* | Floating-point summation order must not flip a decision |
| **Muhurat is a real trading session that the platform does not execute in or count** *(r5.6, registry `session_policy`; a policy choice, changeable only by a new policy version)* | One explicit rule instead of two contradictory sentences |
| **An unrankable security is never a candidate; a missing material ranking input means no rank** *(r5.6, evaluation semantics 1.1.0)* | Otherwise spare capacity admits securities the card could not score |
| **A claim is published only if the model portfolio takes it** (size checks at model size, capacity) and its confidence is at least medium; confidence never changes what the model holds *(r5.6)* | What is recommended must be what is measured |
| **Promotion evidence comes only from exact per-decision reads**; the first-known panel is exploration *(r5.6)* | The panel ignores corrections a decision could have known |
| **The warehouse machine is Windows**, and the Windows paths count as tested only when run there *(r5.6)* | Emulation proves the branch is taken, not that Windows behaves as modelled |

## 6. What is open

**Harsh's values** (nothing proceeds to shadow use until set):

- Every `OPEN` in `portfolio_policy.yaml`: total capital, caps per stock / sector / promoter group, maximum positions, minimum position, drawdown limit and response, cash floor, trim tolerance.
- Broker profile and actual charges — reconciled against one real contract note (including whether STT rounds to the rupee).

**Strategy design parameters** (set once, before each card's first design evaluation; not personal values):

- Each card's measurement capital, target volatility contribution or risk to the stop, maximum position, and `construction.max_positions`.

**Harsh's actions for Stage 0:**

- Download batch 1 of NSE sample files (Stage 0 Plan §5; about 25–30 files) and upload them unaltered. Never re-save them in Excel.
- **Run r5.6 on the Windows warehouse machine:** unzip `equity-spec-kit-r5.6.zip`; `py -3.12 -m pip install -r requirements-dev.txt`; `py -3.12 run_all.py --require-parquet`. Send back `run_all.log` if anything fails.
- Upload `equity-spec-kit-r5.6.zip` itself to the project.
- **Confirm or replace the two lifecycle records** that register both `.9` cards as `experimental`. The r5.6 build wrote them at the real time, on your instruction to make the review's changes, declaring that no sealed holdout result has been seen. The r5.5 records, which carried a hand-typed future time, are withdrawn (Issue Log §13, R6).
- Object, if you wish, to any r5.5 or r5.6 default in §5.
- **Recommended: take `mom_v1` end-to-end through validation before the XBRL-heavy `ltqv_v1` work.** It needs only exchange files and exercises the whole chain.

**Facts only Stage 0 can establish:**

- Surveillance framework start dates.
- Depth of the F&O, price-band and delivery archives.
- **Share-count history depth for the top-500 universe**, which gates both strategies.
- How often ISINs change on sub-division, and the real `security_lineage`.
- Whether rights-entitlement prices from 2020 were retained.
- The auditor-change disclosure archive, and related-party filings.
- Vendor point-in-time integrity.
- Current exchange-charge rate and stamp-duty sides.
- The FY 2024-25 tax straddle (the reference now pins the proposed treatment; confirmation is still due).
- How the Ind AS transition affects `ltqv_v1`'s evaluable window.
- How far back exchange XBRL financial results go. This decides whether a vendor is needed for `ltqv_v1`'s 16 years.
- Real NSE file layouts (S0.6), price-band file semantics (S0.7), Parquet on the warehouse machine (S0.8), and the quarantine limit on real files.

## 7. Roadmap

| Stage | What | Gate before moving on |
| --- | --- | --- |
| **0 — Data reality** | Exchange-file ingestion, XBRL parser prototype, security master (M1, with `security_lineage`), price ingester (M2), look-ahead canary, source-coverage report, vendor bake-off | Document 02 §17 acceptance |
| 1 — Point-in-time core | M3–M6, run manifests with snapshot persistence, orchestrator (M16) | PIT golden cases pass on real data; M6 equals `reference_features.py` |
| 2 — Strategy engines | M7–M9, backtest lab (M14), lifecycle registry (M17) | Production engine passes every golden file unmodified |
| 3 — Surfaces | Opportunity store, briefs and notifications, portfolio state (M15) | Lifecycle, reconciliation, actual-versus-model and non-execution tests |
| 4 — Shadow | Strategies run live without recommending | Promotion evidence per Document 04 |
| 5 — AI research | Change detector and AI extraction (M11–M12) | Document 05 |
| 6 — Intraday | Intraday data and engines | Intraday data contract and validation class |

Supporting documents still to write: Document 07 (build, release and operations — phased), Document 05 (AI evidence — before M12, including counter-evidence coverage conditions), Document 06 (presentation — before the dashboard).

## 8. The immediate next step

**First: r5.6 on Windows.** `py -3.12 run_all.py --require-parquet` on the warehouse machine. Every failure there is a real finding: fix it with a test, and never loosen the check.

**Then S1b: M2 on real files.** It starts when batch 1 is uploaded (Stage 0 Plan §5).

1. Run every batch-1 file through the parsers. Correct each parser to the real layout, and turn each real file into a fixture with hand-checked values. Every correction gets a test that would have caught it.
2. Settle the price-band file's semantics, then build `band_close_state` with golden cases.
3. Settle reissue semantics, adding tombstones if a reissue is a complete snapshot (B10).
4. Decide how a genuine no-trade row is stored. Quarantine already stops one such row from rejecting the day. Calibrate `max_quarantine_share` on the real files.
5. Take the first readings of archive depth and publication times. Those readings move `inferred_basis` from `unverified` to `measured` where live capture allows.
6. On the warehouse machine, run `py -3.12 run_all.py --require-parquet`. **Warehouse data is not trusted until it passes.**
7. When the scheduled downloader starts live capture, set `backfill.live_capture_start` in the source policy.

**If batch 1 is delayed,** S2 can start on synthetic data: the trading calendar, `security_lineage` across ISIN changes, the corporate-action arithmetic, the share-count seed, and the special-dividend threshold (H1).

**Later gates** are in Document 01 §17 and Issue Log §11. The next big one, before the first calibration run:

- the trial log and holdout enforcement;
- Brinson–Fachler with cash as a segment;
- the run-manifest validator;
- the simulation identity;
- each card's measurement parameters pre-registered.

Each slice ends with passing tests, an updated package, and an updated START-HERE.

## 9. Working agreement

1. Structural review of Documents 01–03 is closed. New findings go into the Issue Log, resolved with a regression or golden case, not another design round.
2. Every fix needs a test that would have caught it.
3. Claims about the package are verified by running it, never by reading the changelog.
4. Rules that matter live in the registry, a schema or a card expression — never only in prose.
5. A registry change re-pins only the cards whose closure it touches; a card whose meaning changed gets a new version and a new lifecycle registration.
6. A strategy's status changes only through a lifecycle transition record with the evidence its schema requires.
7. Harsh's reviewers' feedback is assessed on merit and verified against the code. Agreement is never assumed, and disagreement is stated plainly.
8. **At the end of every working session, Claude updates this file:** state, decisions, open items, next step, and the date.

## 10. Revision history of this file

| Date | Release | Change |
| --- | --- | --- |
| 24 Sep 2026 | r5.6 | Review of r5.5 (run on Windows) resolved: Windows durability and OS lock, raw landing, UTF-8 throughout, signal-free mutation check, `run_all.py`, evaluation semantics 1.1.0, session policy, pipeline goldens, narrower closures, lifecycle instants, degenerate promotion statistic, read-contract evidence labels. Authority wording corrected: the package controls, this file reports status |
| 24 Sep 2026 | r5.5 | Independent audit of r5.4 resolved: reference card engine and card-level goldens, evaluation semantics, construction and scale, closure pinning and lifecycle records, feature library, promotion hurdle, M2 fixes, mutation check |
| 23 Sep 2026 | r5.2 | Created as the living handover at the end of the specification phase |
| 24 Sep 2026 | r5.4 | Correction release: review findings that need no real data fixed with tests; three defects found while fixing; documents made consistent and checked automatically |
| 24 Sep 2026 | r5.3 | Four external reviews assessed and verified against the package; r5.4 correction scope set; two gate changes proposed |
| 23 Sep 2026 | r5.3 | Stage 0 plan; slice S1 (M2) built and tested on synthetic data; manifest release-label defect fixed; three defaults adopted; batch-1 download list issued |
