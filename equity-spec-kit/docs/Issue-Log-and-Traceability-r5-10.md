# Issue Log & Traceability — Releases r5 / r5.1 / r5.2 / r5.3 / r5.4 / r5.5 / r5.6 / r5.7 / r5.8 / r5.9 / r5.10

*25 September 2026 · every finding from review indices 17–22 and 42–43, the independent assurance audit (F01–F16), Stage 0 (S0.x), the four external reviews of r5.3 (§10), the independent audit of r5.4 (§12), the review of r5.5 run on Windows (§13), the r5.7–r5.9 corrections (§14–§16) and the reviews of r5.7–r5.9 with the open-findings register (§17), with its disposition*

**Dispositions:** **Fixed** (where) · **Modified** (adopted with a change; reason given) · **Deferred** (named owner and gate) · **Rejected** (reason) · **Retained** (already correct; kept deliberately).

**Verification.** Every "Fixed" item needs a test that would have caught it:

- **Items the linter can express** get a regression case in `test_speclint.py`.
- **Items it cannot express** get a golden case, with a planted mutant: `test_golden.py` for simulation and policy, `test_features.py` for feature definitions, `test_card_golden.py` for what a card means, `test_pipeline.py` for what a whole evaluation produces.
- **Product-code items** get a test in `tests/`.
- **Portability items** get a check in `tests/test_portability.py` that fails on any OS.
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

## 13. Release r5.6 — the review of r5.5, run on Windows

The review ran r5.5 on Windows, the warehouse machine's OS. Eleven of twelve pytest entry points passed there. It found three Windows defects the Linux suite could not see, and a list of P0–P2 items. Every item was verified against r5.5 before any change. Each fix has a test that fails on r5.5, and, for the portability class, a check that fails on Linux too.

**What is certified, and where.** Every contract command passes on Linux under CPython 3.11.15 and 3.12.3, with the pinned dependencies (README, Certification). The Windows code paths run on Linux against an emulation of `kernel32` and `msvcrt`. That emulation catches a Windows-only call on the wrong path, as r5.5's directory fsync would have been caught. It is **not** evidence that the paths work on Windows. The gate before any warehouse data is trusted is `py -3.12 run_all.py --require-parquet` on the Windows machine itself (Doc 01 §17).

**P0 — Windows and the execution contract**

| # | Finding | Disposition |
| --- | --- | --- |
| W1 | `eos/store.py` fsync-ed the directory after every rename. Windows cannot open a directory, so no warehouse write could succeed there | **Fixed** — `eos/fsio.py` gives each platform its own durable replace. POSIX: `rename`, then fsync the directory. Windows: `MoveFileExW(REPLACE_EXISTING \| WRITE_THROUGH)` through `ctypes`, retrying a sharing violation with bounded backoff, and never opening a directory. Every M2 case runs on both platform paths, with the Windows pass refusing any directory open as Windows does; a write-through case and a sharing-violation case are included |
| W2 | `mutation_check.py` bounded each mutant with `SIGALRM`, which Windows lacks | **Fixed** — mutants run in worker processes that report one line each; the parent enforces the per-mutant limit by watching for that line, kills a silent worker, counts the hung mutant as detected and resumes after it. No signals; the same survivors as r5.5 (79 of 588, all allowlisted) |
| W3 | `tests/test_release.py`, and about 50 other `open()` calls, read text in the platform's default encoding (cp1252 on Windows) | **Fixed** — every text-mode `open()` and every text-mode subprocess names UTF-8, and every command writes UTF-8 to stdout. `tests/test_portability.py` checks this three ways. An AST scan fails on any unnamed encoding. Every suite runs under `-X warn_default_encoding -W error::EncodingWarning` with stdout forced to cp1252. Every package text file must be LF-only UTF-8 |
| W4 | `pytest` was not pinned, and was absent on the review machine | **Fixed** — `requirements-dev.txt` pins PyYAML 6.0.3, pyarrow 25.0.1 and pytest 9.1.1; `run_all.py` runs every contract command with the current interpreter on any OS |
| W5 | The README claimed portability it had not tested | **Fixed** — the README's Certification section states exactly what ran where, and names the Windows run as outstanding. The repository's `.gitattributes` (`* -text`) prevents line-ending conversion, and `make_manifest.py --verify` names a CRLF conversion when it finds one |

