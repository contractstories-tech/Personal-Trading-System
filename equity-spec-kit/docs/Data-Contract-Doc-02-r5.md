# Data Contract & Canonical Schema — Document 02 r5

*Release r5.5 · 24 September 2026 · current state only; revision history is in the Issue Log*

Governs every table, field, source, timing rule and feature definition referenced by Document 01 r8 and the strategy cards. The corrections the real Stage 0 files teach go into the next revision, r6, at Stage 0 close. A card owns its thresholds; how the compared value is computed is defined here and in `registry.yaml`. An identifier a card uses that is not in the registry fails the build.

## 1. Conventions

| Convention | Rule |
| --- | --- |
| Timestamps | UTC `TIMESTAMPTZ`; session logic in IST (UTC+05:30, fixed) |
| Dates | `DATE` for trading dates and period ends, interpreted in IST |
| Money and prices | `DECIMAL(20,4)` in INR. Crore appears only in feature codes that say so (`adv_20d_cr`) |
| Shares, volumes | `BIGINT` |
| Ratios and statistics | `DOUBLE`, stored as decimals: 15% is `0.15`; a spread of 2.1 percentage points is `0.021` |
| Nulls | Never meaningful alone; every nullable value carries a `value_state` |
| Basis | Every financial fact carries `basis`; features use consolidated, falling back to standalone only where none is filed, and record which |
| Owners' share | Consolidated profit and equity attributable to owners of the parent |

## 2. Sources and the source policy

Each source has a `source_id` and a role per domain. **Primary** populates; **validation** is compared against it and can raise `conflicted` but never overwrites; **fallback** populates only when primary is missing, and is recorded on the row. Priorities form a versioned `source_policy` with validity dates, and every snapshot records the version it was built under.

| Domain | Primary | Validation |
| --- | --- | --- |
| Daily OHLCV, traded value | NSE bhavcopy | Broker end-of-day candles |
| Delivery | NSE security-wise delivery file | — |
| Price bands | NSE daily price-band file | Derived from OHLC vs prior close |
| Corporate actions | NSE/BSE announcements | Licensed vendor |
| Financial statements | Licensed vendor after the Stage 0 bake-off; exchange XBRL until then | Original filing |
| Filing timestamps | Exchange announcement timestamp | Vendor |
| Shareholding and pledge | Exchange shareholding-pattern XBRL | Licensed vendor |
| Shares outstanding | Derived from corporate actions and allotments (§5) | Shareholding-pattern totals |
| Auditor events, related-party transactions | §13 | — |
| F&O eligibility | NSE contract files, dated | — |
| Surveillance | NSE ASM/GSM lists, dated | BSE lists |
| Sector classification | Licensed vendor, versioned; mapped via `sector_map` to registry `sector_codes` | Exchange classification |
| Benchmarks | NSE Indices TRI series | — |
| 10-year G-sec yield | RBI / FBIL | — |

**A vendor's timestamp never beats the exchange's.** A vendor that cannot supply exchange-traceable filing timestamps and restatement history fails the bake-off.

**Source coverage is recorded, not assumed.** `source_coverage(source_id, date, complete)` states whether a complete snapshot exists. Absence from a complete snapshot is a known negative; absence where no snapshot exists is `missing`, reason `no_source_coverage`.

## 3. Time

**`as_of_ts`.** Every run has one. For a live run it is the evaluation cutoff; for historical computation each row carries `row_cutoff_ts`, the cutoff of its trading date.

**Two cutoff domains, and every row belongs to one.** A single cutoff cannot express the policy: a run at 23:00 must use the 22:30 bhavcopy for day D while ignoring a company filing made at 21:00. Each run therefore carries **two** cutoffs, both recorded in its manifest, and a row is tested against the cutoff of its own domain.

| Domain | Cutoff on D | Sources |
| --- | --- | --- |
| `disclosure` | 20:00 IST | Filings, financial facts, shareholding, auditor events, related-party disclosures, corporate-action notices |
| `exchange_eod` | 23:00 IST | Bhavcopy, delivery, price bands, surveillance lists, F&O contract files, index levels |

Exchange files describe trading that already happened, and the proposed order executes at D+1's open, so waiting for them is not look-ahead. A company filing after 20:00 is new information and belongs to the next run. The domains and their times are in `registry.yaml` under `cutoff_policy`.

**Availability.** Every point-in-time row carries:

| Field | Meaning |
| --- | --- |
| `filed_at` / `source_published_at` | When the source made it public |
| `received_at` | When the pipeline ingested it |
| `effective_from` | `filed_at + policy_lag` (30 min for structured XBRL and CA notices; 4 h for PDF-only) |
| `system_available_at` | When the live pipeline actually had it processed |
| `usable_from` | `greatest(effective_from, system_available_at)`, materialised; the only field point-in-time joins test |

