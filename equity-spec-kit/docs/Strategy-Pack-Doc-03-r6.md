# Strategy Pack — Document 03 r6

*Release r5.2 · 21 September 2026 · current state only · card sections generated from `strategies/*.yaml` by `render_cards.py` · cards pinned to registry 2.2.0*

## 1. How strategies work

A strategy is an independent method of detecting an opportunity. It is not a category a company belongs to, and not a pot your capital is split into. Each strategy is one YAML card: hypothesis, data, triggers, gates, optional ranking, sizing on notional capital, a proposed execution rule, exits, expiry, benchmark, and retirement rule.

**The YAML is the only executable source of a strategy.** The card sections in §7 are generated from it, each stamped with the card's SHA-256, and `render_cards.py --check` fails the build if this document and the YAML ever differ. The prose below explains the strategies; where it and a card disagree, the card governs.

Every card pins the registry it was compiled against by version and hash. A registry change that touches a card forces it to be re-linted and re-validated.

**Both current strategies are `experimental`:** they may be backtested, and they may not reach your feed. Every threshold below is a pre-registered hypothesis. Once formal testing begins, thresholds are frozen; any change is a version bump with a logged reason, including changes prompted by disappointing results.

## 2. Why these two first

The first two strategies are reference implementations chosen to prove the platform, not to define the product. Long-term quality/value exercises point-in-time fundamentals, restatements, reporting durations and corporate-action comparability. Momentum exercises daily market data, technical state, stops, circuits and trading frictions. Between them they cover both of the platform's EOD data paths.

Registered strategy classes waiting for cards: **swing** (shorter-horizon technical logic), **event/catalyst** (disclosure-triggered evaluation using verified filing facts), and **intraday** (reserved until the intraday data contract in Document 02 §16 is implemented). Each will be added as a card and taken through the lifecycle. No platform change is needed.

## 3. `ltqv_v1` — long-term quality/value

**Hypothesis.** Businesses earning high, stable returns on capital, converting profit to cash, with low financial and governance risk, compound faster than the market expects. Buying when they trade below their *own* historical valuation captures that without paying for current enthusiasm.

**How it decides.**

| Gate | Tests | Unknown |
| --- | --- | --- |
| G1 | At least 7 years of complete financials | blocks |
| G2 | 3-year average ROCE ≥ 15% | blocks |
| G3 | 3-year cash from operations ÷ profit ≥ 0.70 | blocks |
| G4 | Interest coverage ≥ 2.5, and either debt/equity ≤ 1.0 or coverage ≥ 6 | blocks |
| G5 | Promoter pledge ≤ 15% | blocks |
| G6 | No statutory-auditor resignation in 5 years | blocks |
| G7 | At most one forensic flag, with ≥ 75% of applicable flags evaluable | blocks |
| G8 | Not under exchange surveillance | blocks |
| G9 | Earnings yield positive and at or above its own 5-year median | blocks |

Ranking weights: 50% quality, 30% value, 20% consistency — each a composite of directional z-scores over the full strategy universe, computed before gating.

**Definitions that matter** (Document 02 governs):

- ROCE uses underlying EBIT over average capital employed, **including lease liabilities**, so returns are measured consistently before and after Ind AS 116.
- A cash-rich business whose capital employed has shrunk below 5% of assets gets a capped ROCE of 1.00 and passes G2, rather than failing it. Negative equity fails.
- Valuation is blacked out after demergers, rights issues and capital reductions until comparable financials exist, so a demerger cannot make a stock look falsely cheap.
- The five-year earnings-yield median covers only the continuing business.
- **The audit-opinion gate has been removed from v1, not softened.** It previously waived wherever opinion data was missing — which, across a backtest, would have validated a strategy *without* that check while the card claimed to have one. A material input may not be waived, so the gate returns as a new card version once the extraction path in Document 02 §13 exists and has coverage. Auditor *resignations*, which come from structured exchange disclosures, remain a blocking gate.
- Forensic flags fire on the numbers alone. Dilution is measured on an issuance-neutral share count, so a bonus issue is never mistaken for dilution.