**P1 — semantics, evidence and the warehouse**

| # | Finding | Disposition |
| --- | --- | --- |
| R1 | Muhurat semantics: the registry said its bars were "not used", Doc 02 said it was not executable, and neither said it is a real trading session | **Fixed** — registry `session_policy` 1.0.0, a stated platform choice. Muhurat trades and is stored; only `normal` sessions are executable, so muhurat is never a unit, never evaluated and never filled in. Its move falls in the next executable return. `weekly_sessions` reads `session_type`; goldens C27–C27d; Doc 01 §7, Doc 02 §3 |
| R2 | An unrankable security reached the model portfolio: `construct` admitted missing ranks after the ranked ones whenever capacity was spare. Material inputs that feed only the ranking could never block | **Fixed** — evaluation semantics 1.1.0. An unrankable security is not a candidate, and `construct` refuses one. Ranking inputs resolve by their unknown behaviour, so a missing material input means no rank. The compiler requires `min_inputs_known` to cover every material composite input; `ltqv_v1`'s quality composite now needs all five. Goldens C25c, C29–C29g, C30, P3 |
| R3 | Confidence counted a conflicted penalised input twice and ignored a conflicted material ranking input, although the policy names "conflicted input used for ranking" | **Fixed** — one band per feature: a penalised input not known, or a conflicted input used in ranking. Conflicted inputs rank with their primary value. Confidence changes neither candidacy nor the model portfolio. Goldens C20c–f, P1, P4 |
| R4 | No golden case ran a population through to the published claims | **Fixed** — `reference_engine.run_pipeline` (universe → filters → ranking → gates → size checks → capacity → quantities → publication) with `golden/pipeline_cases.yaml`, P1–P4 worked by hand, and seven planted defects, including every r5.5 behaviour above, each caught. The publication rule is now normative: what is recommended is what the model portfolio measured (Doc 01 §7) |
| R5 | Card closures were too broad. Adding a weekday re-pinned both cards, and editing `valuation_transformative_actions` re-pinned `mom_v1`, which never reads it | **Fixed** — a closure holds the enums its expressions and enum-typed features use, the blocks its features declare in `depends_on`, and scoring only for ranking cards. Tests: a new weekday, horizon or status leaves both pins. The transformative-actions edit re-pins `ltqv_v1` only. A new surveillance stage or session policy re-pins both. A scoring edit spares a gate-only card |
| R6 | Lifecycle records were ordered by the `decided_at` string. The two r5.5 records carried a hand-typed time that was in the future when they were committed, and a "for Harsh to confirm" author that was never confirmed | **Fixed in r5.6 for string ordering / bad timestamps; chronology assurance completed in r5.7 (C57-7)** — `register_card.py` stamps the real time and refuses a bad `--at`. r5.7 makes ledger/file order authoritative and requires strictly increasing aware instants, so a backdated later transition cannot pass. The two r5.5 records remain withdrawn; both current cards are registered as `1.0.0-prevalidation.9`. |
| R7 | A crash left the O_EXCL writer lock behind, blocking every later ingestion until someone deleted it by hand | **Fixed** — an OS lock (`flock` / `msvcrt.locking`) that the OS releases when the holder dies; the lock file is never deleted. Test: a child process holding the writer is killed, and the parent then ingests |
| R8 | There was no immutable raw landing layer: ingestion parsed the download folder in place | **Fixed** — every file is landed write-once and content-addressed under `_raw/` before parsing. Parsing reads the landed copy, and a `raw_file` row commits with the observations (Doc 02 §12). Tests: bytes preserved exactly; a later change to the original affects nothing; re-landing is a no-op; a tampered landed file is refused |
| R9 | Exact per-decision reads and the first-known panel were presented as equally valid, and the panel was called "conservative" | **Fixed** — the run manifest's `price_read_contract` is required for backtests and replays. The sealed holdout must use `exact_per_decision` (schema-enforced). The panel is described as information-poorer, not conservative, and panel results are never promotion evidence (Doc 02 §6, Doc 04 §7) |

**P2**

