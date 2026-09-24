# Equity Opportunity System — Specification v5.6

*Release r5.6 · 24 September 2026 · Controlling package bound by MANIFEST.json*

## 1. What this system is

An autonomous personal opportunity-discovery and recommendation system for Indian listed equities.

It continuously evaluates the investible universe across **every active, independently defined and validated strategy** — long-term, momentum, swing, event and catalyst, intraday, and any strategy added later. A security is never assigned to a category. It becomes an opportunity only when current point-in-time information satisfies the requirements of one or more strategies. The system has no obligation to recommend anything, and it stays silent when nothing meets the required standard. Where several strategies identify the same security, each rationale stays independently traceable. Every decision and every order remains yours.

The system researches, screens, monitors and recommends. It never places orders, holds no credential that can place one, and routes nothing to a broker.

## 2. Design principles

| Principle | Meaning in practice |
| --- | --- |
| Broad in what it searches | Every production strategy evaluates the whole market-eligible universe on its own trigger. You never choose which screen to run |
| Strict in what it recommends | Only strategies in `production` status can put an opportunity in front of you. Experimental and shadow strategies work silently |
| Autonomous in doing the work | Scheduled and event-triggered evaluation, monitoring and expiry run without intervention |
| Silent when nothing qualifies | Absolute gates, never quotas. A ranked list always has a number one; this system does not have to |
| Independent in how strategies are defined and validated | Each strategy is its own hypothesis with its own card, data, triggers, costs and validation class |
| Unified in how opportunities reach you | One opportunity per security, carrying one claim per qualifying strategy |
| Conservative about data truth | Point-in-time everywhere; unknown is never zero; missing history is never treated as absence |
| Manual at execution | No order path exists in the system, by construction and by deployment policy |

## 3. How it works

```mermaid
flowchart LR
  S[Sources: exchange files, filings] --> W[Point-in-time warehouse]
  W --> F[Feature store]
  O[Orchestrator: schedules and events] --> E[Strategy engines]
  F --> E
  E --> R[Resolver and portfolio allocator]
  P[Your holdings and policy] --> R
  R --> B[Opportunity briefs]
  B --> N[Notifications and monitoring]
  N --> J[Your decision and journal]
```

1. **Data** arrives from exchange files and company filings, is stored immutably, and becomes usable only from the moment it was actually available (Document 02).
2. **The orchestrator** decides which strategy engines run and when: end of day, weekly, on a new filing, or — for intraday strategies once implemented — during the session.
3. **Each strategy engine** applies its own card: data requirements, absolute gates, optional ranking, sizing, entry, exits and expiry, under one set of evaluation rules fixed in the registry. Engines never see each other.
4. **The resolver** merges claims on the same security into one opportunity and never scores agreement: each claim is a weight of its strategy's measurement capital, and the security's size is the largest weight applied to your capital, never the sum, so two strategies agreeing cannot double your exposure. **The allocator** then re-checks impact at your size and applies your portfolio policy — caps, concentration and cash — against actual holdings. When capacity is scarce it fills it in a fixed order: existing holdings, earliest signal, larger company.
5. **An opportunity brief** is produced only when at least one production strategy qualifies. A strategy-valid opportunity that breaches your policy is recorded as *valid but not currently actionable*, not erased.
6. **Monitoring** tracks every live opportunity until it expires, is invalidated, is acted upon, is rejected or closes, and tells you what changed.

## 4. What you see

A short feed. Either:

> **No qualifying opportunities.** 500 market-eligible securities evaluated by 2 production strategies; data healthy.

or a few briefs. Each brief states:

- what is recommended, and which strategy or strategies found it
- why now
- the horizon
- the actual values that triggered each gate
- key supporting evidence
- **material counter-evidence, each class shown with what was searched and its coverage — "none found" only when that coverage is adequate by a stated rule**
- data confidence, strategy status and evidence strength, each shown separately
- portfolio fit
- entry range, invalidation, expiry and lineage

