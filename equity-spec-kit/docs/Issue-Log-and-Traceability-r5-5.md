# Issue Log & Traceability — Releases r5 / r5.1 / r5.2 / r5.3 / r5.4 / r5.5

*24 September 2026 · every finding from review indices 17–22 and 42–43, the independent assurance audit (F01–F16), Stage 0 (S0.x), the four external reviews of r5.3 (§10) and the independent audit of r5.4 (§12), with its disposition*

**Dispositions:** **Fixed** (where) · **Modified** (adopted with a change; reason given) · **Deferred** (named owner and gate) · **Rejected** (reason) · **Retained** (already correct; kept deliberately).

**Verification.** Every "Fixed" item needs a test that would have caught it:

- **Items the linter can express** get a regression case in `test_speclint.py`.
- **Items it cannot express** get a golden case, with a planted mutant: `test_golden.py` for simulation and policy, `test_features.py` for feature definitions, `test_card_golden.py` for what a card means.
- **Product-code items** get a test in `tests/`.
- **Fixture adequacy** is checked by `mutation_check.py`: a new unexplained survivor is a missing case.

Current counts are in the README. Sections below record history, and cite the revisions current when each finding was made.

## 1. Product reframe (index 21)

| # | Finding | Disposition |
| --- | --- | --- |
| 21.1 | Define the product as autonomous opportunity discovery and recommendation | Fixed — Overview §1 |
| 21.2 | "Sleeve" implies capital buckets; use "strategy" | Fixed — terminology throughout; `sleeve`, `sleeve_capital` retired in the registry, so the linter rejects them |
| 21.3 | Open-ended strategy registry; platform strategy-agnostic | Fixed — registry `strategy_classes`; Doc 01 §4 |
| 21.4 | The two strategies are reference implementations, not the product boundary | Fixed — Overview §5; Doc 03 §2 |
| 21.5 | Intraday supported architecturally from the start | Fixed — `intraday` class, resolutions and triggers registered; Doc 02 §16 reserved contract; linter blocks promotion until implemented. Build still later (Doc 01 §17 stage 6) |
| 21.6 | Separate EOD, event and intraday data contracts | Fixed — registry `data_resolutions`; Doc 02 §16 |
| 21.7 | Scheduled and event-triggered orchestration | Fixed — M16 Orchestrator; registered triggers; Doc 01 §5 |
| 21.8 | Opportunity as the central object with strategy claims | Fixed — Doc 01 §9 |
| 21.9 | Show conflicting strategies, don't synthesise consensus | Fixed — Doc 01 §9 |
| 21.10 | Ranking must not be mandatory | Fixed — `selection_method: gate_only \| rank_and_gate`; linter enforces consistency |
| 21.11 | No quota | Retained |
| 21.12 | Validation by strategy class | Fixed in registry (`validation_class`); protocols → Document 04 |
| 21.13 | Keep the lifecycle; only production recommends | Fixed and strengthened — Doc 01 §10 |
| 21.14 | Central allocator; no fixed capital buckets | Fixed — notional capital for measurement only; `portfolio_policy.yaml` with `per_strategy_pct: NONE` default |
| 21.15 | Valid but not currently actionable | Fixed — Doc 01 §6, §9 |
| 21.16 | AI-derived inputs allowed if declared, versioned, validated | Fixed — `ai_inputs` in card; registry `ai_derived` plus verification path; Doc 01 §16 |
| 21.17 | New strategies cannot recommend without the lifecycle | Fixed — Doc 01 §4 |
| 21.18 | Compact opportunity brief | Fixed — Doc 01 §12 |
| 21.19 | "Two strongest contradicting facts" manufactures objections | Fixed — all material counter-evidence, or an explicit "none found" |
| 21.20 | Separate notification policy from generation | Fixed — Doc 01 §12 |
| 21.21 | Monitor opportunities and report what changed | Fixed — Doc 01 §12 |
| 21.22 | Model versus actual portfolios | Retained |
| 21.23 | Simple accept / reject / defer | Fixed — Doc 01 §12 |
| 21.24 | Audit hardening still applies | Covered by §3–§5 below |
| 21.25 | Card metadata: resolution, trigger, horizon, direction, qualification method, data domains, AI flag, class | Fixed. Execution model, cost model and latency tolerance → **Deferred** to Document 04, per validation class |

## 2. Review index 17

| # | Finding | Disposition |
| --- | --- | --- |
| 17.1 | Card doesn't pin the registry it was validated against | Fixed — `registry: {version, sha256}`; linter rejects mismatch |
| 17.2 | No proof runtime state is assigned before use | Fixed — registry runtime owners (provided / derived / stateful); "never assigned" check |
| 17.3 | `revised_formula` is prose | Fixed — now an expression; prose fails as an unresolved identifier |
| 17.4 | Peak and ATR update rule not encoded | Fixed — registry `stateful` init/update; Doc 01 §11 state machine |
| 17.5 | Negative TTL, cooldown and retry values pass; `persist(…, 2.5, …)` passes | Fixed — schema minimums; `persist` count typed as integer |
| 17.6 | Removing the loops block passes | Fixed — `evaluation` required, with registered triggers |
| 17.7 | Environment not pinned for reproducibility | Fixed — run manifest schema; package manifest |
| 17.8 | Limit-fill mechanics undefined | Deferred — Document 04 mandatory golden cases; promotion blocked until then |
| 17.9 | `impact_cost()` is a placeholder | Deferred — Document 04; linter blocks it above experimental |
| 17.10 | "No default" Unknown language is stale | Fixed — Doc 02 §8 |
| 17.11 | Overview mixes superseded material with current requirements | Fixed — every r5 document is current-state only; history lives here |
| 17.12 | "Three named universes make that possible" | Fixed — Doc 01 rewritten |
| 17.13 | Registry formulas are natural language | Accepted — golden cases (Doc 04) and feature unit tests (Doc 07) become the executable truth |