| # | Finding | Disposition |
| --- | --- | --- |
| Q1 | A constant design series divided the Newey–West t-statistic by zero | **Fixed** — `nw_tstat` returns None below a 1e-12 standard error; the decision reports `degenerate: true` and fails; goldens G32g–i |
| Q2 | `START-HERE.md` said it "wins" over everything else | **Fixed** — it is the status and handover note. On what the system is and does, the manifest-bound package controls (Doc 01 §2) |
| Q3 | The audit's reproduction scripts were not bound to any release and used `SIGALRM` | **Fixed** — `audit/README.md` labels them as non-controlling history, written for r5.4 and Unix-only. The package's own checks (`run_all.py`) are what verify a release |

**Found while fixing (not in the review)**

| # | Finding | Disposition |
| --- | --- | --- |
| F1 | `mutation_check.py` mutates `reference_sim.py` and `reference_features.py` only. A trial on `reference_engine.py`, including the `Engine` methods (87 sites), against the card and pipeline goldens left 22 survivors. Some are likely equivalent (defensive guards, rounding of a reported value); others are boundary cases no golden pins yet | **Deferred** — owner Claude; gate: before the first calibration or backtest run (Doc 01 §17), when the mutation check must be green. Add `reference_engine` to the check with class methods included, add goldens for the real gaps and allowlist the reviewed equivalents |
| F2 | A composite's `min_inputs_known` could be set below its number of material inputs, which let a card rank on a different formula when material data was missing (this is how R2 reached `ltqv_v1`) | **Fixed** — a compiler rule (Doc 01 §8); `ltqv_v1`'s quality composite set to 5 of 5 |


## 14. Release r5.7 — post-audit correction release over r5.6

The 24 September 2026 post-audit correction list was reconciled against the r5.6 package before implementation. r5.6 remains the immutable baseline; r5.7 contains only the corrections and their assurance changes. No existing validation or release gate was removed or weakened.

| # | Finding | Disposition |
| --- | --- | --- |
| C57-1 | A clean native-Windows Parquet run needed an undeclared timezone database | **Fixed** — `tzdata==2026.4` is a runtime dependency in `requirements.txt`, because the PyArrow/warehouse timezone path needs it outside development. The r5.6 native Windows run passed after manual installation. **External acceptance later completed:** on 25 September 2026 a clean r5.7 Windows 11 / Python 3.12.10 venv installing only declared dependencies ended `ALL PASSED`; no manual tzdata install was required. |
| C57-2 | A linter-valid `gate_only` card reached construction without ranks and crashed | **Fixed** — `construct()` dispatches on the card's `construction.capacity_order`; `earliest_signal` uses aware `signal_at` instants with deterministic ISIN ties and never invents a rank. Pipeline golden P5 and a planted forced-rank defect cover it. |
| C57-3 | Runtime `max_positions` could silently override a numeric card value | **Fixed** — `run_pipeline()` resolves capacity from the card; a supplied value must match a numeric declaration exactly, while `OPEN` still requires the pre-registered runtime value. Pipeline golden P6 and a planted override defect cover it. |
| C57-4 | Parser-rejected raw bytes could be landed without a durable `raw_file` receipt | **Fixed** — raw landing/receipt is transaction 1 and parsing/observations is transaction 2. Parser rejection leaves bytes, receipt and a rejected `raw_parse_event`, but no observations. The M2 malformed-format regression proves the receipt SHA matches the landed bytes. |
| C57-5 | Lifecycle evidence hashes were stored but not recomputed when resolving status | **Fixed** — every hash-bearing evidence item has a relative path; the linter requires the file, prevents path escape, recomputes SHA-256 and rejects changed, deleted, moved or wrongly hashed evidence. Regression cases cover all five outcomes. |
| C57-6 | Unexpected mutation-worker termination could be credited as a detected mutant | **Fixed** — the harness distinguishes `killed`, `survived`, `timeout`, `equivalent` and `infrastructure_error`. Unexpected exit/malformed worker output fails the campaign and never improves the detected score. `tests/test_mutation.py` kills a worker with exit code 7 and requires `infrastructure_error`. |
| C57-7 | Lifecycle status continuity did not require transition timestamps to move forward in ledger order | **Fixed** — file/ledger order is authoritative and each aware `decided_at` instant must be strictly greater than the previous one. Equal instants across different offsets, backdating, missing offsets and future times fail; existing status-chain checks remain. |
| C57-8 | Regular mutation coverage omitted `reference_engine.py` | **Fixed** — top-level engine functions and `Engine` methods are in the normal campaign. The r5.7 build campaign covered 673 sites overall with 0 unlisted survivors and 0 infrastructure errors; no engine survivor required a new equivalence allowlist entry. |
| C57-9 | Null source URL/retrieval timestamps could not be distinguished from missing provenance | **Fixed** — `raw_file.acquisition_method` is explicit. Manual upload permits absent URL/retrieval time; scheduled/API requires both; vendor/archive import requires retrieval time; all supplied timestamps are aware and retrieval cannot follow receipt. Valid and invalid M2 fixtures cover the rules. |
| C57-10 | Forced changes to a read-only landed blob were invisible to ordinary receipt reads | **Fixed** — `Warehouse.verify_raw_integrity()` re-hashes and re-sizes every receipted blob, checks that its path remains under `_raw`, and fails on missing/moved/changed evidence. `snapshot()` invokes it, and the M2 tamper regression proves both the direct verifier and evidence snapshot fail. |