**Entry.** Three tranches of one third each. Quantities convert at the prior session's close, with the limit only as a price cap — and are additionally capped so that even a fill at the highest permitted price cannot breach the hard position limit. Tranche 1 re-evaluates every gate on every attempt, for up to 30 sessions, and voids the signal if any gate fails. Tranches 2 and 3 start 21 and 42 sessions after tranche 1 and retry for 10 sessions each. A failed recheck skips that session. When retries run out, the remaining tranches are cancelled and the holding is kept. The final tranche takes the remainder, so no shares are stranded by rounding.

**Exits:**

- ROCE below 12% for two consecutive half-years
- Cash conversion below 0.50
- Valuation stretched with a declining ROCE trend
- Pledge above 25% or any auditor event
- Serious surveillance

A 60-session cooldown follows any exit.

**History.** 7 warm-up years (the 7-year operating history and 5-year windows need them) plus 9 evaluable years, of which 3 are holdout: 16 years of history in total.

## 4. `mom_v1` — momentum

**Hypothesis.** Cross-sectional relative strength persists over 3–12 months because information diffuses slowly. Volatility scaling separates persistent trend from noise, and skipping the latest month avoids short-term reversal. In Indian mid-caps, illiquidity and circuits contaminate the effect, so liquidity gating is part of the signal.

**Triggers.** New entries are evaluated at Friday's close. Exits are evaluated every session.

**Gates:**

- 20-day traded value ≥ ₹25 crore
- Price above both its 50- and 200-day averages
- Positive 12-month return after skipping the latest month
- Volatility-adjusted 12-month momentum ≥ 0.60
- 6-month relative strength ≥ 5 points above the Nifty 200 TRI, skip month applied to both sides
- Delivery percentage above an F&O-dependent band — **blocking when delivery data is unavailable**, because delivery is part of the hypothesis. A period without delivery coverage produces no momentum signals rather than a quietly different strategy
- No surveillance

After provisional sizing, two further checks apply: estimated impact cost ≤ 0.35% and participation ≤ 10% of average traded value.

**Delivery bands, pre-registered.** Each band is the **25th percentile** of 20-day delivery percentage over the design period only. It is computed separately for F&O-eligible and non-F&O names, using point-in-time eligibility, and never from the holdout. The quantile is fixed now, before any data is examined, so the choice cannot be fitted.

**Sizing.** Quantity is the smallest of three: the target value at the reference price, the hard position cap at the highest permitted fill price, and the stop-risk budget at that same worst-case fill. The risk taken can therefore never exceed the budget because the fill came in higher than the reference.

**Stop.** The initial stop is 2.5 × the ATR percentage below the entry basis, and is tested from the fill session onward. It then trails 2.5 × the ATR-at-peak percentage below the highest close since entry. ATR is frozen at the moment each new high is set, so post-breakout calm cannot drag the stop upward. The stop is tested against the previous session's value before it updates. It never moves down. All price levels are adjusted on corporate-action ex-dates.

**Other exits:**

- Three sessions below the 50-day average
- Weekly volatility-adjusted momentum below 0.30
- 180 sessions held
- Serious surveillance

A 20-session cooldown follows every exit, including the time exit.

**History.** 1 warm-up year plus 11 evaluable years, of which 3 are holdout: 12 years of price history.

## 5. Acceptance: economic validity versus your deployment view

Two different questions, deliberately kept apart:

1. **Does the strategy work?** Judged after implementable costs, including brokerage, statutory charges, spread, impact and circuit-aware fills, against the card's total-return benchmark. This decides promotion.
2. **Is it worth deploying for you?** The same results viewed after your configurable tax treatment and portfolio policy. This informs your choices and never changes whether the strategy is valid.

A strategy does not become statistically invalid because tax rules change. It may become unattractive for you, and the system shows that separately.

**Per-strategy economic tests.** Document 04 fixes the exact statistics.