## 3. Review index 20 and the independent assurance audit

| # | Finding | Disposition |
| --- | --- | --- |
| 20.1 / F02 / F12 | Card contract not closed; many fields unchecked | Fixed — closed `card.schema.json`; linter v3; all executable fields typed |
| 20.2 | `price_raw` versioning contradicts no-duplicates | Fixed — `price_observation` keyed `(isin, trade_date, version_no)`; resolution rule; Doc 02 §6 |
| 20.3 / F05 | Snapshot alone can't reproduce a run | Fixed — `run_manifest.schema.json`; Doc 01 §13 |
| 20.4 | Date versus timestamp ambiguity; `system_available_at` not propagated | Fixed — `as_of_ts`, per-row cutoff, materialised `usable_from`; historical backfill rule; Doc 02 §3, Doc 01 §14 |
| 20.5 | Lifecycle status is a mutable string | Fixed — lifecycle transition schema with evidence; M17; publication rights enforced in M10 |
| 20.6 | M15 ledger not contracted | Fixed — Doc 02 §15 |
| 20.7 | Demergers make stocks look falsely cheap | Fixed — valuation blackouts; continuing-business earnings-yield median; Doc 02 §5 |
| 20.8 / F04 | Governance inputs lack source contracts | Fixed — Doc 02 §13; auditor split into resignation (structured) and opinion (verified extraction) |
| 20.9 | ROCE averaging, cadence, void predicates | Fixed — Doc 02 §7; registered triggers; registry `void_events` |
| 20.10 / F01 | Document 04 needed before backtesting | Deferred — next document; backtesting blocked |
| 20.11 | Tax-as-view contradicts after-tax acceptance | Fixed — Doc 03 §5 separates economic validity from deployment view |
| 20.12 | `pytest` discovers zero tests | Fixed — pytest-style entry points |
| 20.13 | Gate-number drift in prose | Fixed — Doc 03 rewritten; cards generated |
| 20.14 | Earnings-yield spread units | Fixed — decimals, stated |
| F03 | Cards duplicated in DOCX and YAML without a binding | Fixed — `render_cards.py` generation plus `--check` parity; tamper test passes |
| F06 | Portfolio risk is prose | Fixed — `portfolio_policy.schema.json` plus `portfolio_policy.yaml`, values OPEN |
| F07 | No DDL, foreign keys, idempotency or crash recovery | Partly fixed — idempotency key, allocation invariant, lifecycle transitions; DDL, migrations and crash recovery **Deferred** to Document 07 |
| F08 | Non-execution boundary not policy-as-code | Fixed in spec — Doc 01 §15; deployment manifest and CI scans **Deferred** to Document 07, gated before shadow |
| F09 | Malformed input crashes the linter | Fixed — schema-first; 1,860-card fuzz, zero crashes |
| F10 | No package manifest, lock or environment | Fixed — `MANIFEST.json`, `requirements.txt`; container image and signing **Deferred** to Document 07 |
| F11 | Tests are targeted, not assurance | Partly fixed — 83 cases plus shape fuzz; mutation-score and AST round-trip testing **Deferred** to Document 07 CI |
| F13 | Point-in-time controls not demonstrated | Deferred — Stage 0 adversarial histories; Doc 02 §17 |
| F14 | Corporate-action edge cases | Fixed in policy — fractions, stub, capital reduction, rights; fixtures for mixed consideration, overlapping actions and suspended successors **Deferred** to Document 04 |
| F15 | Benchmark, cost and tax versioning | Deferred — Document 04 effective-dated registries |
| F16 | AI controls need Document 05 | Fixed as a gate — Doc 01 §16, §17 stage 5 |
| Audit gates | Stage 0 may proceed; freeze, backtest, shadow and production each blocked by named conditions | Adopted — Overview §7 |
| Audit seams | Boundary failures to test: filing→PIT, CA→positions, feature→card, sizing→resolver, opportunity→fills, backtest→promotion, data fault→output, AI→dashboard | Deferred — each becomes a Document 04 golden case or a Document 07 integration test, as listed in §7 |
| Audit hand check | Tranche example gave 33, 26, 47 | Noted — 47 arises only if tranche 2 never fills. That path is now defined: exhaustion cancels tranche 3 |

## 4. Review index 22

| # | Finding | Disposition |
| --- | --- | --- |
| B1a | Later tranches convert at the capped limit, underbuying about 13% | Fixed — conversion at the prior session's close; limit as cap only |
| B1b | Tranche 3 absorbs an aborted tranche 2 | Rejected — exhaustion cancels tranche 3. The check did expose that **recheck failure** was undefined; now `recheck_failure: void_signal \| skip_attempt` |
| B2a | Cash-rich firms fail G2 | Fixed — equity > 0 with tiny capital employed → capped 1.00, pass; equity ≤ 0 → fail |
| B2b | Leases inflate post-2019 ROCE | Fixed — lease liabilities inside capital employed and debt/equity |
| B3 | Early backtest years sterile | Fixed — `warm_up_years`; required history = warm-up + evaluable. Their proposed loosened early-history domain → **Rejected**: it makes a feature's meaning time-dependent |
| B4 | AS-OF filter after the join | Fixed — filter inside the right relation; further, availability as one materialised `usable_from` column (found while fixing) |
| B5 | Calibration quantile undeclared | Fixed — q = 0.25 pre-registered. Their p30/p40 → **Rejected** as arbitrary; what matters is fixing it before looking |
| B6 | Demerged stub unvalued in the listing gap | Fixed — `unlisted_stub` at implied value; exit at listing open |
| H1 | Stop state machine | Fixed — Doc 01 §11; strict `>` ties rule; day-one initialisation |
| H2 | Total-return rewrite on corporate actions | Modified — bound to `adjustment_version`; the "spike on every ex-date" is overstated (ratios invariant before ex-date) |
| H3 | Relative-strength skip month ambiguous | Fixed — explicit formula |
| H4 | Integer-literal heuristic; enum collisions | Fixed — integer-literal type; namespaced enum literals; bare literal is an error |
| 22.a | Surveillance archives pre-2018 | Modified — before a framework's start date, **known none**, not `not_applicable`. After it, without coverage, `missing` |
| 22.b | Price-band archive depth | Deferred — Stage 0 verification item; `missing` handled conservatively in Document 04 |
| 22.c | Vendor point-in-time integrity | Retained — the bake-off test |
| 22.d | Percentage "completeness" scores | Rejected — not measurable |