**Native Windows evidence.** The r5.6 baseline was run successfully on Windows 11 / Python 3.12.10 / PyYAML 6.0.3 / PyArrow 25.0.1 / pytest 9.1.1 with Parquet required; the final result was `ALL PASSED`. That run required a manual `tzdata` installation and therefore did not prove clean-install reproducibility. r5.7 fixes the dependency declaration. The build environment could not substitute for the native-Windows rerun; that rerun was subsequently completed on 25 September 2026 and ended `ALL PASSED`.

**Calibration/backtest gate.** r5.7 closes the engine-semantic, lifecycle and mutation-assurance blockers identified by the audit. Calibration/backtesting must still wait for the release suite to be green and for the documented clean-install platform acceptance. Stage 0 real-exchange work may then continue under the existing roadmap.

## 15. Release r5.8 — first real-NSE-data correction release

r5.8 starts from the certified r5.7 package and addresses only semantics exposed by genuine NSE UDiFF and MII Security File data. r5.7 remains unchanged. The 24 September 2026 UDiFF final bhavcopy contained 3,637 rows; r5.7 landed/hashed/stored it correctly but quarantined four legitimate EQ+BL observations solely because two ISINs appeared in more than one source series. The companion MII master also demonstrated that `EQ` alone does not identify company equity, contains exchange test rows, and that a same-report-date master can already contain a later-session symbol or eligibility state. These are treated as systemic data-contract findings; isolated unexplained anomalies continue to fail closed without blocking the roadmap.