- **`ltqv_v1`:**
  - Positive alpha after costs versus Nifty 500 TRI over the evaluable period, and in most rolling 3-year windows.
  - Positive alpha versus Nifty 200 Quality 30 TRI.
  - **Positive selection effect in a Brinson–Fachler attribution.** The strategy excludes about ten sectors, so allocation effects alone must not count as skill.
  - Drawdown no worse than the benchmark's; turnover consistent with a multi-year hypothesis.
  - Positions still open at holdout end are marked and reported separately.
- **`mom_v1`:**
  - Positive alpha after costs versus Nifty 200 Momentum 30 TRI.
  - Sharpe above the benchmark's.
  - Survives the circuit-aware exit model and doubled impact costs.
  - Turnover realistic at intended size.

**Decomposition** against published factor indices is reported for both. If a strategy can be reproduced as an index plus a tilt, buying the index is the better decision.

## 6. Values only you can set

These stay `OPEN` until you set them, and a card cannot pass `experimental` while any remain:

- **In each card's sizing block:** notional capital, the target volatility contribution or risk to the stop, and maximum position size. Notional capital only sizes the strategy's model portfolio for measurement.
- **In `portfolio_policy.yaml`:** your total capital; your caps per stock, sector, promoter group and position count; your drawdown limit and response; your cash floor. The per-strategy cap defaults to `NONE`: there are no capital buckets unless you choose them.

Set these from your own circumstances, never from backtest results.

## 7. Generated cards

The sections below are generated by `render_cards.py` from `strategies/*.yaml`, and parity is checked in CI. Do not edit them here.