## 5. Review indices 18 and 19

| # | Finding | Disposition |
| --- | --- | --- |
| 18 IL-01 | Persisted stop state | Fixed — registry stateful values; table DDL → Document 07 |
| 18 IL-02 | Rights entitlements lose value | Modified — valued at traded close where listed (2020+), else intrinsic; their fixed T+3 sale → replaced |
| 18 IL-03 | Round composites to 8 decimals | Rejected — rounding moves the boundary rather than removing it. Replaced by 1e-9 tie tolerance, fixed aggregation order and pinned environment |
| 18 IL-04 | `persist()` semantics | Fixed — registry function semantics; Doc 02 §8 |
| 18 IL-05 | Cost and tax table | Deferred to Document 04 with corrections: brokerage is broker-specific (some charge nothing on delivery); the long-term gains exemption and 12-month threshold were missing; a long-term *strategy* exit inside 12 months is still short-term for tax; every rate verified at drafting; tax stays a view |
| 18 IL-06 | Exit a merger target whose successor is ineligible | Adopted — revising my earlier objection. The last trading date and acquirer are public in advance, so exit at the open of the last announced trading session |
| 18 IL-07 | Zero ATR | Retained — fixed in r4.1 |
| 18 outline | Blanket ±30% sensitivity | Rejected — economically sensible ranges by strategy class |
| 18 outline | Three real-stock golden fixtures | Modified — synthetic fixtures with answers known by construction first, then real data |
| 18 flowchart | Upper-band test using `band_close_state` at the open | Rejected — look-ahead: a closing state is unknown at the open. Document 04 must test the open price against the band |
| 18 flowchart | 5% lower-circuit haircut | Deferred — Document 04 must parameterise and justify |
| 19.1 | Broker login lifecycle breaks unattended runs | Not applicable to signals: they run on exchange files needing no broker login. M15's read-only access is not time-critical; handled in Document 07 |
| 19.2 | Vendor tiers | Retained — consistent with the Doc 02 §2 bake-off; quoted prices unverified |
| 19.3 | Long silences and whipsaw tempt abandonment | Accepted — the silence brief carries funnel health; Document 04 to report expected signal frequency by regime so a silence is recognisable as normal; Document 06 to present it |
| 19.4 | Review model versus actual quarterly | Accepted — automatic in Doc 01 §12 |
| 19.5 | Stale "four timestamps" | Fixed |

## 6. Found during the r5 work (not in any review)

| # | Finding | Disposition |
| --- | --- | --- |
| R5.1 | Enum literals shared across enums would silently resolve to the first | Fixed — namespacing |
| R5.2 | The first draft of the corrected AS-OF query still tested availability at the run level, not per row | Fixed — `usable_from` per row |
| R5.3 | "Tranche 1 must recheck every gate" was too strong for single-session entries with no new data | Fixed — the rule binds where retries span new data |
| R5.4 | Momentum's time exit (X4) sat outside the cooldown in r4 | Retained fix — X4 in cooldown |

## 7. Release r5.1 — Document 04 dispositions

Every item §8 previously assigned to Document 04:

| Item | Disposition |
| --- | --- |
| Fill and circuit mechanics; open-versus-band test | Fixed — Doc 04 §3; golden G01–G06b; mutants "buy fills at an upper-band open" and "lower-band lock ignored" caught |
| Lower-circuit delay and haircut | Fixed — 1% per locked session, capped 5%, stress 0% and 2%; G05, G06b |
| `impact_cost` model | Fixed — `impact_model_v1`, Doc 04 §5; registry 2.1.0 lifts the placeholder; G07a/b |
| Dated cost and tax schedules | Fixed — `schedules/*.yaml`, each value marked verified / confirm on contract note / historical estimate; G08a–c, G09a–g |
| Rights and stub simulation | Fixed — Doc 04 §3; G12, G13a/b |
| Suspension and delisting | Fixed — marked at last close; zero at delisting without successor or consideration |
| Mixed consideration, overlapping actions, suspended successors | Deferred — real-data golden cases at Stage 0/1 (Doc 04 §2) |
| Warm-up handling | Fixed — Doc 04 §7 |
| Sensitivity by class | Fixed — Doc 04 §9, named grids per card; blanket percentages rejected |
| Promotion statistics and retirement tests | Fixed — Doc 04 §11 |
| Benchmark provenance | Fixed — published TRI only, source and retrieval date stored |
| Expected signal frequency by regime | Fixed — Doc 04 §12 |
| Synthetic-then-real golden cases | Synthetic fixed: 52 cases, 18 planted defects all caught. Real-data → Stage 0/1 |
| Execution and cost models per validation class | Fixed for `fundamental` and `technical_eod`; `event` and `intraday` reserved with stated prerequisites |
| Sealed holdout access; append-only trial log | Fixed in spec — Doc 04 §7, §8; enforcement tests → Document 07 |
| Monotonic degradation under stress | Fixed — Doc 04 §9 acceptable-shape rule |
| `policy_lag` calibration | Fixed — Doc 04 §13 |
| Tax-straddle year FY 2024-25 | Deferred — Stage 0 confirmation (Doc 04 §15) |