| # | Finding | Disposition / assurance |
| --- | --- | --- |
| C58-1 | UDiFF `FinInstrmId` was required to recognise the format but discarded from stored price rows | **Fixed** — `price_observation.source_instrument_id` preserves `FinInstrmId`; legacy rows remain nullable. It is a source join key, not a replacement for permanent `security_id`/ISIN lineage. Regression: legacy/UDiFF parser case and source-identity cases. |
| C58-2 | One-ISIN-per-day validation quarantined legitimate EQ+BL observations (SANOFI and SEDEMAC in the real sample) | **Fixed** — UDiFF uniqueness is source-instrument/day; legacy fallback is ISIN+series/day. Same ISIN in different legitimate source instruments is retained. A true duplicate source observation still fails/quarantines. Regressions include the EQ+BL case and a 3,637-row real-derived shape with zero duplicate-ISIN quarantine. |
| C58-3 | Raw/source exchange observations and the strategy-facing daily price were conflated | **Fixed** — source observations are resolved losslessly; canonicalisation is a separate explicit series policy. `BL`, `IQ` and `RL` remain source evidence and cannot replace the regular-market bar. Equal-priority ambiguity fails. |
| C58-4 | There was no current NSE MII Security File parser/warehouse path | **Fixed** — gzip CSV parsing with exact header fingerprint, unique source token, durable raw receipt/provenance/integrity, versioned `security_master_observation`, dummy/test detection and source coverage. Schema drift fails loudly. |
| C58-5 | The MII file/report date could be mistaken for the session its metadata governs, creating look-ahead | **Fixed fail-closed** — `master_file_date`, availability, nullable `effective_session` and `effective_session_basis` are separate. The filename never proves the effective session. A newer available but unresolved master state blocks eligibility/no-trade inference; a known future-effective state applies only from its effective session. Golden uses the SANGINITA→AGASTYAEN pattern. **Residual:** a universal NSE effective-session convention is not claimed until broader real evidence establishes one. |
| C58-6 | Symbol/series matching could break on legitimate metadata transitions | **Fixed** — contemporary reconciliation keys primarily on `source_instrument_id`; ISIN/symbol/series are cross-check/history fields. Historical bhavcopy state is never overwritten by later master metadata. Unexplained identity conflict fails closed. |
| C58-7 | `FinInstrmTp=STK`, `series=EQ`, ticker-name and ISIN-prefix shortcuts can all misclassify the universe | **Fixed for the initial continuous main-board class** — classification uses exchange series + instrument type + dummy/deletion/eligibility state where effective state is resolved. Goldens cover a company equity (20MICRONS shape), EQ ETF/fund (GOLD360 shape), DVR (`IN9`-style JISLDVREQS), a name containing GOLD that is still a company, and `*NSETEST`. Broad BE/BZ admission remains a Stage 0 policy item rather than a guess. |
| C58-8 | No-trade semantics were undefined; absence, quarantine and source absence could be conflated | **Fixed** — resolver returns explicit `traded`, `no_trade`, `quarantined`, `source_not_available` and `master_state_unresolved`. `no_trade` requires complete final bhavcopy coverage plus an effective eligible master state plus source absence. No zero OHLC or forward-filled fake trade is created. |
| C58-9 | A later complete reissue that removes a former row could only log a conflict and retain the row forever | **Fixed** — `observation_tombstone` is an immutable point-in-time withdrawal event. Before the correction the former row resolves; after the tombstone's `usable_from` it does not. Quarantined rows do not masquerade as omissions. |
| C58-10 | Current security-master status values could be guessed when semantics were unknown | **Fixed fail-closed** — the parser recognises the documented current status set used by the source contract and records whether a status code is known. Unknown status/eligibility semantics produce `market_eligible = null` and `master_state_unresolved`, never eligibility by guess. Regression uses an unknown status code. |
| C58-11 | The real 24-Sep source shape was not represented in automated assurance | **Fixed as a deterministic real-derived golden** — a 3,637-row UDiFF fixture with two same-ISIN EQ+BL pairs proves all 3,637 legitimate source observations survive while the canonical view is derived separately. This does not claim that the build container re-downloaded the user's NSE file; actual native-Windows real-file re-ingest remains release acceptance. |

**r5.7 certification evidence.** After r5.7 was built, a clean Windows 11 / Python 3.12.10 virtual environment outside the manifest-bound package installed only `requirements.txt` and `requirements-dev.txt`; PyYAML 6.0.3, PyArrow 25.0.1, pytest 9.1.1 and `tzdata 2026.4` installed successfully, `pip check` reported no broken requirements, and `run_all.py --require-parquet` ended `ALL PASSED`. That closes C57-1's external acceptance. r5.8 must repeat the same native-Windows/Parquet gate because its warehouse schema and M2 semantics changed.

**r5.8 build assurance.** `tests/test_m2.py` has 61 cases; the build environment ran 122/122 on JSONL across POSIX and Windows-sim paths. Existing linter, simulation, feature, card and pipeline suites remain green. The regular mutation campaign remains 673 sites: 592 killed, 2 mutant timeouts, 79 reviewed equivalent survivors, 0 unexplained survivors, 0 infrastructure errors. Parquet is unavailable in the build environment, so native-Windows `--require-parquet` is not inferred.

**Roadmap gate.** r5.8 deliberately does not solve the entire historical-data roadmap. After its native-Windows/real-file acceptance, Stage 0 continues with a modest multi-date UDiFF/MII sample, real MTO delivery, price-band semantics, archive depth/publication-time measurement, then long-run security lineage/corporate actions and fundamentals before serious multi-year calibration/backtesting.


## 16. Release r5.9 — market-data completion build