**Historical backfill.** Data ingested after the fact has no live `system_available_at`. The rules are set **per source** in `policies/source_policy.yaml`, because separate artefacts (the bhavcopy and the delivery file, for example) have separate publication processes:

- **First version of a row.** It is treated as published at the source's `inferred_published_time_ist` on its trade date. Its `system_available_at` is set to `effective_from`, and it is flagged `availability_inferred = true`.
- **Later version (a correction).** It is **never** inferred. It is available when this system actually received it, so a correction is never back-dated.
- **Invariants.** Each rule records `inferred_basis`, either `unverified` (an assumption) or `measured` (from live capture). The loader refuses any inferred time at or after the source domain's cutoff.
- **Recalibration.** Document 04 recalibrates these times, and `policy_lag`, to a conservative percentile of observed live latency once enough live history exists, and re-derives inferred values under the new policy version.
- **Reporting.** Validation reports state what share of the evidence rests on inferred rather than observed availability.
- **Pre-capture corrections.** Exchange archives serve only final, corrected files. Corrections made before live capture began cannot be recovered, and historical evidence carries that limitation explicitly.
- **Backfill is only for history the system could not have captured live.** The loader refuses backfill inference for a file received on its own trade date, or fewer than `backfill.min_age_days` days after it — a same-day file is a live file. It also refuses it for any trade date on or after `backfill.live_capture_start`, which is set when the scheduled downloader begins. Otherwise a replay could "see" a file its live run did not have.

**Usable in the run for D** if and only if `usable_from ≤ cutoff(domain of the row, D)`. Orders proposed by that run execute at `next_executable_session(D)`.

**Trading calendar.** `trading_calendar(date, is_trading_day, session_type)` with `session_type` in `normal`, `muhurat`, `special_preopen`, `holiday`, `closure`. `next_executable_session(D)` is the first later trading day that is not `muhurat`. "N sessions after" always counts executable sessions.

**Fiscal periods** are identified by actual `period_start` and `period_end`, never assumed.

## 4. Security master and historical state

- **Identity is the `security_id`; the ISIN is its current identifier.** A face-value change normally allots a new ISIN in India, as do some capital reductions and schemes. `security_lineage(security_id, isin, valid_from, valid_to, reason, ca_event_id)` keeps half-open, non-overlapping ISIN windows per security. Features, universe membership and its hysteresis, claims, cooldowns, `holding_days`, model positions, the ledger holding, tax lots and stop and price state are keyed by `security_id`; raw observations and broker trades keep the reported ISIN. Across an ISIN change the price series joins with the action's `f` applied, held quantity is divided by `f`, price state is multiplied by `f`, and holding periods, cooldowns and tax-lot dates carry unchanged (registry `security_identity`; golden cases G33a–b). A merger target converts into the successor's `security_id` at the scheme ratio on the record date. Symbols, BSE codes, broker tokens and former names are aliases with half-open validity windows; overlapping windows are errors.
- **Scope.** NSE main-board equity. Excluded entirely: SME listings, ETFs, REITs, InvITs, preference shares, debt. **Trade-for-trade series stay in the research universe but are excluded from the market-eligible universe.** The reason is platform-level, not strategy-specific: the exchange places securities there under surveillance, every trade settles compulsorily by delivery, and there is no intraday netting, so their trading conditions differ from the rest of the universe for every strategy — not only for those reading delivery data.
- **State tables**, all queried as-of, all with source coverage: `security_classification`, `index_membership` (benchmarks only), `derivatives_eligibility`, `surveillance_status`, `restriction_state` (manual, with author and timestamp).
- **Surveillance before the frameworks existed.** `surveillance_framework(framework, start_date)` records when each framework (ASM long-term, ASM short-term, GSM) began; exact dates are verified at Stage 0. For dates before a framework's start, `surveillance_stage` is **known `none`** — nothing existed to be under. After the start, a date without list coverage is `missing`. Treating the pre-framework years as missing would fail every security for half the history.
- **`sector_map`** is versioned and maps vendor classifications to registry `sector_codes`; an unmapped classification is an error.

## 5. Corporate actions

**Two dates per action.** Price continuity changes on the ex-date; share count changes when shares exist.

**Price adjustment factor `f`** (historical prices × f; historical quantities ÷ f):