**Found while writing the golden cases:**

| # | Finding | Disposition |
| --- | --- | --- |
| R5.5 | Registry priced cash in lieu at the cum price, overpaying fractions by 1/f | Fixed — registry 2.1.0; guarded by G11b and a planted mutant |
| R5.6 | Removing the `impact_cost` placeholder left its regression case without a subject | Fixed — the placeholder rule is now tested against a registry copy, so it stays guarded for future placeholders |
| R5.7 | A planted mutant was first "caught" only because it crashed | Fixed — crashes now count as survivals; the mutant was corrected and is caught by G17d |
| R5.8 | Registry change forced a re-pin of both cards | Done — cards 1.0.0-prevalidation.6, registry 2.1.0 |

## 8. Release r5.2 — review indices 42 and 43

Six of index 43's claims were re-run against the package before any change: the package digest could be zeroed undetected, the lifecycle schema accepted `none → production` with no evidence, the portfolio schema accepted a 500% per-stock cap, the run manifest accepted `"not-a-date"`, N was referenced in three places and defined in none, and `penalise` had no executable meaning anywhere. All six confirmed.

| # | Finding | Disposition |
| --- | --- | --- |
| 43.1 | One scalar cutoff cannot express the 20:00 disclosure / 23:00 market-file policy | Fixed — two cutoff domains in `registry.yaml` and Doc 02 §3; both in the run manifest; golden G22a/b are exactly the 21:00-filing / 22:30-bhavcopy case; mutant "one scalar cutoff" caught |
| 43.2 | `on_filing` could evaluate against a session that has not closed | Fixed — the trigger marks the security for the next `daily_eod` evaluation (registry semantics, Doc 01 §5) |
| 43.3 | Allocator summed claim earmarks, contradicting "convergence never sizes up" | Fixed — security target is the **largest** live claim target (Doc 01 §9); golden G25a–c; mutant "security target is the sum" caught |
| 43.4 | No deterministic resolution when more claims qualify than caps allow | Fixed — existing holdings, earliest signal, larger market cap, ISIN; `min_position_pct`; breaches marked not-actionable; golden G26 |
| 43.5 | Lifecycle schema described rules a validator ignores; no validation-report hash | Fixed — real `if/then` conditionals per edge, evidence required per transition, `validation_report_sha256` added; schema-contract tests in the suite |
| 43.6 | Portfolio schema accepted absurd values; restricted list and promoter-group map undefined | Fixed — bounded percentages, integer counts, fixed `slot_priority`, `restricted_list` and `promoter_group_map` contracts, `factor_limits` extension point reserved |
| 43.7 | Run manifest looser than its prose | Fixed — RFC 3339 formats, per-feature version **and** implementation hash, content hashes for every policy, required engine settings, `holdout_access` mandatory for backtests, ledger entry required for a sealed evaluation |
| 43.8 | `make_manifest --verify` never checked the stored digest | Fixed — the digest is recomputed and compared; verified by tampering |
| 43.9 | `penalise` undefined; a missing material input silently changed a strategy | Fixed — materiality in the registry; `penalise` defined as one confidence band; the linter rejects `penalise` on a material input and any waivable gate reading one. **`ltqv_v1` G7 (audit opinion) removed from v1** and momentum's delivery gate made blocking |
| 43.10 | A permitted higher fill could breach the hard position or risk limit | Fixed — quantities bounded by the cap at the worst permitted fill; golden G24a/b; mutant caught |
| 43.11 | Universe N never defined | Fixed — `policies/market_universe.yaml`, N = 500, hashed into every run manifest |
| 43.12 | Trade-for-trade exclusion justified on momentum-specific grounds | Fixed — restated as a platform-level settlement and surveillance reason |
| 43.13 | Holdout reusable by renaming the version | Fixed — per-lineage holdout ledger; cards declare `lineage`; the linter checks code-to-lineage |
| 43.14 | Promotion metrics undefined | Fixed — Doc 04 §11 defines alpha, Sharpe, Newey–West standard error, turnover, rolling windows, drawdown; golden G29a–d |
| 43.15 | Sensitivity rule implicitly required the chosen value to be the peak | Fixed — broad stable region: same sign, no cliff, no isolated spike; G30d fixes that a pre-registered value need not be best; mutant caught |
| 43.16 | Dividends spendable on the ex-date created liquidity that did not exist | Fixed — accrual on ex-date, spendable on payment date; `expected_cash_event`; golden G27a/b |
| 43.17 | A read-only adapter is insufficient if the credential can trade | Fixed — the credential itself must be provider-scoped read-only, else no broker credential is mounted and M15 is fed by statement import |
| 43.18 | Consolidated/standalone fallback had no golden case | Fixed — fallback is per company, not per date; golden G23a/b; mutant caught |
| 43.19 | History shortfall absorbed silently | Fixed — the declared window is a requirement; shortening it is a new card version with a recorded reason |
| 43.20 | Tax reference lacked carry-forward; straddle year unresolved | Fixed — eight-year carry-forward implemented across years; straddle taxed per sale date with the FY-end exemption; golden G28a/b. Confirmation remains a Stage 0 item |
| 43.21 | Missing band data treated as benign | Fixed — 2% haircut, and uncovered periods excluded from evidence (Doc 04 §16) |
| 43.22 | No extension point for factor/correlation crowding | Fixed — `factor_limits: NONE` reserved in the policy schema |
| 43.23 | Package overstated readiness | Fixed — the overview no longer claims completeness; the gates speak for themselves |