<!-- generated from strategies/ltqv_v1.yaml sha256:c74f074262d4b9b4c49b0609e28e9114fe1b6b09dcf72e139098660a049faa00 -->
```yaml
schema_version: 5
code: ltqv_v1
strategy_class: fundamental_long_term
version: 1.0.0-prevalidation.7
lineage: ltqv
status: experimental
registry: {version: 2.2.0, sha256: 2d531e2a71aee5c9ed9e00c4ac9534dddb4c7d25b4703e3b2b505483087aa128}

hypothesis: >
  Businesses that earn high and stable returns on capital, convert profits
  into cash, and carry low financial and governance risk tend to compound
  book value faster than the market expects. Buying them when they trade
  below their own historical valuation - rather than below a fixed multiple -
  captures that compounding without paying for current enthusiasm.

trade_direction: long
horizon: years
data_resolution: eod_filings
evaluation:
  entry_triggers: [{trigger: daily_eod}, {trigger: on_filing}]
  risk_trigger: {trigger: daily_eod}
selection_method: rank_and_gate

universe:
  base: market_eligible
  exclude_sectors: [banks, nbfc, insurance, capital_markets, metals_mining, cement,
                    commodity_chemicals, sugar, oil_gas_upstream, shipping]
  filters: []

features:
  - operating_history_years
  - roce_3y_avg
  - roce_hy_ttm
  - roce_5y_trend
  - roce_stability
  - cfo_pat_3y
  - debt_equity
  - interest_coverage
  - positive_revenue_growth_years_5y
  - exceptional_frequency
  - market_cap
  - earnings_yield_ttm
  - ey_median_5y
  - ey_vs_own_5y_median
  - ev_ebitda_vs_sector
  - earnings_yield_spread
  - realised_vol_1y
  - promoter_pledge_pct
  - auditor_resignation_5y
  - forensic_flag_count
  - forensic_coverage_pct
  - surveillance_stage

unknown_overrides:
  roce_stability: penalise
  positive_revenue_growth_years_5y: penalise
  exceptional_frequency: penalise
  ev_ebitda_vs_sector: penalise
  earnings_yield_spread: penalise
  promoter_pledge_pct: fail
  auditor_resignation_5y: fail
  forensic_flag_count: fail
  forensic_coverage_pct: fail
  surveillance_stage: fail

params: {}

composites:
  quality_composite:
    inputs:
      - {code: roce_3y_avg,       direction: higher_better}
      - {code: roce_5y_trend,     direction: higher_better}
      - {code: cfo_pat_3y,        direction: higher_better}
      - {code: debt_equity,       direction: lower_better}
      - {code: interest_coverage, direction: higher_better}
    min_inputs_known: 4
  value_composite:
    inputs:
      - {code: ey_vs_own_5y_median,   direction: higher_better}
      - {code: ev_ebitda_vs_sector,   direction: lower_better}
      - {code: earnings_yield_spread, direction: higher_better}
    min_inputs_known: 2
  consistency_composite:
    inputs:
      - {code: roce_stability,                   direction: higher_better}
      - {code: positive_revenue_growth_years_5y, direction: higher_better}
      - {code: exceptional_frequency,            direction: lower_better}
    min_inputs_known: 2

gates:
  - {code: G1,  expr: "operating_history_years >= 7", unknown_blocks: true}
  - {code: G2,  expr: "roce_3y_avg >= 0.15", unknown_blocks: true}
  - {code: G3,  expr: "cfo_pat_3y >= 0.70", unknown_blocks: true}
  - {code: G4,  expr: "interest_coverage >= 2.5 AND (debt_equity <= 1.0 OR interest_coverage >= 6)", unknown_blocks: true}
  - {code: G5,  expr: "promoter_pledge_pct <= 0.15", unknown_blocks: true}
  - {code: G6,  expr: "auditor_resignation_5y == false", unknown_blocks: true}
  - {code: G7,  expr: "forensic_flag_count <= 1 AND forensic_coverage_pct >= 0.75", unknown_blocks: true}
  - {code: G8,  expr: "surveillance_stage == surveillance_stage.none", unknown_blocks: true}
  - {code: G9,  expr: "earnings_yield_ttm > 0 AND ey_median_5y > 0 AND ey_vs_own_5y_median >= 1.0", unknown_blocks: true}

size_dependent_checks: []

ranking:
  expr: "0.50 * quality_composite + 0.30 * value_composite + 0.20 * consistency_composite"

lifecycle:
  signal_ttl: {value: 30, unit: trading_sessions}

sizing:
  method: target_volatility_contribution
  params: {notional_capital: OPEN, target_vol_contribution: OPEN, max_position_pct: OPEN}
  formula: "min(notional_capital * target_vol_contribution / realised_vol_1y, notional_capital * max_position_pct)"
  revised_formula: "min(notional_capital * target_vol_contribution / realised_vol_1y, notional_capital * max_position_pct)"

proposed_execution_rule:
  scope: simulation_and_plan_only
  entry_ref: "close_raw(signal_date)"
  entry_high: "entry_ref * 1.05"
  target_qty: "min(floor(target_value / entry_ref), floor(hard_cap_value / entry_high))"
  revised_target_qty: "min(floor(revised_target_value / close_raw(prev_session(eval_date))), floor(hard_cap_value / tranche_limit))"
  tranches:
    - n: 1
      weight: 0.3334
      limit: "entry_high"
      qty: "floor(tranche_weight * target_qty)"
      attempt_policy: every_session_until_ttl
      recheck_gates: [G1, G2, G3, G4, G5, G6, G7, G8, G9]
      recheck_failure: void_signal
    - n: 2
      weight: 0.3333
      limit: "entry_high * 1.15"
      qty: "max(0, min(floor(tranche_weight * revised_target_qty), revised_target_qty - current_earmark_qty))"
      attempt_policy: retry_window
      first_attempt_sessions_after_tranche_1: 21
      retry_sessions: 10
      recheck_gates: [G1, G2, G3, G4, G5, G6, G7, G8]
      recheck_failure: skip_attempt
    - n: 3
      weight: 0.3333
      limit: "entry_high * 1.15"
      qty: "max(0, revised_target_qty - current_earmark_qty)"
      attempt_policy: retry_window
      first_attempt_sessions_after_tranche_1: 42
      retry_sessions: 10
      recheck_gates: [G1, G2, G3, G4, G5, G6, G7, G8]
      recheck_failure: skip_attempt
  on_exhausted: cancel_release_keep_holding
  exit_execution: open_next_executable_session

exit_rules:
  - {code: X1, cadence: daily, expr: "persist(roce_hy_ttm < 0.12, 2, persist_unit.half_year)"}
  - {code: X2, cadence: daily, expr: "cfo_pat_3y < 0.50"}
  - {code: X3, cadence: daily, expr: "ey_vs_own_5y_median <= 0.57 AND roce_5y_trend <= 0"}
  - {code: X4, cadence: daily, expr: "promoter_pledge_pct > 0.25 OR auditor_resignation_5y == true"}
  - {code: X5, cadence: daily, expr: "surveillance_stage == surveillance_stage.asm_lt_2plus OR surveillance_stage == surveillance_stage.asm_st_2plus OR surveillance_stage == surveillance_stage.gsm_any"}

cooldown:
  trading_days: 60
  applies_after: [X1, X2, X3, X4, X5]

review_triggers:
  - "earnings_yield_ttm <= 0"
  - "forensic_flag_count >= 1"

corporate_action_policy: standard_equity_ca_policy_v2
ca_state_held: [entry_ref, entry_high, tranche_limit, target_qty, revised_target_qty, current_earmark_qty]
signal_void_on: [governance_event, surveillance_entry, transformative_ca]

benchmark: NIFTY_500_TRI
secondary_benchmark: NIFTY_200_QUALITY_30_TRI

ai_inputs: {permitted: false}

validation:
  protocol: document_04
  warm_up_years: 7
  evaluable_years: 9
  holdout_years: 3

retirement:
  min_closed_positions: 20
  min_years: 3
  metric: rolling_alpha_vs_secondary_benchmark_after_costs
  window_years: 3
  threshold: 0.0
```