| Action | f |
| --- | --- |
| Split / consolidation | pre-action shares ÷ post-action shares (₹10 → ₹1 face value: f = 0.1) |
| Bonus a:b (a new per b held) | b ÷ (a + b) |
| Rights a:b at price S | TERP ÷ P_cum, TERP = (b·P_cum + a·S) ÷ (a + b); f = 1 if S ≥ P_cum |
| Demerger | P_discovered ÷ P_cum, where P_discovered is the **parent's** price from the special pre-open session |
| Special dividend D with D ÷ P_cum > 0.05 | (P_cum − D) ÷ P_cum, in `price_adjusted` only |
| Ordinary dividend | 1 in `price_adjusted`; total return only |

**Share-count timing.** Splits, bonuses and consolidations change `shares_outstanding` at the ex-date, 09:00 IST. Rights, QIPs, preferential and ESOP allotments, conversions and merger consideration change it from the allotment disclosure's `usable_from`; buybacks from the extinguishment disclosure. Quarterly shareholding totals reconcile against the derived count; a difference above 1% sets `conflicted`.

**Issuance-neutral share count.** `shares_issuance_neutral` removes split, bonus and consolidation effects, so it moves only on genuine issuance or cancellation. Dilution measures read it.

**Position policy `standard_equity_ca_policy_v3`**, applied centrally by M14 and M15:

| Action | Held quantity | Price-state values | Cash / other | Valuation blackout |
| --- | --- | --- | --- | --- |
| Split, bonus, consolidation | ÷ f; fractions paid as cash in lieu at the post-action price, fraction × P_cum × f; a new ISIN continues the same `security_id` | × f | — | — |
| Special dividend | unchanged | × f | cash credited | — |
| Ordinary dividend | unchanged | unchanged | cash credited | — |
| Rights issue | unchanged until allotment | × f | floor(held × a ÷ b) whole entitlements (fractions ignored), valued and sold: at the traded close on the last trading session where rights entitlements were listed (2020 onward), else intrinsic max(0, TERP − S) — TERP is known before trading and deterministic | ex-date until allotment reaches `shares_outstanding` |
| Demerger (parent held) | parent unchanged | parent × f | resulting-entity **stub** of held × r whole shares, where r is the scheme ratio in resulting shares **per parent share**. Implied price per resulting share = (P_cum − P_discovered) ÷ r; a fractional entitlement is cash in lieu at that price, so the total detached value is always held × (P_cum − P_discovered). State `unlisted_stub`, non-tradable, excluded from caps and capacity; exited at the open of its first executable session after listing | parent valuation features until four post-demerger quarters are filed |
| Merger (held security is target) | converted at scheme ratio on record date | series ends | if the successor is not strategy-qualified for the holding strategy: exit at the open of the target's last announced trading session | — |
| Capital reduction | per scheme | × f | per scheme | until the next half-yearly balance sheet reflects it |

**Why valuation blackouts exist.** After a demerger, market cap falls to the continuing business while trailing profit still includes the business that left, so earnings yield jumps with nothing becoming cheaper. During a blackout, `earnings_yield_ttm`, `ey_vs_own_5y_median` and `ev_ebitda_vs_sector` are `out_of_domain`. `ey_median_5y` excludes blackout sessions and every session on or before the latest **valuation-transformative** action — a demerger, a capital reduction, an amalgamation in which the company is the transferee, or a merger in which it is the target (registry `valuation_transformative_actions`). The historical comparison therefore covers only the continuing business. A rights issue is not valuation-transformative; it gets only its blackout, so a small rights issue does not remove a company from `ltqv_v1` for three years.

**Corporate-action and dividend cash has two dates.** Economic return is recognised on the ex-date; **cash becomes spendable only on the payment or credit date**. A model portfolio that spends a dividend before it is paid has created liquidity that did not exist. Each expected receipt is written to `expected_cash_event` (amount, ex-date, expected credit date, source action), so the later actual credit in M15 matches an expectation instead of raising a reconciliation break.

**Executed trades are immutable.** Position arithmetic uses `entry_basis` and the other price-state values, which the policy adjusts.

## 6. Prices

**Versioned observations.** `price_observation`: `isin` · `trade_date` · `version_no` · `series` · `open` · `high` · `low` · `close` · `prev_close` · `volume` · `traded_value` · `num_trades` · `source_id` · `source_published_at` · `received_at` · `effective_from` · `system_available_at` · `usable_from` · `availability_inferred` · `supersedes_version`. The key is `(isin, trade_date, version_no)`, and a duplicate key is an integrity failure that stops the read. A correction is a new version and never overwrites an old one.

**Delivery is its own table.** `delivery_observation` (`isin` · `trade_date` · `version_no` · `delivery_qty` · `traded_qty_reported` · the same availability fields) is versioned independently. The delivery file is a separate source with its own arrival time, corrections and coverage. Were it a column on the price row, a late delivery file would look like a price correction. Its rows are mapped to ISINs through the same trading date's bhavcopy.