r5.9 starts from r5.8 and implements the next known Stage-0 work that does not require inventing unresolved NSE semantics. It does **not** make r5.8 certified by implication; both the newer schema changes and real-source adapters still require native-Windows/Parquet and real-file acceptance.

| # | Finding | Disposition / assurance |
| --- | --- | --- |
| C59-1 | The MTO parser accepted its synthetic shape but did not validate the exchange type-10 declared row count/date or retain the reported delivery percentage | **Fixed** — type-10 trade date/count are structural; dated filenames must agree; type-20 percentage is retained. Arithmetic mismatch against quantities is a `delivery_pct_mismatch` conflict and never rewrites source evidence. |
| C59-2 | The platform had no independent current daily delivery cross-check | **Fixed** — exact 15-column `sec_bhavdata_full` delivery layout is parsed into a separate `delivery_crosscheck_observation` table. `-` delivery remains unavailable, not zero. It can raise conflicts but never populate/supersede primary MTO delivery. |
| C59-3 | MII daily price-range/tick evidence was discarded while price-band semantics remained unresolved | **Fixed conservatively** — the master retains `PricRg`, `PricRgTp`, `MaxPric`, `MinPric`, `TickSz`. No executable band state is inferred from those fields. |
| C59-4 | Price-band source collection could not start until every historical semantic was solved | **Modified** — `nse_cm_price_band` supports immutable `captured_unparsed` receipt/provenance/integrity evidence. Capture intentionally creates no `source_coverage` or `band_close_state`; historical date/effective-session and tick rounding remain Stage-0 acceptance items. |
| C59-5 | Historical source acquisition and archive naming were ad hoc/manual | **Fixed as an explicit framework** — `eos.m2.catalog` allowlists the known NSE Stage-0 sources and URL/filename conventions; `eos.m2.acquire`/`fetch_nse.py` download bytes only, with allowed-host, hash and retrieval-time controls. Live NSE network behavior remains external acceptance. |
| C59-6 | There was no deterministic date-by-date source coverage report | **Fixed** — coverage states distinguish parsed complete/incomplete, capture-only, rejected, parsed-without-coverage, receipt-only and missing. Capture-only evidence cannot masquerade as strategy coverage. |
| C59-7 | Duplicate-file detection was hash/date scoped but not source scoped; adding validation sources made a byte-identical cross-source payload theoretically capable of false-noop | **Fixed** — duplicate checks now require `source_id + file_sha256 + date`. |
| C59-8 | New delivery/reference paths needed regression coverage without weakening existing gates | **Fixed** — M2 cases cover MTO count/date/pct, validation-only full-bhav delivery, missing delivery, raw MII price-range evidence and non-semantic price-band capture; source-catalogue/acquisition/coverage has a dedicated contract test. Existing simulation/feature/engine mutation gates are unchanged. |

**Deliberate residuals.** r5.9 does not claim a universal MII effective-session formula, historical BE/BZ/right-entitlement semantics, or executable price-band state. Those require representative real-file evidence. The package fails closed instead of coding guesses.

**r5.9 build assurance.** In the available Linux/Python 3.13.5 environment, `run_all.py` ended `ALL PASSED`. `tests/test_m2.py` ran 132/132 on JSONL (66 cases × POSIX and Windows-sim), `tests/test_catalog.py` ran 3/3, manifest 4/4, release consistency PASS, portability 4/4, mutation infrastructure PASS, and the regular campaign remained 673 sites with 592 killed, 2 mutant timeouts, 79 reviewed equivalents, 0 unexplained survivors and 0 infrastructure errors. `python -m pytest -q` reported 19 passed. PyArrow is absent in this environment, so r5.9 native-Windows/Parquet and genuine MTO/full-bhav/price-band/live-download acceptance remain external.

## 17. Release r5.10 — integrity release over r5.9 (reviews of r5.7, r5.8 and r5.9)

r5.7, r5.8 and r5.9 were each reviewed by running them with Parquet in fresh Python 3.11, 3.12 and 3.13 environments, by diffing each against its predecessor, and by adversarial scripts. None of those reviews' findings reached §14–§16. r5.10 fixes every one, each with a regression that fails on r5.9. This section also keeps an **open-findings register** (the last table), so a review finding can no longer drop out of the record.

