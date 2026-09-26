# Strategy Pack — Document 03 r8

*Release r5.9 · 25 September 2026 · current state only · card sections generated from `strategies/*.yaml` by `render_cards.py` · cards pinned to their registry 3.1.0 closures*

## 1. How strategies work

A strategy is an independent method of detecting an opportunity. It is not a category a company belongs to, and not a pot your capital is split into. Each strategy is one YAML card: hypothesis, data, triggers, gates, optional ranking, sizing and construction of its measurement portfolio, a proposed execution rule, exits, expiry, benchmark, and retirement rule.

**The YAML is the only executable source of a strategy.** The card sections in §7 are generated from it, each stamped with the card's SHA-256, and `render_cards.py --check` fails the build if this document and the YAML ever differ. The prose below explains the strategies; where it and a card disagree, the card governs.

Every card pins the hash of its **registry closure** — the registry entries it actually uses, plus the evaluation semantics. A registry change inside that closure forces the card to be re-validated; a change elsewhere (a feature for another strategy, say) leaves it untouched. What the card *means* is fixed by executing it: `test_card_golden.py` runs each card's own expressions against hand-computed cases.

**Both current strategies are `experimental`** — per their lifecycle records in `lifecycle/transitions/`, the only place a status lives: they may be backtested, and they may not reach your feed. Every threshold below is a pre-registered hypothesis. Once formal testing begins, thresholds are frozen; any change is a version bump with a logged reason, including changes prompted by disappointing results.

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

Ranking weights: 50% quality, 30% value, 20% consistency — each a composite of directional z-scores over the full strategy universe, computed before gating. Every quality input is material, so the quality composite needs all five (r5.6; r5.5 accepted four, which would have ranked a company on a different formula when its ROCE trend was missing). Value and consistency may each lack one secondary input. A company whose rank cannot be formed is **unrankable**: recorded with the reason, never a candidate.

**Definitions that matter** (Document 02 governs):

- ROCE uses underlying EBIT over average capital employed, **including lease liabilities**, so returns are measured consistently before and after Ind AS 116.
- A **profitable** cash-rich business whose average capital employed is at most 5% of average assets gets a capped ROCE of 1.00 and passes G2, rather than failing it. A loss-making cash shell fails; negative equity fails; every ROCE is capped at 1.00, so a near-zero denominator cannot produce 600%.
- Valuation is blacked out after demergers, rights issues and capital reductions until comparable financials exist, so a demerger cannot make a stock look falsely cheap.
- The five-year earnings-yield median covers only the continuing business: it restarts after a demerger, capital reduction or amalgamation, but not after a rights issue.
- A company with no promoter has a pledge of zero and passes G5.
- **The audit-opinion gate has been removed from v1, not softened.** It previously waived wherever opinion data was missing — which, across a backtest, would have validated a strategy *without* that check while the card claimed to have one. A material input may not be waived, so the gate returns as a new card version once the extraction path in Document 02 §13 exists and has coverage. Auditor *resignations*, which come from structured exchange disclosures, remain a blocking gate.
- Forensic flags fire on the numbers alone. Dilution is measured on an issuance-neutral share count, so a bonus issue is never mistaken for dilution.

**Entry.** Three tranches of one third each. Quantities convert at the prior session's close, with the limit only as a price cap — and are additionally capped so that even a fill at the highest permitted price cannot breach the hard position limit. Tranche 1 re-evaluates every gate on every attempt, for up to 30 sessions, and voids the signal if any gate fails. Tranches 2 and 3 start 21 and 42 sessions after tranche 1 and retry for 10 sessions each. A failed recheck skips that session. When retries run out, the remaining tranches are cancelled and the holding is kept. The final tranche takes the remainder, so no shares are stranded by rounding.

**Exits** (Kleene logic; an exit also fires when a thesis input turns out-of-domain in the failing direction — negative equity, three years of losses — so a collapsing holding is sold, not held):

- ROCE below 12% for two consecutive half-years
- Cash conversion below 0.50
- Valuation stretched with a declining ROCE trend
- Pledge above 25% or any auditor event
- Serious surveillance

A 60-session cooldown follows any exit.

**Construction.** The measurement portfolio holds at most `max_positions` names (pre-registered before the first design evaluation), filled in rank order when more qualify than fit.

**History.** 7 warm-up years (the 7-year operating history and 5-year windows need them) plus 9 evaluable years, of which 3 are holdout: 16 years of history in total.

## 4. `mom_v1` — momentum

**Hypothesis.** Cross-sectional relative strength persists over 3–12 months because information diffuses slowly. Volatility scaling separates persistent trend from noise, and skipping the latest month avoids short-term reversal. In Indian mid-caps, illiquidity and circuits contaminate the effect, so liquidity gating is part of the signal.