**Row quarantine.** A row failing a row-level check is written to `row_quarantine` with its reason, instead of rejecting the day's file. Row-level checks are a malformed or duplicate ISIN, an impossible OHLC (including zero prices), a negative quantity, or an unmapped or invalid delivery row. The file is rejected — nothing written — only on a structural fault (header, mixed dates, the canary prefix), or when the quarantined share exceeds `quality.max_quarantine_share`. How a genuine no-trade row is stored is settled on the real files (S1b).

**Resolution.** Per `(isin, trade_date)`, the resolved view takes the highest version whose `usable_from` is at or before the cutoff. It joins delivery with `delivery_state` (`known`, or `missing` with reason `no_source_coverage`, `absent_in_covered_file`, `quarantined` or — in a panel read — `not_yet_available`). There are two read contracts, because they answer different questions:

| Contract | Cutoff | Use |
| --- | --- | --- |
| `history_known_as_of(E)` (Document 02 name `price_raw_resolved`) | E's cutoff, for every trade date up to E | The exact input of **one** decision at E. A correction received by E replaces the original print, even for earlier bars |
| `point_in_time_panel(start, end)` with `panel_as_of(panel, E)` | Each trade date's **own** cutoff; a bar first published after it keeps its first version and real `usable_from` | A look-ahead-free panel for a **sequence** of decisions. Each bar is taken as first known, so corrections a later decision could have seen are ignored — a conservative choice. `panel_as_of` masks what decision E could not yet use; no bar a later decision had is ever dropped |

A sequence of historical decisions uses either the exact per-date view or the masked panel. It must never use `history_known_as_of(end)` over the whole range, because every earlier decision would then see corrections that arrived after it. Everything downstream reads a resolved view.

**Series.**

- `price_raw` (resolved): as printed; the only series for execution simulation and band detection.
- `price_adjusted`: `raw × F_cum(t)`, where `F_cum` multiplies every `f` with `ex_date > t` recorded in the adjustment version in use; volume is divided by `F_cum`. Each new action creates a new `adjustment_version`.
- `price_total_return`: `TR(t) = TR(t−1) × (adj_close(t) + adj_div(t)) ÷ adj_close(t−1)`, bound to the **same** `adjustment_version`. Pre-ex-date ratios are invariant to a common rescaling; only the ex-date step needs the matching version. Special dividends already removed in `price_adjusted` are not added again.

**Band state** `band_close_state`: `closed_at_lower_band`, `closed_at_upper_band`, `within_band`, or `missing` when no band file exists. This is a closing fact; it says nothing about whether a trade was possible at the open. Fill feasibility is Document 04's decision.

**Delivery.** `delivery_pct = delivery_qty ÷ volume`. **Traded value** comes from the bhavcopy, never close × volume.

## 7. Financial facts

**Canonical facts** (the only columns of `pit_financial_facts_wide`): `revenue`, `other_income`, `finance_costs`, `depreciation`, `exceptional_net` (gains positive), `pbt`, `tax`, `pat_owners` (quarterly); `total_equity_owners`, `non_controlling_interest`, `total_liabilities`, `borrowings` (excluding leases), `lease_liabilities`, `cash_equivalents`, `receivables`, `inventory`, `total_assets`, `cfo` (half-yearly); `shares_outstanding` and `shares_issuance_neutral` (event-driven, §5).

**`cash_equivalents`** = cash and cash equivalents + other bank balances + current investments, **excluding** earmarked balances (unpaid-dividend accounts, margin money, lien-marked deposits) and all non-current investments.

**Derived measures.**

```text
ebit_underlying  = pbt + finance_costs - other_income - exceptional_net
ebitda           = ebit_underlying + depreciation
capital_employed = total_equity_owners + borrowings + lease_liabilities - cash_equivalents
average CE (FY)  = (capital_employed at prior FY end + capital_employed at this FY end) / 2
pat_underlying   = pat_owners - exceptional_net * (1 - etr)
                   etr = tax / pbt if pbt > 0 and 0 <= etr <= 0.5, else exceptionals removed gross
```

**Leases are inside capital employed.** Under Ind AS 116, lease interest sits in finance costs and is added back to EBIT. Leaving lease liabilities out of capital employed would count the income from leased assets while ignoring the capital funding them, inflating returns for store-heavy businesses from 2019. Pre-2019 history, when rent was an operating expense, is internally consistent under the same formula.