Urgency follows horizon. An intraday setup would notify immediately; a long-term valuation opportunity appears in the next briefing. You accept, reject or defer, optionally with a reason. The system does the rest of the record-keeping.

## 5. Strategies

A strategy is a lens through which the system evaluates the market, not a bucket a company belongs to or a pot your capital is divided into. Each strategy keeps a *model portfolio* whose size and construction are part of its hypothesis, so its performance can be measured independently of what you personally act on. Your actual money is governed by one portfolio policy and one allocator, and changing it never changes a strategy's measured results.

| Strategy | Class | Status | Role |
| --- | --- | --- | --- |
| `ltqv_v1` long-term quality/value | fundamental_long_term | experimental | Reference implementation proving point-in-time fundamentals |
| `mom_v1` momentum | momentum | experimental | Reference implementation proving daily market data, technicals and frictions |
| Swing / mean reversion | swing | planned | Shorter-horizon technical logic |
| Event / catalyst | event_catalyst | planned | Disclosure-triggered evaluation, with evidence from filings |
| Intraday | intraday | planned; architecture reserved | Minute-level data, session state and microstructure simulation (Document 02 §16) |

The two reference strategies prove the framework; they are not the product's boundary. Every class above is already registered, with its data resolution, triggers and validation class. Adding a strategy means writing a card, not changing the platform. The system may propose hypotheses for new strategies, but a new strategy can recommend only after versioning, backtesting, an untouched holdout, and shadowing.

## 6. The controls that make recommendations trustworthy

| Control | What it prevents |
| --- | --- |
| Point-in-time warehouse with `effective_from`, `system_available_at` and a single `as_of_ts` per run | Using information before it was available — the most common way a backtest lies |
| Six explicit value states (`known`, `missing`, `stale`, `conflicted`, `not_applicable`, `out_of_domain`) | Missing data being read as zero, or absence as a clean record |
| Closed-schema strategy cards pinned to the hash of the registry entries they use, compiled by `speclint`, and **executed** by a reference engine against hand-computed card-level cases that fail when a card's meaning changes | Silent drift in what a strategy means, and a card that passes every check while meaning something else |
| One normative set of evaluation rules — unknowns in gates, three-valued exits, stale and conflicted values, filters, decimal comparison — and a reference implementation of every feature a card reads | Two implementations of the same card reaching different decisions |
| Strategy lifecycle as an audited state machine held in lifecycle records outside the card, with publication rights enforced server-side | An unvalidated experiment reaching your feed because it looks exciting today |
| Separate model and actual ledgers | Confusing strategy quality with your own choices |
| Run manifests binding data, code, cards, registry closures, lifecycle records, policies and environment by hash | Results that cannot be reproduced |
| Document 04 validation protocol: executable golden cases for simulation, features, cards and whole populations through to published claims, planted defects that must all be caught, and a mutation check on fixture adequacy; dated cost and tax schedules; a promotion hurdle that rises with the number of trials; a per-lineage holdout ledger that inherits exposure across derived lineages; an append-only trial log (enforcement built before the first calibration run) | Backtests that reward curve-fitting, or assume fills and costs that couldn't happen |
| A read-only broker adapter with no order methods, and a network policy denying broker access to the AI and dashboard components | Any path from a recommendation to an order |

## 7. Status and readiness

| Gate | State |
| --- | --- |
| Architecture, data contract, validation protocol | r5.6. Every finding of the independent audit of r5.4 (Issue Log §12) and of the review of r5.5 (§13) is resolved in the package, each with a test that fails on the release it came from. Remaining items are scheduled to the phase where they first matter (Document 01 §17) |
| Stage 0: sources, parsers, security master, prices | **In progress.** M2 price ingestion is built (r5.3), hardened (r5.4), made codec-independent with row quarantine (r5.5), and given per-platform durability, a crash-safe OS writer lock and write-once raw landing (r5.6). Its full suite passes on Linux on both codecs and on the Windows code paths under emulation. **It has not yet been run on the Windows warehouse machine: that run is the next gate** (README, Certification). Real-file hardening (S1b) waits for the NSE sample files |
| Formal backtesting | Protocol, reference engine and golden cases exist. Blocked until the production engine (M5, M6, M7, M14) passes every golden file unmodified; the trial log, holdout enforcement, Brinson–Fachler and the run-manifest validator exist; each card's measurement parameters are pre-registered; and your contract note reconciles with the cost model |
| Shadow use | Blocked until a strategy passes backtest, holdout and golden cases, and you set its OPEN parameters |
| Production recommendations | Blocked until shadow evidence supports promotion |
| Automated execution | Permanently out of scope |