<!-- generated from strategies/mom_v1.yaml sha256:92dd0e06fbb7d71c7911289ccb6667edb4d027a9c1e9930a3289ed16ad0e635e -->
```yaml
schema_version: 5
code: mom_v1
strategy_class: momentum
version: 1.0.0-prevalidation.7
lineage: mom
status: experimental
registry: {version: 2.2.0, sha256: 2d531e2a71aee5c9ed9e00c4ac9534dddb4c7d25b4703e3b2b505483087aa128}

hypothesis: >
  Cross-sectional relative strength persists over 3 to 12 month horizons
  because information diffuses slowly and investors under-react to it.
  Scaling by realised volatility separates persistent trend from noise, and
  skipping the most recent month avoids short-term reversal. In Indian
  mid-caps the effect is contaminated by illiquidity and circuit halts, so
  liquidity gating is part of the signal rather than a risk overlay.

trade_direction: long
horizon: weeks
data_resolution: eod
evaluation:
  entry_triggers: [{trigger: weekly_eod, weekday: fri}]
  risk_trigger: {trigger: daily_eod}
selection_method: rank_and_gate

universe:
  base: market_eligible
  exclude_sectors: []
  filters: ["circuit_days_60d <= 5"]

features:
  - ret_12m_skip_1m
  - ret_6m_skip_1m
  - realised_vol_60d
  - vol_adj_mom_12m
  - vol_adj_mom_6m
  - rel_strength_6m_vs_nifty200_tri
  - adv_20d_cr
  - delivery_pct_20d_avg
  - is_fno_eligible
  - price_vs_dma50
  - price_vs_dma200
  - atr_pct_20
  - circuit_days_60d
  - surveillance_stage
  - market_breadth

unknown_overrides:
  is_fno_eligible: fail
  surveillance_stage: fail
  market_breadth: penalise

params:
  band_fno:
    value: CALIBRATE
    calibration: {statistic: quantile, q: 0.25, feature: delivery_pct_20d_avg,
                  population: {is_fno_eligible: true}, period: design_only}
  band_cash:
    value: CALIBRATE
    calibration: {statistic: quantile, q: 0.25, feature: delivery_pct_20d_avg,
                  population: {is_fno_eligible: false}, period: design_only}

composites: {}

gates:
  - {code: G1, expr: "adv_20d_cr >= 25", unknown_blocks: true}
  - {code: G2, expr: "price_vs_dma200 > 1.0 AND price_vs_dma50 > 1.0", unknown_blocks: true}
  - {code: G3, expr: "ret_12m_skip_1m > 0", unknown_blocks: true}
  - {code: G4, expr: "vol_adj_mom_12m >= 0.60", unknown_blocks: true}
  - {code: G5, expr: "rel_strength_6m_vs_nifty200_tri >= 0.05", unknown_blocks: true}
  - {code: G6, expr: "delivery_pct_20d_avg >= if(is_fno_eligible, band_fno, band_cash)", unknown_blocks: true}
  - {code: G7, expr: "surveillance_stage == surveillance_stage.none", unknown_blocks: true}

size_dependent_checks:
  - {code: S1, expr: "impact_cost(provisional_value_cr, adv_20d_cr) <= 0.0035"}
  - {code: S2, expr: "provisional_value_cr <= 0.10 * adv_20d_cr"}

ranking:
  expr: "0.60 * z(vol_adj_mom_12m) + 0.40 * z(vol_adj_mom_6m)"

lifecycle:
  signal_ttl: {value: 3, unit: trading_sessions}

sizing:
  method: stop_risk_budget
  params: {notional_capital: OPEN, risk_to_stop_pct: OPEN, max_position_pct: OPEN}
  formula: "min(notional_capital * risk_to_stop_pct / (2.5 * atr_pct_20), notional_capital * max_position_pct)"

proposed_execution_rule:
  scope: simulation_and_plan_only
  entry_ref: "close_raw(signal_date)"
  entry_high: "entry_ref * 1.03"
  target_qty: "min(floor(target_value / entry_ref), min(floor(hard_cap_value / entry_high), floor(notional_capital * risk_to_stop_pct / (entry_high * 2.5 * atr_pct_20))))"
  tranches:
    - n: 1
      weight: 1.0
      limit: "entry_high"
      qty: "target_qty"
      attempt_policy: single_session
      recheck_gates: []
      recheck_failure: void_signal
  on_exhausted: void_signal
  exit_execution: open_next_executable_session

stop:
  evaluation_order: test_then_update
  initial: "entry_basis * (1 - 2.5 * atr_pct_20)"
  update: "max(stop_prev, highest_close_since_entry * (1 - 2.5 * atr_pct_at_peak))"

exit_rules:
  - {code: X1, cadence: daily,  expr: "close_raw(eval_date) < stop_in_force"}
  - {code: X2, cadence: daily,  expr: "persist(price_vs_dma50 < 1.0, 3, persist_unit.session)"}
  - {code: X3, cadence: weekly, expr: "vol_adj_mom_12m < 0.30"}
  - {code: X4, cadence: daily,  expr: "holding_days >= 180"}
  - {code: X5, cadence: daily,  expr: "surveillance_stage == surveillance_stage.asm_lt_2plus OR surveillance_stage == surveillance_stage.asm_st_2plus OR surveillance_stage == surveillance_stage.gsm_any"}

cooldown:
  trading_days: 20
  applies_after: [X1, X2, X3, X4, X5]

review_triggers: []

corporate_action_policy: standard_equity_ca_policy_v2
ca_state_held: [entry_ref, entry_high, entry_basis, highest_close_since_entry,
                stop_prev, stop_in_force, target_qty, current_earmark_qty]
signal_void_on: [band_close_event, surveillance_entry, transformative_ca]

benchmark: NIFTY_200_MOMENTUM_30_TRI

ai_inputs: {permitted: false}

validation:
  protocol: document_04
  warm_up_years: 1
  evaluable_years: 11
  holdout_years: 3

retirement:
  min_closed_positions: 50
  min_years: 2
  metric: rolling_return_vs_benchmark_after_costs
  window_years: 2
  threshold: 0.0
```