**Durations.** Raw facts carry `period_start`, `period_end`, `reported_duration` (`quarter`, `half_year_ytd`, `nine_month_ytd`, `full_year`), `canonical_period` (Q1–Q4, H1, H2, FY) and `normalisation` (`as_reported`, `derived_from_ytd`, `derived_q4`). Flows are normalised to discrete periods before entering the wide view: Q2 = H1 − Q1; Q3 = 9M − H1; Q4 = FY − 9M, else FY − (Q1+Q2+Q3). Any non-known component makes the derivation `missing`. The raw figures are preserved.

**TTM.** Flows: sum of four contiguous discrete quarters. Balance-sheet items: latest half-yearly value, with its `period_end`. Cash flow: at a half-year end, CFO_TTM = CFO_FY(prior) − CFO_H1(prior) + CFO_H1(current); at a year end, CFO_FY.

**Accounting regime.** Every fact carries `accounting_regime` (`indian_gaap` or `ind_as`). Ind AS was adopted in phases from FY 2016-17, so multi-year windows reaching earlier cross a definitional break in revenue recognition, depreciation, leases and consolidation. A feature whose window spans the change is computed but flagged `regime_spanning`, and Document 04 requires results to be reported separately for signals that depended on a regime-spanning feature. Whether a card's evaluable period should start after the transition is a Stage 0 decision, recorded in the card, not an implementation choice.

**Restatements** append a version with its own availability fields. A derived figure uses the component versions usable at the row's cutoff.