**Triggers.** New entries are evaluated at the week's last executable session on or before Friday: Thursday when Friday is a holiday or a muhurat session, which trades but is not executable under the platform's session policy. Exits are evaluated every session; the weekly momentum exit on the same weekly session.

**Gates:**

- 20-day traded value ≥ ₹25 crore
- Price above both its 50- and 200-day averages
- Positive 12-month return after skipping the latest month
- Volatility-adjusted 12-month momentum ≥ 0.60
- 6-month relative strength ≥ 5 points above the Nifty 200 TRI, skip month applied to both sides
- Delivery percentage above an F&O-dependent band — **blocking when delivery data is unavailable**, because delivery is part of the hypothesis. A period without delivery coverage produces no momentum signals rather than a quietly different strategy
- No surveillance

After provisional sizing, two further checks apply: estimated impact cost ≤ 0.35% and participation ≤ 10% of average traded value.

**Delivery bands, pre-registered.** Delivery percentage is the 20-session volume-weighted ratio of delivered to traded shares. Each band is the **25th percentile** of it over the design period only, pooled over every security and weekly entry session in the strategy universe (`sampling: pooled_entry_sessions`). It is computed separately for F&O-eligible and non-F&O names, using point-in-time eligibility, and never from the holdout. The quantile and the sampling are fixed now, before any data is examined, so the choice cannot be fitted.

**Sizing.** Quantity is the smallest of three: the target value at the reference price, the hard position cap at the highest permitted fill price, and the stop-risk budget at that same worst-case fill. Sizing and the initial stop use the same ATR, the one known at the signal, so the risk taken can never exceed the budget, whatever permitted price the fill comes in at.

**Stop.** The initial stop is 2.5 × the signal-date ATR percentage below the entry basis — known before the order, so the brief can state it — and is tested from the fill session onward. It then trails 2.5 × the ATR-at-peak percentage below the highest close since entry. ATR is frozen at the moment each new high is set, so post-breakout calm cannot drag the stop upward. The stop is tested against the previous session's value before it updates. It never moves down. All price levels are adjusted on corporate-action ex-dates.

**Other exits:**

- Three sessions below the 50-day average
- Weekly volatility-adjusted momentum below 0.30
- 180 sessions held
- Serious surveillance

A 20-session cooldown follows every exit, including the time exit.

**Construction.** When more names qualify on a Friday than the measurement portfolio's `max_positions` allows, the rank — 60% 12-month and 40% 6-month volatility-adjusted momentum, cross-sectional z-scores — decides which fill. That is what makes the strategy cross-sectional, as its hypothesis says, rather than a pure threshold filter. A name missing either momentum input is unrankable and not a candidate, however much capacity is free. A conflicted input ranks on its primary value and costs one confidence band.

**History.** 1 warm-up year plus 11 evaluable years, of which 3 are holdout: 12 years of price history.

## 5. Acceptance: economic validity versus your deployment view

Two different questions, deliberately kept apart:

1. **Does the strategy work?** Judged after implementable costs, including brokerage, statutory charges, spread, impact and circuit-aware fills, against the card's total-return benchmark. This decides promotion.
2. **Is it worth deploying for you?** The same results viewed after your configurable tax treatment and portfolio policy. This informs your choices and never changes whether the strategy is valid.

A strategy does not become statistically invalid because tax rules change. It may become unattractive for you, and the system shows that separately.

**Per-strategy economic tests.** Document 04 §12 governs; in summary:

- **Every strategy** must clear a pre-registered statistical hurdle on its design-period alpha. The hurdle rises with the number of design trials logged for its lineage. Its sealed-holdout alpha must be positive and consistent with the design estimate.
- **`ltqv_v1`** additionally:
  - positive alpha versus Nifty 200 Quality 30 TRI, the benchmark its retirement rule uses;
  - positive in at least 60% of rolling 3-year windows;
  - **positive Brinson–Fachler selection**, because the strategy excludes about ten sectors and allocation effects alone must not count as skill;
  - drawdown no worse than the benchmark's plus 5 percentage points;
  - turnover below 40% a year;
  - positions still open at holdout end reported separately.
- **`mom_v1`** additionally:
  - Sharpe above the benchmark's;
  - survives doubled costs, doubled impact and the circuit-aware exit model.

**Decomposition** against published factor indices is reported for both. If a strategy can be reproduced as an index plus a tilt, buying the index is the better decision.

## 6. Hypothesis parameters, and values only you can set

**Measurement parameters — part of each hypothesis, not personal values.** Each card's `sizing` params and `construction.max_positions` are `OPEN`: the measurement capital in INR, the target volatility contribution or risk to the stop, the maximum position, and the maximum number of positions. They define the model portfolio a strategy is *measured* on:

- the measurement capital decides which impact and participation checks pass;
- the concentration and capacity rule shape alpha and drawdown.