**Correction to earlier records.** Three records overstate the mutation result:
- C57-8 ("no engine survivor required a new equivalence allowlist entry");
- the r5.8 and r5.9 build-assurance paragraphs ("0 unexplained survivors");
- README counts from r5.7 to r5.9.

These are **not true**. `mutation_check.py` built each mutant without the module's `__`-prefixed globals. `reference_engine.py` reads `__file__` at import, so every engine mutant raised `NameError` while being built, and the worker counted a build failure as `killed`. None of the 84 engine mutants ever ran. With the harness fixed, the r5.9 campaign reports 22 unexplained engine survivors and fails. The dispositions below replace those statements.

| # | Finding | Disposition / assurance |
| --- | --- | --- |
| C510-1 | Engine mutants never ran: build failures were counted as kills (review of r5.7; unchanged in r5.8 and r5.9) | **Fixed** — mutants are built in the module's own globals, and a mutant that cannot be built ends the worker with `infrastructure_error`, never a kill. `tests/test_mutation.py` reproduces the old harness fault through a hook and requires `infrastructure_error`, and checks that every mutant of every reference module builds. |
| C510-2 | The first real engine campaign left 22 survivors | **Fixed** — 21 are killed by new goldens: card cases C13c–d, C20g, C21c, C25d–e, C29h–k, C30c–d, C31–C33b and C34–C34b, and pipeline cases P1 (tranche), P5, P5b and P7–P9. Some goldens use linter-valid card variants that exercise engine branches the shipped cards never use: a composite in a gate, a waivable gate, and ranking with composites plus a z-term. One survivor is a reviewed equivalent: `num()`'s None/bool guard, since a bool as Decimal 0/1 decides identically and a non-known value never reaches `num`. Final campaign: 673 sites, 591 killed, 2 timeouts, 80 reviewed equivalents, 0 unexplained, 0 infrastructure errors. Engine: 83 of 84 killed, 1 equivalent. |
| C510-3 | `earliest_signal` ties broke on ISIN alone, contradicting Doc 01 §9 and the recorded decision (larger market cap, then ISIN). Every signal of an EOD run shares one instant, so gate-only capacity was in effect alphabetical (review of r5.7) | **Fixed** — ties break on the instant, then larger market cap, then ISIN. P5 is corrected (S04, the larger cap, is admitted) and P5b covers equal caps. A planted r5.9 defect is caught by P5. |
| C510-4 | A file that parsed but failed a quality check kept its receipt with **no** parse event, indistinguishable from a crash between the two transactions (review of r5.7) | **Fixed** — every ingest path records `rejected`, with format, trade date and reason, for a post-parse quality rejection. Regression covers the backfill guard and the kill switch. |
| C510-5 | A correction delivered in the other file format was **back-dated**. UDiFF rows were keyed by `FinInstrmId` and legacy rows by ISIN+series, so the same instrument on the same date had two identities. A UDiFF correction received days after a legacy original became a "first version" inferred usable at 22:30 on the trade date. A trade-date decision saw both prices, and the canonical read failed with `IntegrityError` (review of r5.8; unchanged in r5.9). r5.8 had replaced r5.3's "same content in the other format writes no version" test with one asserting the new behaviour | **Fixed** — one observation identity, (ISIN, series), in every format (`eos/m2/identity.py`). `FinInstrmId` is kept as an attribute. The same content in either format is unchanged, and a changed value is version 2, available when received. Duplicates within a file are the same `FinInstrmId` twice, or the same (ISIN, series) under two IDs. Regressions: same content is one observation; a correction in the other format is never back-dated; a same-ISIN+series duplicate is quarantined. The 3,637-row real-derived EQ+BL case stays green. |
| C510-6 | Tombstones were written on **every** omission, although no real reissue had shown NSE reissues are complete snapshots. An omission from a file of the other format, whose row set differs, would have withdrawn rows. r5.9 extended this to the full-bhav table (reviews of r5.8 and r5.9) | **Fixed** — a new source-policy field, `reissue_semantics` (policy 1.5.0), is `unverified` for every source. An omission keeps the prior row and logs `absent_in_reissue`, saying why. With `complete_snapshot`, only a same-format omission is tombstoned. Regressions cover both modes and the cross-format case. Delivery rows now join only active price rows (r5.9 also joined tombstoned ones). |
| C510-7 | The price-band live URL could be captured under any past date. Asking for 5 Mar 2021 saved today's list as `sec_list_05032021.csv`, and the coverage report then showed that date as captured (review of r5.9) | **Fixed** — a live-URL source can only be fetched for the retrieval date in IST, and the name records the capture date, not a proven effective session. Regression in `tests/test_catalog.py`. |
| C510-8 | The downloader trusted any response (review of r5.9). An HTML "Access Denied" page served with HTTP 200 was saved as `BhavCopy_…csv.zip`. Redirect targets were not host-checked, there was no rate limit or size cap, and an existing file was overwritten | **Fixed** — https only; the NSE host allowlist is enforced on every redirect and on the final URL; content checks reject HTML pages, missing zip/gzip magic bytes and binary-for-text; size cap; minimum request interval; identical bytes are reused and a reissue saved beside the original; `retrieved_at` is taken before writing. Regressions for each. |
| C510-9 | r5.9 described full-bhav delivery as a cross-check of MTO but never compared them (review of r5.9) | **Fixed** — whichever file arrives second compares per (ISIN, series), logging `delivery_source_mismatch`, `delivery_traded_qty_mismatch` or `delivery_availability_mismatch`. MTO stays primary and neither value is changed. Regression in both arrival orders. |
| C510-10 | The catalogue had only the UDiFF bhavcopy URL, so no pre-July-2024 history could be downloaded, although the Stage 0 plan needs it (review of r5.9) | **Fixed** — the bhavcopy URL follows the layout in use on the date, with an explicit `--variant` override. The cut-over date (`UDIFF_ONLY_FROM`, 8 July 2024) is **unverified** and only chooses the URL. Month names come from a fixed table, never the locale. |
| C510-11 | `coverage_report.py` counted weekends as missing, and silently created an empty warehouse when given a wrong path (review of r5.9) | **Fixed** — weekdays by default (`--include-weekends` to widen), with a note that weekday holidays still read as missing until the trading calendar exists. `Warehouse(create=False)` makes a wrong path an error. |
| C510-12 | Found while writing P8: a card whose sizing formula omits the max-position term had its quantity capped by the engine, but the uncapped target was reserved as cash, leaving it idle and starving later candidates | **Fixed** — the model's allotment and model-size checks use `min(sizing, notional_capital × max_position_pct)`. Golden P8 shows such a card behaves exactly like its capped twin; a planted r5.9 defect is caught. |