**Index 42.** Its two substantive additions are adopted: the **Ind AS / Indian GAAP break** (facts now carry `accounting_regime`, spanning windows are flagged, and whether `ltqv_v1`'s window starts after the transition is a Stage 0 decision) and **XBRL taxonomy drift** (Stage 0 now requires the same securities to parse across 2015, 2019 and 2024 filings). Its rights-entitlement, F&O-coverage and Parquet-bootstrap points were already covered; its broker-token point is largely dissolved by 43.17. Its recommendation to freeze the documents immediately is **rejected** — six verified defects existed at the time it was written.

**Found while implementing r5.2:**

| # | Finding | Disposition |
| --- | --- | --- |
| R5.9 | The tax reference applied the FY exemption to a bucket's gross gain before the carried-forward loss was set off, overstating tax by 3× in the test case | Fixed — set-off, then exemption on the net gain, then per-regime rates; the defect is now a planted mutant |
| R5.10 | `min()` is a two-argument function; my first momentum quantity formula passed three | Caught by the linter during the edit — the compiler working as intended |
| R5.11 | The stop was never tested on the fill session itself | Fixed — sessions now start at the fill session; golden G10b covers a fill-day stop-out |

## 9. Release r5.3 — Stage 0, slice 1 (M2 price ingestion)

First product code: `eos/` (PIT primitive, warehouse, canary, M2 parsers, ingestion, resolver), `policies/source_policy.yaml`, `tests/test_m2.py` (30 cases, 8 planted read-path defects) and `tests/test_manifest.py`. Built against synthetic NSE-shaped files; no real exchange file has been parsed yet.

| # | Finding | Disposition |
| --- | --- | --- |
| S0.1 | The r5.2 package's `MANIFEST.json` said `"release": "r5.1"`. `make_manifest.py` hardcoded the string and `--verify` never checked it, so every run manifest would have recorded the wrong release | Fixed — one `RELEASE` constant; `--verify` checks it against `MANIFEST.json` and the README heading. `tests/test_manifest.py` plants the exact defect; the r5.2 script was run against it and passes it, the new one fails it |
| S0.2 | Row-count warning band evaluated in floating point: 19 rows vs 20 (exactly 95%, inside ±5%) warned, because \|0.95 − 1\| computes to 0.0500…044 | Fixed — thresholds compared in exact rational arithmetic. Found by the slice's own test; reverting the fix makes that test fail |
| S0.3 | Doc 02 §6 puts `delivery_qty` on `price_observation`, yet delivery has its own source, arrival time, correction cycle and coverage. Storing it on the price row would make a late delivery file look like a price correction | Implemented as `delivery_observation`, versioned independently and joined in `price_raw_resolved`, which also returns `delivery_state` (`known` / `missing`, reason `no_source_coverage` or `absent_in_covered_file`). **Doc 02 text still says the old thing** — batched into Doc 02 r4 at Stage 0 close (see S0.10) |
| S0.4 | Doc 02 §3 gives a `policy_lag` only for disclosures. Nothing said when a backfilled exchange file counts as available, and a value at or after 23:00 would silently drop every historical price out of its own day | Fixed — `policies/source_policy.yaml`: the **first** version of a backfilled row is inferred published 22:30 IST on its trade date, flagged `availability_inferred`; a **later** version is never inferred (available when actually received). The loader refuses an inferred time at or after the `exchange_eod` cutoff; tested |
| S0.5 | Exchange archives serve the final, corrected file. Corrections made before this system started capturing live are unrecoverable, so backfilled history treats corrected values as known on the trade date | **Limitation**, accepted: corrections are rare and small. Correction history exists only from live capture onward. Stated in the Stage 0 coverage report |
| S0.6 | Parsers are written from the documented layouts (legacy bhavcopy, UDiFF bhavcopy, MTO delivery), not verified against real files | Open — header fingerprinting fails loudly on any mismatch. Hardening on Harsh's sample files is the next task |
| S0.7 | Price-band file semantics not established: whether it gives band percentages or prices, whether the file dated D carries D's bands, and the tick-rounding rule | Open — `band_close_state` deliberately **not** built until a real file settles it; a wrong band rule would corrupt every fill in Document 04 |
| S0.8 | The Parquet codec cannot be exercised in the chat environment (no `pyarrow`, no network) | Open — `tests/test_m2.py` reports it as SKIP, never ok; `--require-parquet` makes it a failure. Must pass on the warehouse machine before Stage 0 closes |
| S0.9 | The canary needed a design that fails on an empty read, not only on a leaked row | Fixed — sentinel rows per partition, each built to be selected by one plausible wrong read (filter on `received_at`, `source_published_at`, `effective_from`, `system_available_at`; highest version regardless of cutoff; the disclosure cutoff applied to exchange data; an empty result). All 8 planted defects caught |
| S0.10 | `registry.yaml`'s header comment names "Document 02 r3" | Left unchanged: editing it changes the registry hash and forces a card re-pin and version bump (working agreement 5). Updated once, with Doc 02 r4, at Stage 0 close |

## 10. Release r5.4 — four external reviews of r5.3

Every factual claim was re-run against the r5.3 package before any change. Review 1 (independent assurance) reproduced in every case tested. Seven of review 2's nine findings describe behaviour the package already specifies or implements. Review 3 could not open the package. Review 4 is strategic.

**Review 1 — blocking findings**

| # | Finding | Disposition |
| --- | --- | --- |
| B1 | Demerger: Doc 02 said stub value "(P_cum − P_discovered) × ratio"; the reference computed something else; G12's ratio of 1 hid the contradiction | **Fixed** — ratio defined as resulting shares per parent share; total always held × (P_cum − P_discovered); fractional entitlement is cash in lieu (Doc 02 r4 §5, `reference_sim.demerger`). Goldens G12b–d (½, 3, fractional); mutants "r5.3 prose" and "fraction dropped" caught |
| B2 | One file's ingestion was four independent appends; a crash between them left prices without coverage, and the retry crashed | **Fixed** — batch transactions (stage → commit record → apply; readers refuse while a committed batch is unapplied; the next writer rolls it forward). `tests/test_m2.py` crashes at all four boundaries and during recovery; each ends in the uninterrupted state |
| B3 | The lock covered each append, not read-latest → allocate-version → commit; two writers produced two "version 2" rows and the resolver silently picked one | **Fixed** — one writer lock spans the whole ingestion; duplicate `(isin, trade_date, version_no)` is an `IntegrityError` at read. Real two-thread race test. **Found while fixing:** re-entrancy was per object rather than per thread, so a second thread sharing the object skipped the lock. The race test caught it; now per thread, and mutation-checked |
| B4 | Holdout ledger and trial log are specified, not enforced | **Deferred, gate moved earlier** — before the first calibration or backtest run (Doc 01 §17), not "before shadow". Exposure cannot be un-seen, so a log built later cannot record trials that ran before it |
| B5 | Doc 04 §11 claimed `reference_sim` implements drawdown and the selection effect; it does not | **Doc corrected now** (Doc 04 r3 §11 states what exists). Implementation and goldens are due before the first calibration run |
| B6 | Brinson–Fachler undefined for cash | **Deferred** — same gate as B5; recorded in Doc 04 r3 §11 |
| B7 | Lifecycle status inside the card: a status-only change alters the card's hash | **Accepted; deferred** to the Stage 0 registry and card-schema re-pin, and in any case before M17 |
| B8 | One read function served two meanings: the view of one decision, and a panel for a sequence | **Fixed** — `history_known_as_of(E)` and `point_in_time_panel(start, end)` (Doc 02 r4 §6, Doc 01 r7 §14). The test puts a correction after its trade date and checks both |
| B9 | One inferred availability time for all exchange sources | **Fixed** — per-source rules with `inferred_basis` (`source_policy.yaml` 1.1.0); the loader validates each; `availability_profile()` reports the inferred share; Doc 04 r3 requires lag-sensitivity reruns. **Severity qualified:** orders execute at the next open, so a later-than-inferred publication biases results only if it came after that open |
| B10 | A complete reissue cannot delete an erroneous row | **Deferred to S1b** — needs the real reissue semantics; tombstones if reissues are complete snapshots |
| B11 | The run-manifest schema cannot prove a complete feature closure | **Deferred** — a semantic validator is due before the first calibration run |
| B12 | Identity of a multi-date backtest undefined | **Deferred** — parent/child simulation identity, same gate |

**Review 1 — high priority**

| # | Finding | Disposition |
| --- | --- | --- |
| H1 | Special-dividend threshold 5%; the SEBI derivatives rule has been ≥ 2% since June 2022 | **Confirmed; deferred to S2.** Narrower impact than stated: momentum returns read the total-return series; only adjusted-series features (DMA gates, volatility, ATR) are affected. Also define equality at the threshold |
| H2 | `production → retired` accepted empty evidence | **Fixed** — schema conditional; regression checks in `test_speclint.py`, which fail against the r5.3 schema |
| H3, H4 | Actual-portfolio state and promoter-group map not bound into lineage | **Deferred** — before shadow (Doc 01 §17) |
| H5, H6 | Retirement metrics and the shadow "two standard errors" test not executable | **Deferred** — before production |
| H7 | Tax loss carry-forward never lapsed | **Fixed** — vintage carry with eight-year lapse; goldens G28c/d; mutant caught. **Found while fixing:** an unabsorbed short-term loss was carried as long-term, so it could not offset a later short-term gain. Fixed; golden G28e; mutant caught |
| H8 | Naive timestamps silently read as IST; linter accepted `2026-99-99` | **Fixed** — `parse_ts` refuses a missing offset; golden fixtures converted explicitly with `ist()`; linter formats check the calendar. Tests for both; the linter check fails against the r5.3 linter |
| H9 | `*_cutoff_ts` typed `date` in the registry | **Accepted; deferred** to the single Stage 0 re-pin |
| H10 | Doc 02 still put `delivery_qty` on `price_observation` | **Fixed** — Doc 02 r4 §6 (S0.3). The batching default applied to registry re-pins; a governing document known to be wrong is corrected now |
| §6 | Release drift across documents | **Fixed** — Overview v5.4, Doc 01 r7, Doc 04 r3 references; counts removed from prose; `tests/test_release.py` checks every revision reference, titles, README listing and release labels. It found one stale reference the review missed (the Stage 0 Plan citing Doc 02 r4 before it existed) |

**Found while building r5.4**

| # | Finding | Disposition |
| --- | --- | --- |
| R5.12 | The first r5.4 build hash-bound 17 files of a stray `docs/.git` (an exploratory `git init`). `make_manifest.py` binds whatever is on disk | **Fixed** — hidden files and directories are refused by build and by `--verify`. `tests/test_manifest.py` plants one; the r5.3 script binds it silently, the new one refuses |

**Review 2** — checked claim by claim:

- **Rejected as not matching the package:**
  - Execution at T close: Doc 04 executes at the next executable session's open.
  - The UDiFF parser keying on the wrong date: it keys on `TradDt`, the trade date.
  - An EQ-only series filter: the parser applies none.
  - Banks scored on industrial ratios: `ltqv_v1` excludes banks, NBFCs, insurers and capital-markets firms.
  - A static symbol join for delivery: mapping is through the same day's bhavcopy, which carries the ISIN.
  - Demerger stub unspecified: Doc 02 §5 specifies it.
  - TTM and half-yearly balance-sheet rules undefined: Doc 02 §7 defines both.
  - DP charges missing: `dp_charge_per_sell_scrip_day` is in the cost schedule.
  - Circuit locks ignored: Doc 04 already handles fills at the bands; the band data itself was already logged as S0.7.
- **Adopted:**
  - Zero-price or zero-volume rows in real bhavcopies: M2's OHLC check would reject a whole file containing them. S1b.
  - Daily manual downloads will not last: a scheduled downloader on the warehouse machine, before shadow. It also starts live capture of corrections (S0.5).

**Review 3.** It could not open the package. Its symbol-mapping point is handled as above, and its XBRL-depth expectation matches the open S3 question. **Adopted:** whether a muhurat bar counts in rolling windows is unspecified. That goes to S2, as a Doc 02 and registry rule rather than in the universe policy as the review suggested.

**Review 4.**

- **Adopted:** the data-maintenance burden and automation, which are the same as review 2's second point.
- **Retained, already allowed:** truncate `ltqv_v1`'s window or buy vendor data (Doc 02 §14, as a new card version).
- **Rejected:** "weekly opportunity cards before full backtesting". That would mean acting on unvalidated strategies, contrary to the recorded shadow-before-recommend rule.
- **Open for Harsh:** taking `mom_v1` end-to-end through validation before the XBRL-heavy `ltqv_v1` work.

## 11. Carried forward — owners and gates

The phase at which each open control becomes mandatory is in **Document 01 §17**. That replaces the single "Document 07 before shadow" gate.

| Owner | Items | Gate |
| --- | --- | --- |
| **Stage 0 / real-data golden cases** | Mixed consideration, overlapping actions, suspended successors; FY 2024-25 straddle confirmation; contract-note reconciliation (including STT rounding); Doc 04 §17 items; real ISIN changes in `security_lineage`; share-count history depth | Before any backtest counts as evidence |
| **Document 05** | AI evidence schema, prompt-injection handling, model provenance, verification and confirmation workflow; counter-evidence coverage conditions | Before M12 |
| **Document 06** | Brief and silence presentation; how coverage is shown | Before the dashboard |
| **Document 07** | DDL and migrations; deployment manifest; network policy; order-endpoint scans; container image and dependency lock; release signing; licence and source-provenance policy (including automated NSE download); mutation check in CI; kill-switch atomicity; restore, replay and idempotency integration tests | Phased, per Document 01 §17 |
| **Stage 0** | Every Doc 02 §17 verification item; S0.6–S0.8; B10 reissue semantics; no-trade row storage; the quarantine limit calibrated on real files; H1 special dividends; Doc 02 r6 carrying whatever the real files teach | Before Stage 0 closes |
| **Before live capture** | `live_capture_start` set in the source policy | When the scheduled downloader starts |
| **Before the first calibration or backtest run** | B4 trial log and holdout enforcement; B6 Brinson–Fachler with cash; B11 semantic run-manifest validator; B12 simulation identity; each card's measurement parameters pre-registered; snapshot persistence | Document 01 §17 |
| **Before shadow / production** | H3–H6, the scheduled downloader, actual-versus-model divergence golden cases, Document 07 operations | Document 01 §17 |

## 12. Release r5.5 — the independent audit of r5.4

Each finding was reproduced against r5.4 before any change (`audit/repro/` in the working repository), and each fix has a test that fails against r5.4. The registry and card-schema re-pin planned for Stage 0 close (H9, B7, S0.10) is done here, in one step, because A2–A4 changed what a pin is.

**Class A — structural**

| # | Finding | Disposition |
| --- | --- | --- |
| A1 | No part of the package executed a card: a card with a 5% ROCE gate and a 4× ATR stop passed every check | **Fixed** — `reference_engine.py` evaluates each card's own expressions; `golden/card_cases.yaml` (hand-computed) and `test_card_golden.py` with planted card edits, including exactly that one, each caught; freeze criterion now requires card-level goldens (Doc 01 §8) |
| A2 | Evaluation semantics undefined: three-valued AND/OR/NOT, `out_of_domain: fail` in exits and `persist`, stale/conflicted/not_applicable in gates, filters on unknown, `substitute`, weekly exit weekday and holidays, review triggers in model portfolios | **Fixed** — normative, versioned `evaluation_semantics` in the registry (inside every closure); Doc 01 §7; Kleene exits; an out-of-domain-fail input fires the exit unless `on_out_of_domain: review` (the `ltqv_v1` collapse case now sells); `substitute` removed; weekly rule; goldens C07–C19 |
| A3 | Model-portfolio capacity undefined; the rank had no consumer; personal `OPEN` sizing values changed which momentum signals existed; actual recommendations sized on notional capital | **Fixed** — card `construction` (max positions, capacity by rank, residual cash); sizing redefined as pre-registered hypothesis parameters; the allocator converts a claim to a weight of your capital and re-runs size checks at your size; goldens C24–C26; Doc 01 §4, §9; Doc 04 §3 |
| A4 | Cards pinned the whole registry file, so any edit re-versioned every card (and would burn holdouts); lineage was self-declared | **Fixed** — cards pin their registry closure; every entry versioned; registration declares derived and seen lineages, and the ledger inherits their exposure (Doc 04 §7); closure-scope test |

**Class B — high priority**

| # | Finding | Disposition |
| --- | --- | --- |
| B1 | Identity across ISIN changes undefined | **Fixed in specification** — `security_identity` in the registry; Doc 02 §4; CA policy v3; goldens G33a–b. Populated from real ISIN changes at S2 |
| B2 | Linter bypasses: `substitute`, a composite in a waivable gate, the hard cap as a substring, look-ahead through `next_executable_session` | **Fixed** — all four rejected (regression cases); the cap is checked structurally *and* enforced by the engine; price functions accept only evaluation dates |
| B3 | The panel dropped late first publications; backfill mode back-dated a same-day file | **Fixed** — the panel keeps the first version with its real `usable_from`, and `panel_as_of` masks it per decision; `backfill.min_age_days` and `live_capture_start` in source policy 1.2.0; tests |
| B4 | The Parquet codec accepted naive timestamps; only one test used Parquet | **Fixed** — one pre-write validator for every codec (also refuses unknown columns, floats for decimals, bools for ints); every M2 case runs on every available codec; `pyarrow` pinned |
| B5 | Fundamentals assembly underspecified; the basis fallback was timeless | **Fixed in specification and reference** — `period_panel_as_of` and `basis_for_window` (reference and `eos/pit.py`); Doc 02 §7; goldens G23a–d, G31a–c |
| B6 | ROCE: loss-making cash shells scored 1.00; near-zero average CE gave 600%; negative prior CE gave −120% | **Fixed** — `roce_rule`: cap tested on average CE, only for EBIT > 0; universal 1.00 cap; goldens G17a–o |
| B7 | Promotion rule sign-only (about 20% of zero-alpha strategies passed); trial count unused; Doc 03 and Doc 04 disagreed; `ltqv_v1` retired on a benchmark never tested at promotion | **Fixed** — Newey–West t hurdle scaled by logged trials; holdout consistency; minimum detectable alpha reported; Quality 30 test for `ltqv_v1`; Doc 03 §5 defers to Doc 04 §12; goldens G32a–f |
| B8 | 34 of 36 card-read features had no executable definition; delivery %, window conventions, "transformative action" and calibration sampling ambiguous | **Fixed** — `reference_features.py` and `golden/feature_cases.yaml` for every card-read feature and flag, with an automated coverage check; `window_conventions`; ratio-of-sums delivery; valuation-transformative actions exclude rights issues; calibration `sampling: pooled_entry_sessions` |

**Class C — medium**

| # | Finding | Disposition |
| --- | --- | --- |
| C1 | Test adequacy: 67% mutation score; the PIT equality boundary and several branches unpinned; one planted mutant hard-coded its answer | **Fixed** — boundary and branch goldens; the hard-coded mutant replaced by a logic mutant; `mutation_check.py` with every survivor reviewed as equivalent in `golden/mutation_allowlist.yaml` (score 87% on a larger surface) |
| C2 | Gate outcomes depended on float summation order | **Fixed** — gate, exit, filter and forensic-flag inputs quantised to 9 dp and compared in Decimal; goldens C10, F76 |
| C3 | Momentum risk budget exceeded when ATR rose between signal and fill; stop unknown before the order | **Fixed** — `atr_pct_at_signal` drives sizing and the initial stop |
| C4 | Rights intrinsic value: prose said P_ex, the reference used TERP | **Fixed** — TERP, with whole entitlements; golden G13c |
| C5 | One bad row rejected the whole day | **Fixed** — `row_quarantine`, with a limit; `quarantined` delivery reason; tests |
| C6 | Ingestion re-read the whole log for every file (quadratic backfill) | **Fixed** — only the trade date's partition is read; per-day cost now flat |
| C7 | "None found" counter-evidence had no coverage definition | **Fixed in specification** — Doc 01 §12: coverage always shown; "none found" only under a stated coverage condition (Documents 05/06) |
| C8 | Actual-versus-model claim divergence unspecified | **Fixed in specification** — Doc 01 §9 rules; golden cases are a Stage 3 gate |
| C9 | A void predicate named a card's gate by number | **Fixed** — `void_parameters`, checked by the linter |

**Class D — hygiene**

| # | Finding | Disposition |
| --- | --- | --- |
| D1 | Drift the release test could not see (Doc 03's release line, prose counts, section references, the silence example) | **Fixed** — `tests/test_release.py` now checks every document's release line and every `Document 0N §M` / `Doc 0N sM` reference against real headings, including the registry's; counts removed from prose |
| D2 | Environment pins unchecked | **Fixed** — `pyarrow` pinned; the execution contract states the environment |
| D3 | STCG 15% marked verified from 2004; service-tax history; STT rounding | **Fixed** — 10% to March 2008; dated service-tax rates; STT rounding noted for the contract-note reconciliation |
| D4 | `eval()` on fixture strings | **Fixed** — explicit fixture data |

**Found while building r5.5**

| # | Finding | Disposition |
| --- | --- | --- |
| R5.13 | Cross-sectional scoring lived only in Doc 02 prose, outside any card's pin | **Fixed** — registry `cross_sectional_scoring`, inside every closure |
| R5.14 | A forensic flag at exactly its threshold fired because (0.1 + 0.1 + 0.1) / 3 > 0.10 in floating point | **Fixed** — the C2 quantisation applies inside features; golden F76 |
| R5.15 | YAML reads a key named `on` as boolean true | **Fixed** in the feature fixtures (`on_date`); noted for every future YAML schema |
| R5.16 | Several first-draft feature and card fixtures could not tell a mutant from the original (identical horizons in the ranking case; a cash-conversion coincidence between three and four years) | **Fixed** — found by the planted edits and the mutation check; fixtures changed so each mutant is distinguishable |
| R5.17 | A no-promoter company had no defined pledge and would have failed `ltqv_v1` G5 | **Fixed** — pledge 0.0 with a `no_promoter` flag; golden F24 |
| R5.18 | Under pytest, `tests/test_m2.py`'s `test` decorator was collected as a test and errored, and no M2 case ever ran (since r5.3) | **Fixed** — decorator renamed `case`; a `test_m2_suite` entry point runs every case on every available codec |
