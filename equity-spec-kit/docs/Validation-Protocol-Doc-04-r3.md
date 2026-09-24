# Validation Protocol — Document 04 r3

*Release r5.4 · 24 September 2026 · governs how every backtest, shadow run and promotion is conducted*

## 1. Purpose and what counts as evidence

A backtest is evidence only if it was run under this protocol, and a strategy is promoted only on evidence. Nothing here changes a strategy's thresholds. It fixes how a strategy is simulated, costed, tested and judged, so that a result cannot be improved by choosing a friendlier simulation after seeing the numbers.

**A result counts as evidence only if all of these hold:**

1. It was produced by an engine that passes every golden case (§2).
2. Its run manifest is complete and immutable (Document 01 §13).
3. It used only design-period data, or it is the single sealed holdout evaluation (§7).
4. It is recorded in the append-only trial log, whatever its outcome (§8).
5. It applies the dated cost schedule and the fill model in this document, not a variant.

## 2. Golden cases

The golden cases are executable and live in the package:

| File | Role |
| --- | --- |
| `reference_sim.py` | Plain reference implementations of every rule this document fixes |
| `golden/golden_cases.yaml` | 75 synthetic cases, answers computed by hand before the reference ran |
| `test_golden.py` | Runs the cases; also plants 28 known defects and requires every one to be caught |

**Synthetic first.** Synthetic cases have answers known by construction, so they test the logic without depending on data quality. They cover: buy fills at and above the limit and at the upper band; exits at, after and without the lower band; the impact model; costs across dates; the tax view across three regimes, set-off, grandfathering and the holding-period boundary; the stop state machine including ties and post-peak calm; bonus, fractional-bonus, demerger and rights transforms; tranche arithmetic including exhaustion and a falling target; `persist`; winsorised z-scores including the minimum and zero-variance cases; ROCE with leases, cash-rich and negative equity; negative-over-negative cash conversion; tie-breaking; point-in-time reads, including the basis-filter trap; the look-ahead canary; and valuation blackouts.

**Teeth.** `test_golden.py` plants each defect found in review into the reference, one at a time: a single scalar cutoff for both data domains, a security target that sums claims, slots allocated by market cap, dividends spendable on the ex-date, quantities ignoring the hard cap, the exemption applied before loss set-off, sensitivity that demands a peak, basis substituted per date, a benign missing-band assumption, a stop not tested on the fill day, tie-updating peaks, current-ATR stops, post-join basis filters, cash in lieu at the cum price, tranches converted at the capped limit, fills at an upper-band open, a missing exemption, a missing set-off, unknown treated as false, nearest-rank winsorisation, sample standard deviation, negative-over-negative ratios, leases outside capital, cash-rich firms failing ROCE, stamp duty on sells, 12 months treated as long-term, no tie tolerance, and ignored lower-band locks. Every one must make a case fail. A mutant that survives is a gap in the fixtures, and must be closed with a new case before any backtest counts.

**Conformance.** M5, M6 and M14 must expose equivalent functions and pass the same file unmodified. A production engine that disagrees with the reference on any case is wrong until proven otherwise, and the resolution is recorded in the issue log.

**Real-data cases come next** (Stage 0 and 1). Each is chosen for a failure mode, not recognisability, and its expected values are computed by hand from the original filings and exchange files: a merger with a symbol change; a demerger with a discovery session and a later-listing stub; a split; a bonus with fractions; a rights issue with a listed entitlement and one from before 2020; a restated company; a company whose standalone and consolidated results were filed on different days; a price correction published after the fact; a trade-for-trade security; a surveillance entry; and a security that went suspended and then delisted. Each is added to the golden file with its source documents referenced by hash.

## 3. Execution model (M14)

All proposed executions are simulated at the open of `next_executable_session` after the evaluating run.

**Buys (pre-open limit orders).** No fill if the open is **at the upper band**: no sellers can be assumed, whatever the limit. This is tested on the open price against the band — the closing band state is unknown at the open, and using it would be look-ahead. Otherwise the order fills at the open if the open is at or below the limit, and does not fill if it is above. Fills are all-or-nothing at the proposed quantity; partial fills are not modelled in v1, a limitation offset by the participation cap (≤ 10% of average traded value) and the impact charge. Impact is charged as an explicit cost (§5), never by moving the fill price, so the limit's meaning is preserved.