**Point-in-time assembly of periods.** Facts are stored as `fact(isin, basis, fact_code, period_start, period_end, version, usable_from, …)`. A feature over several periods (TTM, three or five fiscal years, a prior year's balance sheet) is built from the **period panel as of the cutoff**: for each period, its latest version usable at the cutoff (`period_panel_as_of`). A restatement of an old period that arrives after a newer period was filed replaces that old period only; it never becomes "the latest row" (golden cases G31a–c).

**Basis, decided as of the cutoff for the whole window.** A multi-period feature uses consolidated figures if consolidated figures usable at the cutoff exist for every period of its window. It uses standalone figures if none of them has consolidated figures. If the window would mix bases, it is `missing`, never a blend (`basis_for_window`; golden cases G23a–d). The decision uses only what was usable at the cutoff, never today's knowledge that a company later began consolidating.

**Wide view key:** `(isin, basis, effective_from)`, with `usable_from` materialised; it serves single-row facts and the canonical join of Document 01 §14.

## 8. Features

`registry.yaml` owns every feature's version, type, series, cadence, formula, domain, `out_of_domain` outcome and default Unknown behaviour. Cards override Unknown behaviour (`exclude`, `fail` or, for secondary inputs, `penalise`) only where the strategy needs different treatment. There is no implicit platform fallback. **`reference_features.py` implements every feature and forensic flag a card reads, and `golden/feature_cases.yaml` fixes each with hand-computed answers; `test_features.py` checks that every card-read feature has golden cases.** M6 must reproduce them all.

**Rolling windows** follow the registry's `window_conventions`:

- A session is an executable exchange session. Muhurat sessions are never units, and their bars are stored but not used.
- A security is *present* when a resolved bar exists for it. A suspended or untraded session is absent. A listed-but-untraded session counts as present with zero traded value for ADV.
- `X(t−k)` falls back to the last present value within 5 sessions, else missing.
- Volatility uses log returns between consecutive present sessions only, with a sample standard deviation × √250.
- Each windowed feature states its minimum presence.
- `delivery_pct_20d_avg` is a volume-weighted ratio of sums over the last 20 sessions with volume > 0 and known delivery, with ≥ 15 such sessions. It is not a mean of daily ratios, in which a ten-share day would weigh like a ten-lakh day.

**Materiality.** Every feature is **material** unless `registry.yaml` lists it under `secondary_features`. A material input may never be given `penalise`, and may never feed a gate that waives on unknown, directly or through a composite. `penalise` is defined exactly: each penalised input that is not known lowers `data_confidence` one band (`high → medium → low → insufficient`); below `medium` a claim is recorded but not shown. Confidence never alters a score or a rank.

**Value states:** `known`, `missing`, `stale`, `conflicted`, `not_applicable` (meaningless for this entity type; never implies failure on its own), `out_of_domain` (inputs valid but outside the range where the feature means anything). `out_of_domain` resolves by the feature's declared outcome: `fail` fails any gate reading it and fires any exit reading it; `drop` removes it from composites and makes it unknown for any gate. How gates, exits and filters treat each state is fixed in the registry's `evaluation_semantics` (Document 01 §7): `stale`, `conflicted` and `not_applicable` are non-known in a gate.

**Domain rules needing more than a line:**

| Feature | Rule |
| --- | --- |
| `roce_3y_avg`, `roce_hy_ttm` | Per the registry's `roce_rule`. Equity ≤ 0 → `out_of_domain: fail`. The cash-rich test is on the **average** capital employed actually used as the denominator: average CE ≤ 5% of average total assets (inclusive) with underlying EBIT > 0 → **1.00, capped**, flag `cash_rich_capped`; with EBIT ≤ 0 → `out_of_domain: fail`, since a cash shell earning nothing is not a quality business. Every other value is capped at 1.00. This avoids both failing excellent cash-rich businesses and rewarding loss-making treasuries or near-zero denominators (golden cases G17a–o) |
| `interest_coverage` | Capped at 100; zero finance costs → 100 and `no_finance_cost = true` |
| `ev_ebitda_vs_sector` | Peers: same sector code in the market-eligible universe on the date, before any card's exclusions, excluding the security itself; non-positive-EBITDA peers excluded; ≥ 8 valid peers; peer median > 0; not in blackout; otherwise `drop` |
| `promoter_pledge_pct` | A company with no promoter holding has 0.0 — nothing can be pledged — so a professionally managed company does not fail a pledge gate |
| `earnings_yield_ttm`, `ey_vs_own_5y_median` | `out_of_domain` during a valuation blackout (§5) |
| `ey_median_5y` | Median of stored `earnings_yield_ttm` over 1,250 sessions, excluding blackout sessions and sessions on or before the latest valuation-transformative action (§5); ≥ 750 known values, else `drop`. Never loosened to fill early history (§14) |
| `rel_strength_6m_vs_nifty200_tri` | (TR_stock(t−21) ÷ TR_stock(t−126)) − (TR_index(t−21) ÷ TR_index(t−126)); the skip month applies to both |
| `atr_pct_20`, volatility features | Strictly positive, with minimum session coverage |
| `earnings_yield_spread` | Decimal difference; 0.021 = 2.1 percentage points |

**Working-capital measures:** `opm_fy` = EBITDA ÷ revenue; `receivable_days_fy` = FY-end receivables ÷ FY revenue × 365; `inventory_days_fy` = FY-end inventory ÷ FY revenue × 365. The revenue base is used because COGS is not a canonical fact; the flags test changes in days, which largely cancels the choice of base.

**`persist(cond, n, unit)`:** TRUE if and only if `cond` is TRUE on the last *n* evaluable units; UNKNOWN if any of them is unknown; FALSE otherwise. Non-trading days are not units.

## 9. Cross-sectional scoring

The registry's `cross_sectional_scoring` block is normative and is inside every card's closure. Per feature, per evaluation date:

1. **Population:** the strategy universe on that date — market-eligible, minus the card's sector exclusions and the securities whose universe filters are FALSE (an UNKNOWN filter keeps a security in the population but not among the candidates), before gates.
2. **Contributors:** population members with `known` values.
3. **Minimum:** fewer than 30 contributors → the z-score is `missing` for all that day.
4. **Winsorise** at the 1st and 99th percentiles, computed with linear interpolation between order statistics (`numpy.quantile(method="linear")`, DuckDB `quantile_cont`).
5. **Standardise** with the population mean and standard deviation (divisor N) of the clipped values. Standard deviation = 0 → `missing` for all that day.
6. **Direction:** multiply by −1 for inputs the card declares `lower_better`.

A composite is the mean of a security's available directional z-scores, `missing` below `min_inputs_known`, and never re-standardised. **Ties:** scores within 1e-9 are ties, broken by higher market cap, then ISIN. Aggregations run in a fixed, declared order, recorded in the run manifest.

## 10. Universe ranking

**Population on D:** in-scope securities (§4) with a resolved close on D or within the prior 5 sessions, and a `shares_outstanding` value that is `known` or `conflicted`. Market cap uses the last resolved close on or before D, and records `price_age_sessions`; a stale-priced security may remain in the universe but cannot enter it.

Total shares are used, not free float, so this is the *point-in-time top-N market-cap universe* — never an index's constituent list.

**Coverage** = securities with usable share counts ÷ in-scope securities with a price. At 98% or more the run proceeds normally. Between 95% and 98%, data confidence drops one band and the gap is logged. Below 95%, the kill switch fires and nothing is published; backtests exclude and count such dates.

**N is fixed by policy, not by the implementer.** `policies/market_universe.yaml` (schema `market_universe_policy.schema.json`) is versioned and hashed into every run manifest. Version 1.0.0 sets **N = 500**, entry after 5 consecutive sessions inside the top 500, exit after 5 consecutive sessions outside the top 550. N materially changes which securities exist for every strategy, the cross-sectional scores and the signal counts, so it can never be left to an implementation choice.

## 11. Freshness, reconciliation and conflicts

**Freshness** (a value becomes `stale` after): daily, 5 sessions without a new row; quarterly, 165 days after `period_end`; half-yearly, 270 days; annual, 450 days; event data never goes stale.

**Tolerances** (validation vs primary; beyond → `conflicted`): close price, exact to the paisa; volume and traded value, 0.1%; statement lines, 0.5% or ₹1 crore, whichever is larger; share counts, 1%; promoter holding and pledge, 0.5 pp; corporate-action ratios, exact.

**Conflicts** are logged to `data_conflict` with both values, both sources, the tolerance breached and the first date affected. Resolution is manual, recorded with a reason, and creates a new version. For ranking only, a conflicted share count keeps its primary value.

## 12. Storage, snapshots and bootstrap

Partitioned Parquet with a `_manifest.json` per partition. There is no persistent database file.

**One pre-write validator for every codec.** Before any part is written, every row is checked against its table schema. Naive timestamps, unknown columns, floats where the schema says decimal and booleans where it says integer are refused, on Parquet exactly as on the JSONL test codec.

**Every logical write is one all-or-nothing batch.** One source file, for example, writes observations, conflicts, quarantined rows, coverage and its ingestion-log entry. The batch runs in three steps:

1. Its parts are staged: written to temporary files, fsynced and renamed, but listed by no manifest.
2. One batch record is written atomically. **This is the commit point.**
3. The manifests are updated idempotently, and an applied-marker is written.

A reader refuses to read while any committed batch is unapplied, and the next writer rolls such a batch forward. A part listed without a commit record is an integrity failure. All writes run under one warehouse lock, which spans reading the latest version, allocating the next one and committing, so no two writers can allocate the same version. A snapshot lists every manifest hash in use. The bootstrap script is generated from the snapshot and lists files explicitly — never globs — so no query reads a partition written after its snapshot. Old adjustment versions are kept until no snapshot references them.

## 13. Governance and forensic source contracts

Each hard governance input has a defined evidence universe, so "unknown" can be told apart from "searched and not found".

| Table | Contents | Source | Coverage rule |
| --- | --- | --- | --- |
| `auditor_event` | appointment, resignation (with stated reason), change type (`rotation` / `resignation` / `other`), effective date | Exchange disclosure of statutory-auditor changes (structured) | Complete for dates where the exchange disclosure archive is covered |
| `audit_opinion` | fiscal year, opinion type (`unmodified` / `qualified` / `adverse` / `disclaimer`), evidence reference | Independent auditor's report in the annual report | Extracted, then verified deterministically (the opinion paragraph heading matches the type) and confirmed by a human before becoming a fact; until confirmed, `missing` |
| `related_party_transaction` | period, counterparty, nature, value | Related-party disclosures filed with the exchange, and annual-report notes | Applicable only for periods where a disclosure exists |
| `promoter_holding` | filing date, promoter %, pledged % | Shareholding-pattern XBRL | Per filing |

`auditor_resignation_5y` reads `auditor_event`; `audit_qualification_5y` reads confirmed `audit_opinion` rows. **`audit_qualification_5y` is defined here but used by no v1 card**: it was removed from `ltqv_v1` because a material input may not be waived where data is missing, and it returns as a new card version once this table has coverage. Mandatory rotation is not churn. AI may propose `audit_opinion` extractions (Document 05); a proposal never becomes a fact without verification and confirmation.

## 14. History and warm-up

Every card declares `warm_up_years` (history needed before its features are in domain) and `evaluable_years` (the design period plus holdout). **Required raw history = warm-up + evaluable.** For `ltqv_v1` that is 7 + 9 = 16 years of fundamentals and prices; for `mom_v1`, 1 + 11 = 12 years of prices. A feature's domain is never loosened in early history to manufacture signals: that would make its meaning depend on when you look. A shortfall in purchased history is **not** absorbed silently. A card declaring 16 years cannot be promoted on 10: the declared window is a requirement, and shortening it is an explicit decision that changes the card — a new version, with the reason recorded in the lifecycle evidence.

## 15. Actual-portfolio ledger (M15)

| Table | Rule |
| --- | --- |
| `executed_trade` | Immutable. `trade_id` is the broker's ID; `idempotency_key` = hash(broker, trade_id, isin, side, qty, price, exec_ts). Carries execution and settlement dates, quantity, price, and charges by component |
| `trade_correction` | A broker correction is a new event referencing the original; the original stays |
| `cash_event` | Deposits, withdrawals, dividends, corporate-action cash, cash in lieu, charges, taxes; each with `effective_date` and `received_at` |
| `expected_cash_event` | Receipts the corporate-action policy expects (amount, ex-date, expected credit date). An actual credit matching an expectation closes it; timing differences never raise a break |
| `holding_snapshot` | Broker-reported holdings as of a timestamp; a validation source, never overwriting the ledger |
| `ledger_holding` | Derived from trades, corrections and CA events; the primary source for the allocator |
| `reconciliation_break` | Where snapshot and ledger differ: quantity, first date, state (`open` / `explained` / `resolved`), resolution note |
| `manual_holding` | Off-platform or pre-system positions, entered by the user and marked as such |
| `opportunity_execution` | Links a fill to claims with `allocated_qty`; allocations sum to the fill quantity |

Late imports carry their `received_at`, and the historical ledger state is reconstructed as of any timestamp. An open reconciliation break on a security marks its claims *valid but not currently actionable* until resolved.

## 16. Intraday data contract (reserved)

Registered now so the architecture carries it; not yet implemented.

- `price_intraday_bar(isin, ts, interval, ohlcv, trades, source, received_at)` — 1-minute bars as the minimum resolution.
- `quote_snapshot(isin, ts, best bid/ask, depth levels)`, where licensed.
- `intraday_band(isin, date, lower, upper, revisions)` and `session_state(date, phase, halts)`.
- An intraday-eligible universe that adds liquidity and data-coverage conditions to market-eligible.
- Intraday cost, impact and fill models belong to Document 04's intraday validation class.

No intraday card can pass `experimental` until these are implemented; the linter enforces this through `data_resolutions.implemented`.

## 17. Quality checks, Stage 0 acceptance and verification items

**Every ingestion:** OHLC ordering and ISIN validity per row (a failing row is quarantined, §6; the file is rejected above the quarantine limit); uniqueness of `(isin, trade_date, version_no)`; row count within ±5% of the prior day (kill switch below 90%); close-to-close moves beyond 3× the band with no corporate action flagged for review; adjusted-series continuity at ex-dates within ±25%, or 5× the 60-day median absolute return; the balance-sheet identity (assets = liabilities + owners' equity + NCI) within 1%; normalised quarters summing to FY within 0.5%; share-count reconciliation within 1%; allocations summing to fills; alias windows not overlapping; `usable_from ≥ filed_at` everywhere.

**Stage 0 acceptance:**

- The XBRL parser reproduces the canonical facts for 15–20 difficult securities, including reporting-duration normalisation.
- **The same three securities parse correctly in 2015, 2019 and 2024 filings.** Exchange XBRL taxonomies changed across releases (`in-gaap`, `ind-as-2016`, `ind-as-2019`) and tags move namespace or nesting between them; testing only current filings would hide that.
- Price-band file coverage is measured across the full history; uncovered periods are listed, since Document 04 excludes them from evidence rather than assuming they were benign.
- Restatement versioning is correct on at least three restated companies.
- Continuous series across a split, a bonus, a rights issue and a demerger, with the demerger stub valued.
- A price correction is resolved as-of correctly.
- The vendor bake-off (30–50 securities) confirms exchange-traceable timestamps and restatement history.
- The canary hard-fails.

**Verification items** — each becomes a confirmed fact or a documented limitation before Stage 0 closes:

- start dates of the ASM and GSM frameworks, and dated list coverage after them
- historical F&O eligibility files
- price-band files
- depth of delivery data
- rights-entitlement trading data from 2020
- the exchange auditor-change disclosure archive
- related-party disclosure filings
- whether exchange XBRL carries any structured forward guidance
- special pre-open session timing across history

## Appendix A — Registry

`registry.yaml` 3.0.0 in the spec kit is authoritative and is not reproduced here. Every entry carries its own version. It holds:

- **Features and functions:** 41 features and 8 forensic flags; 10 typed functions, with the date arguments of price functions restricted (`impact_cost` is `impact_model_v1`, Document 04 §5).
- **Normative blocks:** `evaluation_semantics`, `window_conventions`, `cross_sectional_scoring`, the two cutoff domains, the materiality list and the confidence policy.
- **Runtime identifiers:** 26, with owners and initialisation/update rules.
- **Enums:** 21, with literals always namespaced (`surveillance_stage.none`).
- **Classes and triggers:** 5 strategy classes, 5 data resolutions and 5 triggers.
- **Vocabularies:** 4 benchmarks, 29 sector codes and 2 sizing methods.
- **Events, identity and policy:** 4 void events with predicates and declared parameters; security identity; valuation-transformative actions; the corporate-action policy v3.
- **Retired identifiers:** 27.

To change it: edit the file and run `python3 speclint.py`. A card whose closure the edit touched fails with its new closure hash. Re-validate that card, version it if its meaning changed, re-pin it, and register the new version (`register_card.py`). Cards whose closure the edit did not touch are unaffected. Add a regression or golden case for whatever the change prevents.