**Open-findings register** (every finding not fully closed; each row must be dispositioned by the release that closes it):

| # | Item | Owner and gate | State |
| --- | --- | --- | --- |
| O-1 | Native-Windows/Parquet run of r5.10 in a fresh environment with only declared dependencies | Harsh; before any warehouse data is trusted | Open (r5.7 passed; r5.8–r5.10 not yet run there) |
| O-2 | Real-file re-ingest: the 24-Sep UDiFF/MII sample, plus MTO, full-bhav and price-band captures, for a few dates | Harsh / Stage 0 S1b | Open |
| O-3 | Live NSE downloads through `fetch_nse.py` (session warm-up, anti-bot behaviour) | Harsh / Stage 0 S1b | Open; can only be tested live |
| O-4 | Reissue semantics per source: are NSE reissues complete snapshots? | Stage 0; first real reissue | Open; `unverified`, so no tombstones |
| O-5 | The bhavcopy layout cut-over date (`UDIFF_ONLY_FROM`) and whether both formats were published in parallel | Stage 0 archive check | Open; affects only which URL is tried |
| O-6 | The MTO type-10 declared-count field on a real file | Stage 0 S1b | Open; a wrong assumption fails loudly |
| O-7 | MII effective-session convention; price-band layout, date semantics and tick rounding | Stage 0 multi-date sample | Open (carried from r5.8/r5.9) |
| O-8 | The two lifecycle records edited in place in r5.7 to add `linter_report_path` (records are append-only in spirit) | Harsh; at card confirmation | Open; recorded here, no integrity impact (nothing hashes the records) |
| O-9 | `snapshot()` re-hashes every raw file each time; the cost grows with a multi-year backfill | Before the first multi-year backfill | Open; measure on the warehouse machine |