**Exits (market on open).**

| Situation | Simulated fill |
| --- | --- |
| Open above the lower band | The open |
| Open at the lower band | No fill; retry at each following open |
| First unlocked open after *k* locked sessions | Open × (1 − 1% × *k*), haircut capped at 5% |
| Band file missing for the session | Open × (1 − 2%), plus any accumulated lock haircut |

The per-session haircut stands in for queue position when a locked stock reopens. It is an assumption, stress-tested at 0% and 2% per session (§9). The missing-band haircut is 2% rather than a token amount because band data is most likely missing exactly when a security was locked; periods without band coverage are additionally excluded from evidence (§16).

**Suspension and delisting.** A held security that is suspended is marked at its last close and cannot be sold. If it delists with a successor, the corporate-action policy applies. If it delists without a successor or cash consideration, it is marked to zero on the delisting date. Recovering value later is not assumed.

**Corporate actions** follow `standard_equity_ca_policy_v2` (Document 02 §5).

- **Rights entitlements** are sold at the entitlement's traded close on its last trading session where one was listed (2020 onward), else at intrinsic value.
- **Demerger stubs** are carried at implied value, and exited at the open of the resulting entity's first executable session after listing.
- **Merger targets** whose successor fails the strategy are exited at the open of the last announced trading session.
- **Fractional entitlements** are paid as cash at the post-action price.

Buybacks are not tendered into.

**Model portfolios.** Each strategy runs on its card's notional capital, sized by its card, with no cross-strategy netting. Cash earns nothing in v1, a conservative simplification.

**Cash has two dates.** Dividends and corporate-action cash accrue to return on the ex-date, but become **spendable only on the payment date**. Crediting spendable cash on the ex-date would let the simulator buy with money it did not yet have.

**Size versus fill.** Quantity is derived from the reference price, then capped so that a fill at the highest permitted price still cannot breach the hard position limit — and, for stop-risk sizing, cannot exceed the risk budget. A higher allowed fill reduces quantity rather than silently enlarging the position or the risk.

## 4. Cost model

`schedules/costs_india_equity_delivery.yaml` is effective-dated: every trade uses the rates in force on its date. Components are STT, stamp duty, the NSE exchange charge, the SEBI fee, GST on brokerage plus exchange and SEBI charges, brokerage by broker profile, and a depository charge per sell. Each component is rounded to the paisa, as on a contract note.

| Component | Current rate | Status |
| --- | --- | --- |
| STT, delivery | 0.1% buy and 0.1% sell | Verified — Budget 2026 changed derivatives STT only, effective 1 April 2026 |
| Stamp duty | 0.015%, buy side only | Confirm against a contract note |
| NSE exchange charge | 0.00297% | Confirm against a contract note — sources cite 0.00297%–0.00325% |
| SEBI turnover fee | ₹10 per crore | Verified |
| GST | 18% on brokerage + exchange + SEBI | Verified |
| Brokerage | Profile: `flat_20` (₹20 per order, default) or `zero_delivery` | Your broker's actual profile to be set |
| DP charge | ₹13.50 + GST per sell per scrip-day | Broker-specific |

Rates before July 2020 (stamp duty) and before June 2013 (STT) are historical estimates to be confirmed at Stage 0. Their effect on multi-year results is small, but they are recorded as estimates rather than presented as facts. Before any shadow run, one of your actual contract notes is reconciled against the model to the paisa.

## 5. Impact model — `impact_model_v1`

```text
impact_cost(value_cr, adv_cr) = half_spread(adv_cr) + 0.02 × sqrt(value_cr / adv_cr)
half_spread: ADV ≥ ₹100 cr → 0.05%;  ≥ ₹25 cr → 0.10%;  otherwise 0.20%
```

The square-root term is the standard form of market impact. The coefficient 0.02 corresponds to roughly 2% daily volatility with a unit coefficient. Impact is charged on both entry and exit, and is what momentum's S1 check (≤ 0.35%) tests. It is a v1 assumption to be calibrated in shadow, by comparing modelled impact with realised slippage on actual fills, and it is stress-tested at 2× (§9).

## 6. Tax view