They are set once, **before the first design evaluation**, recorded in a new card version, and never changed after seeing results, except as a new version with fresh holdout data. Choose them to represent a sensible deployment scale for the strategy, not your personal risk appetite. A card cannot pass `experimental` while any remain `OPEN`.

**Your values — only in `portfolio_policy.yaml`.** These are:

- your total capital;
- your caps per stock, sector, promoter group and position count;
- your minimum position;
- your drawdown limit and response;
- your cash floor;
- your trim tolerance.

The per-strategy cap defaults to `NONE`: there are no capital buckets unless you choose them. A strategy's claim reaches you as a **weight** of its measurement capital, applied to your total capital and then capped by your policy. Changing these values changes your recommendations but never a strategy's measured results.

Set every value from your own circumstances, never from backtest results.

## 7. Generated cards

The sections below are generated by `render_cards.py` from `strategies/*.yaml`, and parity is checked in CI. Do not edit them here.

<!-- generated from strategies/ltqv_v1.yaml sha256:a18a13f9dc9861d4ba53b55ce8646bb7e51acea4e8dbb743586375547ddafdd9 -->
```yaml
schema_version: 6
code: ltqv_v1
strategy_class: fundamental_long_term
version: 1.0.0-prevalidation.9
lineage: {code: ltqv, derived_from: []}
registry: {version: 3.1.0, closure_sha256: 960667f3e567f378c5a45f091081f02736aafc886ae2d1e15293b0e1ce295d7e}

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
    min_inputs_known: 5          # every input is material (r5.6: a composite may tolerate missing secondary inputs only)
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

# Model-portfolio construction is part of the hypothesis (Doc 04 s3): pre-registered once, before the first
# design evaluation, and never set from personal circumstances. Personal sizing lives in portfolio_policy.yaml.
construction:
  max_positions: OPEN
  capacity_order: rank
  residual_cash: uninvested

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

corporate_action_policy: standard_equity_ca_policy_v3
ca_state_held: [entry_ref, entry_high, tranche_limit, target_qty, revised_target_qty, current_earmark_qty]
signal_void_on: [governance_event, surveillance_entry, transformative_ca]
void_parameters:
  governance_event: {promoter_pledge_pct: 0.15}

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

<!-- generated from strategies/mom_v1.yaml sha256:a6209714631cffb95e7824308c695bfeadf7e718ac31f95ddf3dfb05ce17d480 -->
```yaml
schema_version: 6
code: mom_v1
strategy_class: momentum
version: 1.0.0-prevalidation.9
lineage: {code: mom, derived_from: []}
registry: {version: 3.1.0, closure_sha256: 9ab85c0f695ebc6f891c5b0f6e2b5e2be1b46f3788c8cb9c9ff189217f1a0679}

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
                  population: {is_fno_eligible: true}, period: design_only,
                  sampling: pooled_entry_sessions}
  band_cash:
    value: CALIBRATE
    calibration: {statistic: quantile, q: 0.25, feature: delivery_pct_20d_avg,
                  population: {is_fno_eligible: false}, period: design_only,
                  sampling: pooled_entry_sessions}

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
  formula: "min(notional_capital * risk_to_stop_pct / (2.5 * atr_pct_at_signal), notional_capital * max_position_pct)"

# Model-portfolio construction is part of the hypothesis (Doc 04 s3): pre-registered once, before the first
# design evaluation, and never set from personal circumstances. Personal sizing lives in portfolio_policy.yaml.
construction:
  max_positions: OPEN
  capacity_order: rank
  residual_cash: uninvested

proposed_execution_rule:
  scope: simulation_and_plan_only
  entry_ref: "close_raw(signal_date)"
  entry_high: "entry_ref * 1.03"
  target_qty: "min(floor(target_value / entry_ref), min(floor(hard_cap_value / entry_high), floor(notional_capital * risk_to_stop_pct / (entry_high * 2.5 * atr_pct_at_signal))))"
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
  initial: "entry_basis * (1 - 2.5 * atr_pct_at_signal)"
  update: "max(stop_prev, highest_close_since_entry * (1 - 2.5 * atr_pct_at_peak))"

exit_rules:
  - {code: X1, cadence: daily,  expr: "close_raw(eval_date) < stop_in_force"}
  - {code: X2, cadence: daily,  expr: "persist(price_vs_dma50 < 1.0, 3, persist_unit.session)"}
  - {code: X3, cadence: weekly, weekday: fri, expr: "vol_adj_mom_12m < 0.30"}
  - {code: X4, cadence: daily,  expr: "holding_days >= 180"}
  - {code: X5, cadence: daily,  expr: "surveillance_stage == surveillance_stage.asm_lt_2plus OR surveillance_stage == surveillance_stage.asm_st_2plus OR surveillance_stage == surveillance_stage.gsm_any"}

cooldown:
  trading_days: 20
  applies_after: [X1, X2, X3, X4, X5]

review_triggers: []

corporate_action_policy: standard_equity_ca_policy_v3
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