## 8. Controlling package

The controlling set is the file package whose SHA-256 digests are recorded in `MANIFEST.json`. Editable copies anywhere else — including live documents — are drafts.

| Artefact | Role |
| --- | --- |
| This overview (v5.6) | Product scope and principles |
| Document 01 r9 — Core Platform Architecture | Modules, flows, evaluation semantics, state machines, boundaries |
| Document 02 r6 — Data Contract & Canonical Schema | Every table, field, source, timing rule and feature definition |
| Document 03 r8 — Strategy Pack | Reference strategies; card sections generated from the YAML |
| Document 04 r5 — Validation Protocol | Simulation, costs, tax view, holdout lineage, trials, stress, metrics, promotion statistics, acceptance |
| `registry.yaml` 3.1.0 | Single owner of feature, vocabulary, evaluation-semantics and session-policy metadata; each entry versioned |
| `lifecycle/`, `register_card.py` | Each card version's status and the evidence behind it |
| `policies/market_universe.yaml` | The universe policy: N = 500 and its buffers |
| `strategies/*.yaml` | The only executable source of each strategy |
| `schemas/*.json` | Card, run-manifest, portfolio-policy and lifecycle-transition schemas |
| `speclint.py`, `test_speclint.py`, `render_cards.py`, `make_manifest.py` | Compiler, regression suite, rendering parity, package binding |
| `reference_sim.py`, `reference_features.py`, `reference_engine.py`, `golden/*.yaml`, `test_golden.py`, `test_features.py`, `test_card_golden.py`, `test_pipeline.py`, `mutation_check.py`, `schedules/*.yaml` | Executable meaning of simulation, features, cards and the whole evaluation; golden cases; fixture-adequacy check; dated cost and tax schedules |
| `run_all.py`, `tests/test_portability.py`, `requirements*.txt` | One command for every check on any OS; portability regressions; pinned dependencies |
| `portfolio_policy.yaml` | Your policy, values OPEN until you set them; the allocator's rules are fixed |
| Stage 0 Plan | Data-reality sources, order of work, files to download |
| `eos/`, `tests/`, `policies/source_policy.yaml` | Product code (Stage 0), its tests, and the source and availability policy |
| Issue Log & Traceability r5.6 | Disposition of every review finding |

## 9. What comes next

1. **Stage 0.** Exchange-file ingestion; the XBRL parser prototype; the security master (including real ISIN changes); the vendor bake-off; verification of historical source coverage, including share-count history for the universe; reconciling one of your contract notes against the cost model; confirming the items in Document 04 §17.
2. **Real-data golden cases**, added as Stage 0 produces verified data: merger, demerger, split with an ISIN change, bonus with fractions, rights with and without a listed entitlement, restatement, standalone and consolidated filed on different days, price correction, late-published file, trade-for-trade, surveillance entry, suspension and delisting.
3. **Take `mom_v1` end-to-end first**: pre-register its measurement parameters, calibrate its delivery bands, evaluate the design period, run the sealed holdout, then shadow. It needs only exchange files; `ltqv_v1` also waits on XBRL depth and share-count history.
4. **Document 07 — Build, Release and Operations**, phased: each control is due at the phase Document 01 §17 names. **Document 05 — AI Evidence**, before M12. **Document 06 — Presentation**, before the dashboard.

Findings from here on go into the issue log and are resolved through executable tests, not further design rounds.