`schedules/tax_india_listed_equity.yaml` applies the regime in force on each **sale date**, with FIFO lot matching. Long-term means held for more than 12 months: exactly 12 months is still short-term.

| Sale date | Short-term | Long-term |
| --- | --- | --- |
| to 31 Mar 2018 | 15% | exempt |
| 1 Apr 2018 – 22 Jul 2024 | 15% | 10% above ₹1 lakh per FY; pre-Feb-2018 holdings grandfathered |
| from 23 Jul 2024 | 20% | 12.5% above ₹1.25 lakh per FY — unchanged by Budget 2026; the Income Tax Act 2025, in force from 1 Apr 2026, renumbers sections only |

Short-term losses set off against short- and long-term gains; long-term losses against long-term only; eight-year carry-forward. STT is not deductible. Cess at 4% is a view parameter; surcharge depends on your income and stays OPEN.

**Multi-year losses.** Losses carry forward by vintage and by kind, and each vintage lapses after eight years. A loss from FY *y* is usable in FY *y*+1 to *y*+8. Brought-forward losses are applied oldest first: short-term losses against short-term and then long-term gains, long-term losses against long-term gains only. A short-term loss stays short-term when carried. The reference implements this across years; golden cases G28c–e fix the lapse, the last usable year and the carried short-term loss.

**The straddle year.** FY 2024-25 contains sales under both regimes. Each sale is taxed at the rate in force on **its own date**; the FY exemption is the one in force at the financial year's end, applied once to the net long-term gain and shared pro-rata across regime buckets. Confirmation of this treatment remains a Stage 0 item.

**The tax view never gates.** Promotion is judged after costs (§12). The after-tax result is reported beside it as your deployment view. A long-term *strategy* exit inside 12 months is short-term for tax, and the view shows that plainly. The treatment of FY 2024-25, which straddles the July 2024 change, is flagged for confirmation at Stage 0.

## 7. Data windows, warm-up and the sealed holdout

Each card declares `warm_up_years`, `evaluable_years` and `holdout_years` (Document 02 §14).

- **Warm-up** produces no signals and is never evaluated.
- **The design period** is the evaluable span minus the holdout.
- **The holdout** is the most recent `holdout_years`.

**Holdout exposure is tracked per lineage, not per version.** `schemas/holdout_ledger.schema.json` is an append-only record, one per strategy lineage (`ltqv`, `mom`). Every design evaluation and every sealed evaluation appends the date range it touched. Once a range has been exposed to research for a lineage, it is permanently design-known **for every descendant card**. A card that fails its holdout and is then revised cannot reuse those years as if they were unseen: its descendant needs genuinely later data, which in practice means the shadow period. Without this, "one sealed evaluation per card version" would be defeated by renaming the version.

**The holdout is sealed.** Any run whose manifest has `holdout_access: none` cannot read holdout dates; M5 refuses them. Exactly one run per card version may carry `holdout_access: sealed_evaluation`, and it is recorded in the lifecycle evidence. A second holdout run for the same card version is invalid. Changing a card after seeing its holdout result makes it a new version, which needs fresh holdout data — in practice, a shadow period.

**Calibration** (for example momentum's delivery bands) runs once, on design data only, at the quantile the card pre-registers, and is recorded in the trial log with its inputs. The result is written into the card, making a new version before testing begins.

**Walk-forward means evaluation, not refitting.** The v1 cards have no parameters fitted during evaluation. Walk-forward reports performance in consecutive out-of-time segments with parameters frozen. Any future card that refits must freeze its refitting algorithm before the holdout, and must declare it in the card.

## 8. Trial log

`trial_log` is append-only. Every simulation run is recorded: parameters, card hash, manifest ID, headline results, and whether it was a stress variant, sensitivity point, calibration, design evaluation or the holdout evaluation. Failed and abandoned runs are recorded too. The count of design trials per card is reported with every promotion decision, so a result that is the best of many attempts is visible as such. Nothing in the log is deleted or edited.

## 9. Stress and sensitivity

Every candidate for promotion reports these alongside its base result. They are reported, never selected on.

| Stress | Base | Variants | Required |
| --- | --- | --- | --- |
| Costs | 1× schedule | 2× | Alpha remains positive at 2× (momentum) |
| Impact | model | 2× | Momentum survives |
| Entry delay | next open | +1 session | Degradation reported; no sign flip for long-term |
| Lower-band haircut | 1% per session | 0%, 2% | Reported |
| Missing data | none | 5% of feature values set missing at random | No crash; degradation reported |
| Stop variant (momentum) | peak-ATR trail | current-ATR Chandelier; trail from close | Discrete alternatives; reported |

**Threshold sensitivity is set by strategy class, never a blanket percentage.** For `ltqv_v1`:

- ROCE gate at 12%, 15% and 18%
- Cash conversion at 0.6, 0.7 and 0.8
- Valuation gate at 0.9, 1.0 and 1.1 of the median

For `mom_v1`:

- Volatility-adjusted momentum at 0.4, 0.6 and 0.8
- Relative strength at 0%, 5% and 10%
- Delivery quantile at 0.20, 0.25 and 0.30

Categorical rules are tested by discrete alternatives, not percentages.

**Acceptable shape — a broad stable region, not a peak.** A pre-registered threshold has no reason to sit at the empirical optimum, and requiring it to would reward fitting. The test is that, across the grid around the chosen value:

- every neighbouring point has the **same sign** as the chosen one (no cliff),
- no neighbour falls below **half** the chosen point's value (no cliff),
- and the chosen point is **no more than 1.5×** the mean of its neighbours (no isolated spike).

A chosen value that is *worse* than its neighbours passes: that is evidence of pre-registration, not of a problem. `reference_sim.sensitivity_ok` implements this and golden case G30d fixes it.

## 10. Attribution and decomposition

**Brinson–Fachler**, per period, against the benchmark's sector weights:

```text
allocation  = Σ_s (w_p,s − w_b,s) × (R_b,s − R_b)
selection   = Σ_s  w_b,s × (R_p,s − R_b,s)
interaction = Σ_s (w_p,s − w_b,s) × (R_p,s − R_b,s)
```

Sectors use `sector_map` at each date. For `ltqv_v1`, whose exclusions remove about ten sectors, **selection must be positive over the evaluable period**. Outperformance that comes only from allocation — from simply not owning banks through a credit cycle — is not strategy skill.

**Factor decomposition:** each strategy's returns are regressed on the relevant published NSE factor index TRIs and the Nifty 500 TRI. The residual alpha, and the share of variance explained, are reported. If a strategy is largely reproducible by an index, buying the index is the better decision, and the report says so.

**Benchmark provenance:** every benchmark series is the published TRI from NSE Indices, stored with its source and retrieval date. Index levels are never reconstructed from constituents.

## 11. Metric definitions

Innocuous-looking choices here decide promotions, so each is fixed and has a golden case.

| Metric | Definition |
| --- | --- |
| Monthly excess return | Strategy monthly return minus the benchmark TRI's monthly return, both after costs |
| **Alpha (annualised)** | Arithmetic mean of monthly excess returns × 12. Not a regression intercept, not a CAGR difference |
| **Sharpe (annualised)** | Mean monthly return in excess of the 91-day T-bill ÷ its **sample** standard deviation (divisor n−1) × √12 |
| **Standard error** | Newey–West with Bartlett weights on the monthly series, lag 6 for acceptance tests: `γ₀ + 2Σ(1 − j/(L+1))γⱼ`, over n. Returns are autocorrelated, so a naive standard error would overstate precision |
| **Turnover (annual)** | Total traded value ÷ 2 ÷ average portfolio value ÷ years |
| **Rolling windows** | 36-month windows stepped monthly, each weighted equally; the reported figure is the share with positive alpha |
| **Drawdown** | Peak-to-trough of the daily model-portfolio value series, after costs |
| **Selection effect** | Brinson–Fachler selection term (§10), summed over the evaluable period |

**Implementation status.** `reference_sim` implements alpha, Sharpe, the Newey–West standard error and turnover, fixed by golden cases G29a–d. **Drawdown and the Brinson–Fachler selection effect are not yet implemented, and nor is the rolling-window share as defined above.** Cash's treatment in attribution is also not yet defined: whether it is a segment, with what benchmark weight and return, and to what reconciliation tolerance. All of these must exist, each with hand-worked golden cases, before the first calibration or backtest run (Document 01 §17). Until then no promotion criterion that uses them can be evaluated.

## 12. Acceptance by validation class

| Class | Required for experimental → shadow |
| --- | --- |
| `fundamental` (`ltqv_v1`) | All golden cases pass. Alpha after costs versus the primary benchmark is positive over the design period **and** in the sealed holdout. Positive in at least 60% of rolling 3-year windows. Positive Brinson selection. Maximum drawdown no worse than the benchmark's plus 5 percentage points. Annual turnover below 40%. Smooth sensitivity. Positions open at holdout end marked and reported separately |
| `technical_eod` (`mom_v1`) | All golden cases pass. Alpha after costs versus the benchmark positive in design and holdout. Sharpe above the benchmark's. Survives 2× costs and 2× impact. Survives the lower-band model. Smooth sensitivity |
| `event` | Reserved: requires verified-fact event inputs (Document 05) and an event-time evaluation design before any card is accepted |
| `intraday` | Reserved: requires the intraday data contract (Document 02 §16), quote-based fills, intraday statutory charges (STT 0.025% on sells for intraday equity, among others, confirmed at drafting), and session-state simulation |

**Shadow → production:**

- A shadow period declared in advance: 12 months or 20 closed claims for `fundamental`, whichever is later; 6 months or 30 closed claims for `technical_eod`.
- Shadow results within the backtest's expected range — each measure within two standard errors of its backtest estimate.
- Realised execution slippage on any real fills within 1.5× the modelled costs plus impact.
- No unexplained data or pipeline faults.

**Retirement tests** run on each card's declared metric, window, threshold and minimum sample, on a rolling basis. A breach suspends the strategy pending review. It is never auto-retired and never auto-tuned.

## 13. Expected signal frequency

Every validation report includes the distribution of qualifying signals per month over the design period, split by market regime. Regimes are market-breadth terciles and the Nifty 500 TRI's 12-month return sign; they are used for reporting only, never for signals. This tells you in advance how long a silence is normal: if `ltqv_v1` historically went eight months without a signal in strong markets, a seven-month silence is expected, not a fault.

## 14. Policy lag calibration

Once three months of live runs exist, the distribution of `system_available_at − filed_at` is measured per source type. `policy_lag` is set to its 95th percentile, rounded up to the next 15 minutes. It is recorded as a new policy-lag version, and inferred historical availability is re-derived under it. Results are rerun and compared; a strategy whose results depend materially on the lag is flagged. The same applies to each source's inferred backfill time (Document 02 §3), which is set per source in `policies/source_policy.yaml`. Every validation report states the share of price and delivery observations whose availability is inferred rather than observed, and results are rerun with each inferred time moved later to show how much they depend on it.

## 15. The validation report

Every promotion candidate produces one report, hashed and referenced by its lifecycle transition. It contains:

- the card version and hash
- all run manifest IDs
- golden-case and linter results
- the trial count
- design and holdout results after costs, with the after-tax view beside them
- rolling-window results, stress table, sensitivity grids, attribution and decomposition
- the expected signal frequency
- censoring notes
- every assumption from this document that remains unconfirmed

## 16. Coverage gaps are excluded from evidence

A period in which a **material** input has no source coverage does not produce evidence. It is excluded from the evaluable period, and the exclusion is reported with its dates and cause. This is what prevents a strategy from quietly becoming a different strategy through history: momentum without delivery data is not momentum, and a long-term strategy without governance data is not the one described in the card.

Consequences, stated so they cannot be traded away:

- Excluded periods shorten the evaluable window. If that takes it below the card's declared `evaluable_years`, the card cannot be promoted until either the data is obtained or the card is re-declared as a new version (Document 02 §14).
- Secondary inputs behave differently: their absence lowers data confidence through `penalise`, and the period still counts.
- Price-band and surveillance coverage gaps are treated the same way, since both change simulated exits.

## 17. Items to confirm at Stage 0

- The current NSE exchange charge, and stamp-duty sides, from an actual contract note
- STT and stamp duty history before 2013 and 2020
- The tax treatment of FY 2024-25, the straddle year
- Your broker profile, and its DP charge
- The availability of rights-entitlement price history from 2020
- The lower-band haircut assumption, compared against observed reopening behaviour on locked stocks
- The FY 2024-25 straddle treatment, against a filed return or professional advice
- Ind AS adoption dates per company, and whether `ltqv_v1`'s evaluable window should begin after the transition
