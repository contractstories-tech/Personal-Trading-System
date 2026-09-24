# Independent Assurance Report — Equity Opportunity System, package r5.4

*24 September 2026 · Subject: `equity-spec-kit-r5.4.zip` (package digest `67bf137f…2f92`, 44 files), plus `START-HERE.md` and `Stage-0-Plan.md` as supplied · Reproduction scripts: `audit/repro/`*

---

## 0. Verdict in one page

**Overall state.** The package is an unusually disciplined specification with a small, well-engineered first slice of product code. The data-ingestion foundation (M2: versioned observations, per-source availability, batch-atomic warehouse, look-ahead canary) is sound. I would trust it as the controlling foundation for **continuing Stage 0**. I would not yet trust it as the controlling foundation for **building the strategy engine and backtest lab, or for freezing Documents 01–04**.

The reason is not that the architecture is wrong. It is that the part of the system that turns data into decisions exists only as prose and typed-but-never-executed expressions. Every executable check in the package passes for a card with a 5% ROCE gate, a 0.10 cash-conversion gate and a 4×-ATR stop, just as it does for the real card (§3, A1). That is where the remaining ambiguity sits, and it is where two competent teams would build materially different systems.

**Confidence I would place in it today:**

| Layer | Confidence | Basis |
| --- | --- | --- |
| M2 ingestion, warehouse, canary (synthetic data) | **High** | I re-ran all 38 cases, ran the full suite on the production Parquet codec for the first time, and wrote adversarial tests. Two small defects found (B3, B4) |
| Data contract: timing, cutoffs, availability, corporate-action arithmetic | **Moderate–high** | The design is sound. Three definitional gaps remain: ISIN changes (B1), fundamentals assembly (B5) and rights valuation (C4) |
| Strategy-card compiler | **Moderate** | It is a real typed compiler, but its central safety rules can be bypassed (B2) |
| Evaluation semantics, model portfolios, features | **Low** | Mostly unspecified or prose-only (A1–A3, B8) |
| Validation protocol and promotion rule | **Moderate for the mechanics, low for the decision rule** | Costs, tax, fills and holdout are good. The promotion test would pass about 1 in 5 zero-alpha strategies (B7) |

**What should prevent what:**

| Next step | Decision | Conditions |
| --- | --- | --- |
| Continue Stage 0 (S1b real files, S2 security master, S3 XBRL, S4 coverage) | **Go** | Nothing here blocks it. Fold in B4 (an hour's work) now, and B1 during S2 |
| Structural freeze of Docs 01–04 and the registry | **Not yet** | A1–A4, B1 and B6, done inside the Stage 0 re-pin you have already planned |
| Build M7/M8/M9/M14 (engines, allocator, backtest lab) | **Not yet** | A1–A3 first; otherwise the engine *becomes* the specification |
| First calibration or backtest run | **Blocked** | Your existing gate items (B4–B12 of your Issue Log §10), plus A1–A3, B2, B7, B8, C1, and B5 for `ltqv_v1` |
| Shadow | **Blocked** | Existing gates, plus B3, C3, C7 and C8 |
| Production | **Blocked** | Existing gates |

**Has structural review reached diminishing returns?** For **architecture prose**, yes. I agree with your own assessment, and I would not commission another document-review round. The findings below are almost all of one kind: semantics that an executable reference would have forced someone to decide. The next assurance activity should target **executable artifacts** — a reference card evaluator, a reference model-portfolio constructor and reference feature implementations, each with card-level golden cases — not documents.

---

## 1. Scope, method and environment

**What I did:**

1. Unzipped the package, verified the manifest and ran all eight commands in the execution contract. All pass as claimed (92 linter cases plus a 1,860-card fuzz; 81 golden cases and 32 of 32 planted defects caught; parity; 38 M2 cases; 4 manifest cases; release consistency).
2. Read every document, schema, policy, card, registry entry and source file. I reconstructed the chain *raw file → observation → resolved view → feature → gate → claim → size → allocation → fill → corporate-action transform → exit → metric → promotion* and looked for where each link is defined.
3. **Installed `pyarrow` 25.0.1** (Python 3.11.15, PyYAML 6.0.1). Then:
   - ran `tests/test_m2.py --require-parquet`, which **passes**: the first execution of the Parquet codec;
   - re-ran the *whole* M2 suite on the Parquet codec, which **found B4**.
4. Wrote adversarial experiments:
   - linter bypasses;
   - read-contract scenarios with late publication and wrong ingestion mode;
   - hand-worked numerical probes of ROCE, rights, risk budget and float boundaries;
   - a Monte Carlo test of the promotion rule;
   - a semantic-change test on the cards;
   - **a mechanical mutation analysis of `reference_sim.py`** against the golden cases (267 mutants);
   - an ingestion scaling measurement.
5. Everything executed is reproducible:
   - `python3 audit/repro/reproduce_findings.py <unzipped kit>`
   - `python3 audit/repro/mutation_analysis.py <unzipped kit>` (output saved in `audit/mutation_analysis_output.txt`).

   Neither script modifies the package.

**What I could not verify:**

- **Real exchange files.** None were supplied, so parser correctness on real layouts is untested, as you already state.
- **Anything needing network access to NSE, BSE, RBI or vendors.**
- **Python 3.12 / PyYAML 6.0.3 specifically.** I ran 3.11 / 6.0.1, and everything passed.
- **Market-structure facts I state from domain knowledge.** These are marked "verify at Stage 0" where material. The main one is how often ISINs change on sub-division (B1).

**Authority model as I reconstructed it.** This is consistent with your START-HERE §4:

- The YAML card is the executable strategy.
- The registry owns vocabulary and definitions.
- Doc 02 governs data, Doc 01 architecture and Doc 04 validation.
- Doc 03 is generated and explanatory.
- `MANIFEST.json` defines the controlling set.

One structural observation follows from this. **The registry's formulas are prose** (your Issue 17.13, accepted). Of the 36 distinct features the two cards read, only 2 have even a partial reference implementation: single-year ROCE and the cash-conversion ratio. (Z-scores and `persist` are functions, not features.) So for 34 features the controlling definition is a sentence.

---

## 2. Answers to the central questions

**Can this exact package be trusted as the controlling foundation for building and validating the system?**
For data ingestion and Stage 0, **yes**. For the strategy, portfolio and validation layers, **not yet**. The controlling artifacts leave decision-changing semantics undefined (A2, A3), and the gate called "golden cases pass" does not test the cards (A1).

**Could two competent teams independently build materially the same system?**
- **M2:** yes, very nearly.
- **Strategy engine and backtest:** no. They would diverge on:
  - three-valued logic in exits;
  - what `out_of_domain: fail` means inside an exit;
  - `stale` and `conflicted` values in gates;
  - model-portfolio capacity;
  - how notional sizing scales to actual recommendations;
  - roughly 30 prose feature formulas;
  - how ISIN successors chain.

  Several of these change which securities are held, not merely the decimals.

**Could the platform produce point-in-time-correct, numerically sound, reproducible, appropriately qualified outputs?**
The design intent is correct almost everywhere, and the availability model is better than most institutional systems I have seen. I found:
- two concrete point-in-time holes in the read and ingest path (B3);
- one invariant that holds only on the test codec (B4);
- one core area underspecified (fundamentals assembly, B5);
- several numerical definitions that are economically wrong at their boundaries (B6, C3, C6).

**Does the package prevent known classes of silent error, rather than document them?**
- **At ingestion:** yes, genuinely. Crash atomicity, the lock, duplicate identity, hash verification and the canary are all executable and tested.
- **At the strategy layer:** only partly. Three of the compiler's headline rules — materiality, the hard cap and look-ahead — are bypassable, and all the bypasses were accepted in testing (B2).

**Are strategies separable from the platform, and can they be promoted, suspended, changed and retired without corrupting comparability?**
The concept is right: cards, lineage, a holdout ledger, a lifecycle schema. But every card pins the SHA-256 of the **whole registry file**, and any registry edit forces every card to a new version. That makes a strategy's identity depend on unrelated registry content, and it collides with the rule that a changed card needs fresh holdout data (A4).

**Can the system explain, years later, why a security was or was not surfaced?**
The run-manifest design is strong. Three gaps remain:
- portfolio state and the promoter-group map are not bound (you already track this as H3/H4);
- snapshots are not yet persisted anywhere;
- identity is not chained across ISIN changes (B1), without which "what happened next" breaks at every sub-division.

**Is the boundary between deterministic logic, AI, personal constraints and manual execution clear and enforceable?**
- **On paper:** clear.
- **In code:** there is currently no AI code, no broker code and no network code at all. I searched every `.py` file, so no latent order path exists today.
- **Technical enforcement:** correctly deferred to Documents 05 and 07.
- **One boundary to tighten now:** personal sizing currently leaks into strategy measurement (A3).

**Would I personally move from specification into implementation and formal validation?**
- **Into Stage 0 implementation:** yes, now.
- **Into engine implementation and validation:** after a focused correction pass — A1–A4 plus the B items tagged "re-pin" — which I estimate at weeks, not months. The quickest way to do it is to write the reference evaluator (A1), because that forces most of A2 and A3 to be decided.

---

## 3. Findings

Severity is by consequence. **Gate** is the latest point by which each must be closed. **Owner** is the artifact that should carry the fix.

### Class A — must be resolved before structural freeze and before the first calibration or backtest run

These do not block Stage 0 data work.

#### A1. Card semantics are never executed; the freeze criterion does not test the card

- **Evidence:**
  - There is no expression evaluator anywhere in the package; I searched every `.py` file.
  - `reference_sim.py` implements rules with the constants hard-coded. For example, `run_stop(..., mult=2.5)` at `reference_sim.py:141`, while the card's stop multiplier lives in `strategies/mom_v1.yaml:106-107`.
  - The golden cases call these functions directly and never read a card.
  - Doc 01 §8 defines the **freeze criterion** as linter PASS, suite PASS, render parity PASS and golden PASS.
- **Reproduced (`reproduce_findings.py`, A1).** I changed `mom_v1`'s stop from 2.5× to 4.0× ATR, `ltqv_v1` G2 from ROCE ≥ 15% to ≥ 5%, and G3 from 0.70 to 0.10. After regenerating Doc 03, all of these still pass: `speclint` (both cards), `test_speclint` 92/92, parity OK, `test_golden` 81/81 with 32/32 mutants caught.
- **Why it matters.** The goldens prove that the *reference functions* are right. Nothing proves that a production engine interprets the *card* correctly: its gates, tri-state combination, overrides, composites, ranking, tranche expressions, stop expressions and exits. That is exactly the layer where a coding agent is most likely to diverge. It is also where a card edit could silently change a strategy while every gate stays green.
- **Smallest correction:**
  1. A `reference_engine.py` that parses card expressions with the existing `speclint` parser and evaluates them over a synthetic feature panel under the normative semantics in A2.
  2. **Card-level golden cases.** For example: "given this 30-session feature panel for 3 securities, `mom_v1` produces claims {…}, stop path {…} and exit on session k". The thresholds come from the YAML, so the 2.5 → 4.0 edit above must fail a case.
  3. Planted card mutants, such as `>=` → `>` in a gate or a changed stop multiplier.
  4. Amend the freeze criterion to require card-level goldens.
- **Owner:** Doc 04 §2 and the package. **Gate:** before the first calibration run, and part of structural freeze.

#### A2. Evaluation semantics are undefined where the outcome changes materially

Doc 01 §7 defines tri-state *gates* and an input-resolution order, and nothing more. The following are undefined:

| Gap | Evidence | Divergence it permits |
| --- | --- | --- |
| **a. Three-valued `AND` / `OR` / `NOT`** | Never defined; the words "Kleene" and "three-valued" appear nowhere | `ltqv_v1` X4 is `promoter_pledge_pct > 0.25 OR auditor_resignation_5y == true`. With pledge at 30% and auditor data missing, one reading fires the exit ("TRUE on known inputs" under Kleene logic). A strict reading raises only a review trigger and keeps holding |
| **b. `out_of_domain: fail` inside exits and `persist`** | Doc 02 §8 says only "`fail` fails any gate reading it"; Doc 01 §7:122 says exits fire only when TRUE on known inputs | The catastrophe case for `ltqv_v1`: a large write-off turns equity negative. `roce_hy_ttm` → out of domain, so X1's `persist(…, 2, half_year)` is UNKNOWN (`reference_sim.persist` returns `None`). `cfo_pat_3y` → out of domain once 3-year PAT ≤ 0, so X2 is undefined. `ey_vs_own_5y_median` → out of domain, so X3 is undefined. Under the natural reading **no deterministic exit fires**, and the model portfolio (which has no human to act on review triggers) holds the collapsing company until delisting. Symmetry says `fail` should be *conservative for the position*: fail the gate, fire the exit |
| **c. `stale`, `conflicted` and `not_applicable` in gates** | Doc 02 §8:188 lists the states; §11 defines when a value becomes stale; nothing says what a gate does with one | One team uses the last value; another blocks. Promoter pledge, for example, is stale 165 days after quarter-end |
| **d. Universe filters on unknown** | `mom_v1.yaml:28` `circuit_days_60d <= 5`; filters also define the z-score population (Doc 02 §9) | An unknown filter result — for instance, with no band file — changes both the candidates and every score |
| **e. `substitute`** | Registered at `registry.yaml:15`, defined nowhere | See B2: it also bypasses materiality |
| **f. Weekly cadence** | `mom_v1` X3 has `cadence: weekly` with no weekday; `weekly_eod: fri` has no holiday or muhurat rule | Different exit days; skipped or shifted entry weeks |
| **g. Review triggers in model portfolios** | Undefined in Doc 04 | Whether M14 ignores them, exits on them, or flags the period |

- **Smallest correction.** One normative "evaluation semantics" section, versioned in the registry and pinned by cards. Recommended choices:
  - **Gates:** any non-`known` material input makes the gate unknown, so gates never need three-valued combination.
  - **Exits:** Kleene logic over known terms; `out_of_domain: fail` *fires* the exit. Alternatively, cards declare `on_out_of_domain: exit | review` per exit.
  - **`stale`:** unknown for gates.
  - **`conflicted`:** unknown for gates; the primary value for ranking, with a confidence drop (as the registry already implies).
  - **Filters:** unknown excludes from the candidates but not from the scoring population.
  - Delete `substitute`.
  - **Weekly:** the last executable session of the ISO week, at or before the named weekday.
  - **Model portfolios** ignore review triggers, and the report counts them.

  Each choice gets a card-level golden case (A1).
- **Owner:** Doc 01 §7 plus the registry. **Gate:** before the first calibration run; part of freeze.

#### A3. Model-portfolio construction and sizing scale are undefined, and personal values leak into strategy measurement

- **Evidence:**
  - Doc 04 §3 ("Model portfolios", line 63) says only "runs on its card's notional capital, sized by its card".
  - No card declares a maximum number of positions or what happens when qualifying claims exceed capital.
  - `rank_and_gate` computes a rank (Doc 01 §7), but **no document gives the rank a consumer**. Scarce actual capacity is filled by holdings → earliest signal → market cap → ISIN (Doc 01 §9).
  - `mom_v1`'s gates are absolute thresholds, so in a strong market hundreds of the top-500 names can qualify on the same Friday.
  - The sizing parameters are `OPEN` "user values" (Doc 03 §6): notional capital, target volatility or risk-to-stop, and maximum position. Yet:
    1. maximum position and volatility target determine concentration, and therefore measured alpha and drawdown;
    2. `S1` and `S2` in `mom_v1` test `provisional_value_cr` in **absolute INR**, so notional capital decides *which signals exist*;
    3. "cash earns nothing" means the choice of capital also sets cash drag.
  - Separately, Doc 01 §9:152 sets the **actual** target to the largest claim target, which the registry computes from `notional_capital` (`target_value` ← `sizing.formula`). That contradicts Doc 01 §4:88: "notional capital … exists only to run that strategy's model portfolio".
- **Why it matters:**
  - **Two teams would build different backtests.** One might take the top of the rank, another fill by market cap, another lever up.
  - **Your personal risk settings would change a strategy's measured validity.** Changing them after the holdout would either burn the holdout or quietly change what was validated.
  - **Recommendations would be sized to the notional portfolio, not your capital.**
  - **The momentum hypothesis says "cross-sectional", but the implementation as specified is an absolute filter whose rank does nothing.**
- **Smallest correction:**
  1. **Measurement construction** becomes part of the hypothesis, pre-registered in the card:
     - a fixed measurement capital in INR, so the impact checks are realistic;
     - a maximum number of positions or a weighting rule;
     - the capacity rule, recommended as *rank order within the strategy*, with the existing deterministic tie-break;
     - the treatment of residual cash.
  2. **Personal sizing** belongs to the allocator only. Define the conversion — for example, claim weight = `target_value / notional_capital`, and actual target = weight × `total_capital`, capped by policy. Re-run S1/S2 at the actual size in M8b.
  3. Card parameters then contain no personal values. Your `OPEN` items move entirely into `portfolio_policy.yaml`.

  Golden cases: capacity with 5 qualifying claims and room for 3; scale conversion; S1 failing at actual size but passing at notional size.
- **Owner:** Doc 01 §4 and §9, Doc 04 §3, the card schema. **Gate:** before the first backtest; part of freeze.

#### A4. Strategy identity is coupled to the whole registry file; lineage is self-declared

- **Evidence:**
  - `speclint.py:686` compares each card against `sha256_file(registry.yaml)`.
  - Working agreement 5 says "A registry change re-pins every card … and bumps card versions".
  - Doc 04 §7 says "Changing a card after seeing its holdout result makes it a new version, which needs fresh holdout data".
  - S0.10 shows the symptom: a wrong comment has been left in the registry because fixing it would re-version both cards.
  - Lineage is a free string that the linter only checks for code-prefix consistency. A revised momentum card declared as a new lineage `momx` starts with a clean holdout ledger.
- **Why it matters.** Once one strategy has had its sealed holdout evaluation, adding a feature for a *different* strategy — or fixing a typo — forces the evaluated card to a new version. Under your own rule, that requires fresh holdout data. Either the rule gets waived informally ("it's only a mechanical re-pin"), which erodes the control, or every registry edit burns holdouts. Neither is sustainable across years of adding strategies. Self-declared lineage defeats the ledger by renaming one level up, which is exactly the attack the ledger was built to stop at version level.
- **Smallest correction** (at the Stage 0 re-pin you have already scheduled):
  1. Pin each card to a **canonical hash of its registry closure**: the entries it references, the corporate-action policy, the cutoff policy and the evaluation-semantics version. Keep the whole-file hash in the run manifest for provenance.
  2. Add a `version` per registry entry. Run manifests already expect `feature_version` (`run_manifest.schema.json`), and today nothing supplies it.
  3. A re-pin that leaves the closure unchanged is not a new strategy version.
  4. Lineage gains `derived_from`. The holdout ledger rule becomes: a lineage created after any sealed exposure in the same strategy class must declare which exposures informed it, and inherits them.
- **Owner:** the registry, the card schema, `speclint`, Doc 04 §7. **Gate:** the Stage 0 re-pin.

### Class B — high-priority corrections

#### B1. Identity across ISIN changes is undefined; Indian sub-divisions commonly change the ISIN

- **Evidence:**
  - `successor_isin` appears once in the whole package (Doc 02 §4:85).
  - Prices, deliveries, features, universe hysteresis, claims, cooldowns, `holding_days`, tax lots and stop state are all keyed by ISIN.
  - No rule says how any of them chain across a successor.
- **Domain fact (verify its frequency at Stage 0).** In Indian depositories a change of face value normally produces a **new ISIN**. So do some capital reductions and schemes. Mergers convert a target into a successor.
- **Consequences if unchained:**
  - after every split, the security drops out of the market-eligible universe for 5 sessions (the entry hysteresis);
  - 200-day, 12-month and 5-year features reset;
  - the tax holding period restarts;
  - a held momentum position loses its stop state.

  Much of this happens silently: "unknown", not an error.
- **Correction:**
  - an explicit `security_lineage` (a stable internal `security_id` with ISIN validity windows);
  - rules for which tables are keyed by `security_id` versus ISIN;
  - the price and adjustment join across the boundary;
  - carrying claim state, cooldown, holding period and tax lots through, with the corporate-action factor applied.

  Golden cases: a split with an ISIN change; a merger conversion.
- **Owner:** Doc 02 §4–§5, M1. **Gate:** S2 (security master), before Stage 0 closes.

#### B2. The compiler's materiality, hard-cap and look-ahead rules are bypassable

- **Reproduced.** All of the following were accepted by `speclint`:
  1. `unknown_overrides: {roce_3y_avg: substitute}`, and the same on momentum's delivery input. The materiality rule at `speclint.py:376` blocks only `penalise`.
  2. A waivable gate `quality_composite > 0` built from material inputs. The check at `speclint.py:620` inspects direct feature references only.
  3. `target_qty: "max(floor(target_value / entry_ref), floor(hard_cap_value / entry_high))"`, and `… + floor(0 * hard_cap_value)`. The hard-cap rule at `speclint.py:576` is a **substring test**.
  4. `entry_ref: "close_raw(next_executable_session(signal_date))"`, and a gate reading `open_raw(next_executable_session(eval_date))`. Both are future prices, and both type-check.
- **Why it matters.** These are the three rules the r5.2 release most relied on: that material inputs block, that fills cannot breach the cap, and that there is no look-ahead. In prose they are prevented; in the compiler they are bypassable. A runtime canary would catch (4) only if every price read goes through M5.
- **Correction:**
  1. Remove `substitute`, or define it and treat it like `penalise`.
  2. Expand composites and parameters to their feature closure before the waiver check.
  3. Enforce the hard cap as an **engine invariant**, independent of the card, and replace the substring check with a structural one (a top-level `min(…)` containing `floor(hard_cap_value / <limit>)`).
  4. Remove `next_executable_session` from the expression vocabulary — no card uses it — and restrict the date arguments of `close_raw` and `open_raw` to `signal_date`, `eval_date` and `prev_session(…)`.

  Each gets a regression case.
- **Owner:** `speclint`, the registry. **Gate:** before the first calibration run.

#### B3. Two point-in-time holes in the read and ingest path

- **(a) `point_in_time_panel` silently drops late-published bars.**
  - **Reproduced:** D2's bhavcopy arrives live at 23:30, after D2's 23:00 cutoff. The live decision on D3 had D1, D2 and D3. `point_in_time_panel(D1, D3)` returns only D1 and D3, and D2 is permanently absent (`eos/m2/resolve.py:95-100`).
  - The docstring presents the panel as merely conservative about *corrections*. In fact it is lossy for late *first* versions. That breaks backtest-equals-live for shadow-period replays and the shadow-versus-backtest comparison in Doc 04 §12. It also changes rolling-window features in ways that depend on per-feature presence rules.
  - **Correction:** define the panel as each bar's *earliest* version with its `usable_from` retained, masked per decision cutoff. Add a regression test.
- **(b) `mode="backfill"` back-dates a file actually received after the cutoff.**
  - **Reproduced:** today's file ingested at 23:45 in backfill mode becomes usable at 22:30 and is visible to the 23:00 run it missed (`eos/m2/ingest.py:56`). A later replay would "see" data the live run did not have.
  - **Correction:** add `live_capture_start` to `source_policy.yaml`. Refuse backfill inference for trade dates on or after it, or when `received_at` is within N days of the trade date. Add a test.
- **Gate:** before the scheduled downloader starts live capture, and before any replay or shadow comparison.

#### B4. The production Parquet codec accepts naive timestamps; the invariant holds only on the test codec

- **Reproduced.** With `pyarrow` installed:
  - `JsonlCodec` refuses a naive 22:30.
  - `ParquetCodec` stores it as 22:30 **UTC**, which is 04:00 IST the next day. The naive check lives only in `_enc` (`eos/store.py:86-89`), which `ParquetCodec.dumps` (`:133`) never calls.
  - Re-running the whole M2 suite on Parquet: 37/38 pass, and `naive_timestamps_refused_by_store` fails.
- **Why it matters:**
  - H8 is recorded as fixed.
  - Your own gate — "warehouse data is not trusted until the Parquet round-trip passes" — would be satisfied while this invariant is false on the production codec.
  - Also, only one test ever exercised Parquet.
- **Correction:**
  - one pre-write validator shared by both codecs;
  - parametrise `tests/test_m2.py` over both codecs, with `--require-parquet` running everything;
  - pin `pyarrow` in `requirements.txt`. Version 25.0.1 passes the round-trip here; the pin must be re-validated on the warehouse machine.
- **Gate:** before any warehouse data is trusted. The fix is small.
- **Positive result:** apart from this one invariant, the Parquet round-trip and the rest of the suite pass on Parquet.

#### B5. How fundamentals are assembled point-in-time is underspecified, and it is the core of `ltqv_v1`

- **Evidence:**
  - Doc 02 §7:180 keys the wide view `(isin, basis, effective_from)`.
  - The canonical query (Doc 01 §14) AS-OF joins **one** row.
  - The features, however, need *periods*: four contiguous quarters for TTM, three and five fiscal years, and the prior year's capital employed.
  - With restatements, the most recently *available* row can be a restated **old** period. "A derived figure uses the component versions usable at the row's cutoff" (Doc 02 §7) is the right rule, but no table or function shape implements it.
  - The basis fallback is timeless. `asof_with_basis_fallback(…, company_files_consolidated)` and golden G23 take a boolean with no date. Evaluated with today's knowledge, a company that began consolidating in 2016 is either excluded before 2016 (a survivorship-like look-ahead) or mixes bases inside a 3-year window.
- **Correction:**
  - a versioned `fact(isin, basis, fact_code, period_start, period_end, version, usable_from)` table;
  - a normative `period_panel_as_of(isin, basis, cutoff)` returning the latest version of each period;
  - basis chosen as-of the cutoff, with every period in a window required to share one basis (otherwise `missing`).

  Golden cases: an old period restated after a newer period is filed; a switch from standalone to consolidated.
- **Owner:** Doc 02 §7, Doc 01 §14. **Gate:** decided in S3; implemented before M4–M6. Not needed for `mom_v1`.

#### B6. The ROCE definition is economically wrong at its boundaries (`ltqv_v1` G2, X1 and ranking)

- **Reproduced (`reference_sim.roce`):**

  | Case | Result |
  | --- | --- |
  | Operating loss (EBIT −20), cash-rich, capital employed ≤ 5% of total assets | **ROCE = 1.00, capped**: passes G2 and sits at the top of the quality composite |
  | EBIT 30, capital employed 150 now, −140 a year earlier | **ROCE = 6.00 (600%)** — no cap outside the cash-rich branch |
  | Same, prior capital employed −200 | **ROCE = −1.20** — fails G2 for a good business moving out of net cash |

- **Also undefined:** whether the 5% test applies at year-end, at year-start or to the average capital employed that is actually the denominator. The mutation analysis shows 0.05 → 0.055 survives every golden case.
- **Why it matters.** The cap was introduced to avoid failing excellent cash-rich businesses (B2a). As written, it rewards *any* cash-rich company, including loss-making treasuries. It also creates unbounded or sign-flipped values around net-cash transitions, which are common in asset-light Indian mid-caps with large customer advances.
- **Correction:**
  - cap branch only when underlying EBIT > 0; otherwise compute normally, or treat as out of domain (`fail`);
  - apply a universal `min(ROCE, 1.00)`;
  - test the cap on the average capital employed actually used;
  - average capital employed ≤ 0 with EBIT > 0 is capped; with EBIT ≤ 0 it fails.

  Add a golden case for each, and pin the 5% threshold.
- **Owner:** the registry. **Gate:** the Stage 0 re-pin. The card is pre-validation, so the change is cheap now.

#### B7. The promotion rule is statistically weak, and the acceptance documents disagree

- **Evidence:**
  - Doc 04 §12's criteria are all **sign-based**: alpha > 0 over the design period and in the holdout, at least 60% of rolling windows positive, positive Brinson selection, Sharpe above the benchmark's.
  - The Newey–West standard error is defined "for acceptance tests" (§11:192), and **no acceptance test uses it**.
  - The trial count is "reported" but enters no criterion.
- **Reproduced (Monte Carlo).** A strategy with **zero** true alpha and 5–12% tracking error passes the design-alpha, holdout-alpha and 60%-windows tests with **p ≈ 0.20–0.21**. That is before the drawdown, turnover and Brinson conditions, which are partly correlated with these.
- **Acceptance inconsistencies:**
  - Doc 03 §5:112–114 requires positive alpha versus Nifty 200 Quality 30 and drawdown "no worse than the benchmark's".
  - Doc 04 §12 has no Quality-30 test and allows benchmark drawdown + 5 pp.
  - `ltqv_v1` **retires** on rolling alpha versus the secondary (Quality 30) benchmark (`ltqv_v1.yaml:183`), which is never tested at promotion. A strategy could be promoted and breach its retirement metric immediately.
- **Why it matters.** This is the single place where curve-fitting turns into money. The lineage ledger stops repeated holdout draws, which is good, but it cannot fix a weak test.
- **Correction** (pre-register before the first design evaluation):
  - a hurdle on the Newey–West t-statistic, or a probability-of-backtest-overfitting / deflated-Sharpe hurdle that uses the logged trial count, over the design period;
  - the holdout required to be consistent with the design estimate, not merely positive;
  - a stated minimum detectable alpha for each validation class;
  - Doc 03 §5 aligned with Doc 04 (Doc 04 governs);
  - either test alpha versus Quality 30 at promotion, or retire against the primary benchmark;
  - recorded in the reports: the Momentum-30 and Quality-30 TRIs are recent launches (about 2019–2020), and their earlier history is back-calculated.
- **Owner:** Doc 04 §11–§12. **Gate:** before the first design evaluation.

#### B8. Most features are defined only in prose, and several prose definitions admit materially different implementations

- **Evidence:**
  - Of the 36 distinct features the cards read, only single-year ROCE and the cash-conversion ratio have reference implementations (alongside the z-score and `persist` functions). The other 34 have only a registry sentence.
  - Concrete ambiguities:
    - **`delivery_pct_20d_avg`** is "mean delivery_qty / volume over 20 sessions". That could be the mean of daily ratios or a ratio of sums. No minimum presence is stated, although `adv_20d_cr` has "≥ 15 present". Zero-volume days are undefined. The volume could be the bhavcopy's or the MTO file's.
    - **Per-security session windows** (DMA 50/200, returns, ATR): exchange sessions versus the security's traded sessions, minimum presence for the DMAs, suspensions, and IPOs younger than the window. The muhurat question is already logged.
    - **`ey_median_5y`** excludes sessions "before the latest transformative action". The registry's `transformative_ca` includes **rights issues**, so read literally, any rights issue removes a company from `ltqv_v1` G9 for about 3 years (750 sessions).
    - **Delivery-band calibration** (`mom_v1` parameters): the population and sampling are unstated — pooled security-sessions, Friday samples, the strategy universe after filters, or per-date quantiles averaged. Pre-registration is incomplete while any of these is open.
- **Why it matters.** The *first* run your plan envisages is the delivery-band calibration. It depends on the least-specified feature.
- **Correction:** every feature a card reads gets a reference implementation plus a golden case before any run that reads it. Specify `delivery_pct_20d_avg` and the calibration sampling before the calibration run. Define "transformative" for `ey_median_5y` separately from the void event.
- **Owner:** the registry, Doc 02 §8, `reference_sim`. **Gate:** feature by feature, before the first run that reads each one.

### Class C — medium

#### C1. The test suite is regression-strong and adequacy-weak

- **Raw mutation score: 67%** (179/267 killed; `audit/mutation_analysis_output.txt`). Some survivors are equivalent (rounding precision, epsilons), and `rolling_windows` is admittedly not implemented.
- **Meaningful survivors — behaviours no golden case pins:**
  - **the point-in-time boundary itself:** `usable_from == cutoff`, in `usable`, `asof` and `read_checked`. A filing at 19:30 plus a 30-minute lag lands exactly on 20:00, so this case will be common;
  - `close == stop`;
  - `open == limit`;
  - the ex-date equality boundary;
  - the ROCE 5% threshold;
  - the tranche-2 clamp `rtq - earmark` (the "falling target" case never binds it);
  - the straddle-year rule "exemption in force at FY end" (`fy + 1` → `fy - 1` survives);
  - current-year short-term-against-long-term set-off inside `tax_multi_year`;
  - regime pro-rating of long-term tax;
  - the "isolated spike" sensitivity rule (G30b fails on the cliff rule first, so the spike rule is never independently tested);
  - a lock followed by a missing band file;
  - the lowest impact tier.
- **Planted mutants.** Of the 32, `exemption_on_gross` (`test_golden.py:265`) hard-codes the expected wrong answer when `ltcg == 150000.0`. It proves nothing about logic. The rights fixtures all use `a = 1`.
- **Correction:**
  - add the boundary and branch goldens above;
  - replace the hard-coded mutant;
  - bring mutation-score CI forward from Document 07 to "before the first calibration run", with a threshold on non-equivalent survivors.

#### C2. Gate boundaries are evaluated in floating point, so the result depends on summation order

Ingestion thresholds use exact arithmetic (S0.2), but features are `DOUBLE`.

- **Reproduced.** A 3-year mean of [0.01, 0.01, 2.08] against 0.70 gives 0.7000000000000001 (PASS) in one order and 0.6999999999999998 (FAIL) in the other. The same happens at 1.0, 2.5 and 6.0 — `ltqv_v1`'s debt-to-equity and coverage thresholds.
- **Correction:** evaluate gate, exit and filter comparisons in `Decimal`, or with a declared conservative epsilon recorded in `engine_settings`. Add a golden case.

#### C3. The momentum risk budget can be exceeded, and the stop is unknown when you place the order

- **Evidence:** the quantity is capped using ATR at the signal date (`mom_v1.yaml:92`). The initial stop uses ATR at the fill date (`:106`). Doc 03 §4 states that the risk "can never exceed the budget".
- **Reproduced:** ATR rising from 2.0% to 2.6% between signal and fill takes the risk at the initial stop to **1.30× the budget**.
- **Manual-execution consequence:** the stop depends on the fill session's own range, so the brief cannot state the exact invalidation level before you trade.
- **Correction:** freeze the initial-stop ATR at the signal date. This is a card change at pre-validation.

#### C4. Rights-entitlement intrinsic value: prose and executable reference disagree

- **Evidence:** Doc 02 §5:117 and the registry say `max(0, P_ex − S)`. `reference_sim.py:209` uses `TERP − S`, and "P_ex" is not defined as open or close.
- **Reproduced:** with P_ex = 100 against TERP = 112, the entitlement is worth 500 by the prose and 800 by the reference.
- **Correction:** adopt TERP (deterministic and known before trading), or define P_ex exactly. Align the prose, registry and reference.
- **Gate:** S2.

#### C5. One bad row rejects the whole file

- **Evidence:** a single malformed ISIN, an OHLC violation or an unmapped MTO symbol rejects the entire day. You already know this about zero-price rows. Real CM files carry many instruments outside your scope: debt, SME, ETFs, rights-entitlement series.
- **Correction:** generalise the zero-price decision into a scoped quarantine policy:
  - out-of-scope instruments are logged and skipped;
  - an in-scope defective row is quarantined, with coverage marked incomplete for that ISIN;
  - whole-file rejection is kept only for structural faults.
- **Gate:** S1b.

#### C6. Ingestion cost grows linearly per file, so a full backfill is quadratic

- **Evidence:** every ingestion re-reads and re-hashes the entire `ingestion_log` (`_already`) and lists every manifest.
- **Measured** on 3-row synthetic files, Parquet: 0.47 → 0.82 → 1.31 s per day at 100, 200 and 300 days.
- **Extrapolated (not measured):** a 12–16-year backfill of two sources runs to many hours.
- **Correction:** parse first, then check only that trade date's log partition, or keep a SHA index.
- **Gate:** S1b.

#### C7. "All material counter-evidence … including 'none found' after adequate coverage" has no definition of adequate coverage

- **Why it matters:** "None found" is the single phrase most likely to convey more certainty than the evidence supports. Before Stage 5 the only counter-evidence sources are deterministic.
- **Correction:** for each counter-evidence class, state a machine-checkable coverage condition. Otherwise display "not searched" or "coverage X%", never "none found".
- **Owner:** Doc 01 §12 now (as a rule); Doc 05/06 for detail.

#### C8. How actual claims diverge from model claims is unspecified

- **Undefined cases:**
  - you buy a partial quantity, late, or above the limit;
  - tranche timing is anchored to your fill or to the proposed tranche 1;
  - a manual holding meets a new claim.
- **Correction:** Stage 3 golden cases. They should be noted in Doc 01 §9 now.

#### C9. A void-event predicate names a card's gate by number

- **Evidence:** `registry.yaml:147` (`governance_event`) refers to "the card's G5 threshold". In `mom_v1`, G5 is relative strength.
- **Correction:** make it a declared card parameter, and have the linter check it.

### Class D — low and hygiene

- **D1. Drift that the r5.4 consistency check cannot see.** It only checks revision tokens and titles:
  - Doc 03's header still says "Release r5.2 · 21 September 2026";
  - Doc 04 §2 says 75 cases and 28 mutants (the actual figures are 81 and 32);
  - Overview §9 cites "Document 04 §15" for Stage 0 items (they are in §17);
  - the registry cites "Doc 02 s14 / s15" (now §13 / §16) and "Document 02 r3";
  - the Overview's silence example says "1,842 securities evaluated", while the universe is N = 500.

  Extend `test_release.py` to header release lines and section anchors, and remove counts from prose.
- **D2.** The README requires Python 3.12 and PyYAML 6.0.3, but nothing checks the running versions. Everything also passes on 3.11 / 6.0.1. Consider a hash-locked `requirements.txt` that includes `pyarrow`.
- **D3. Schedule details.** All are low effect and already marked as estimates to confirm, except the first:
  - the tax schedule marks STCG at 15% from 2004-10-01 as **verified**, but it was 10% until 31 March 2008 (outside the current windows);
  - contract notes typically round STT to the rupee, so a reconciliation "to the paisa" will show a difference by design (verify on your contract note);
  - service tax in 2012 was 10.3–12.36%, not the 15% applied.
- **D4.** `test_golden.py:63` calls `eval()` on fixture strings. The file is hash-bound, but explicit data would be better.

---

## 4. Findings that belong in later documents (correctly deferred; not re-raised)

I checked these deferrals and agree with their timing:

- the trial log and lineage enforcement (B4 in your log);
- drawdown and Brinson, including cash as a segment (B5, B6);
- the semantic run-manifest validator (B11) and simulation identity (B12);
- lifecycle status leaving the card (B7);
- portfolio-state lineage (H3, H4);
- retirement and shadow statistics (H5, H6);
- Document 05 (AI);
- Document 06 (presentation);
- Document 07 (deployment, network, credential and order-endpoint scans; kill-switch atomicity; restore and replay);
- reissue semantics (B10);
- band-file semantics (S0.7).

Two items should move **earlier** than currently scheduled:

1. **Mutation-score CI** (C1), from Document 07 to before the first calibration run.
2. **Snapshot persistence** — where a snapshot's part list is stored so that a `data_snapshot_id` can be replayed — should be defined in Stage 1 alongside run manifests, not in Document 07.

---

## 5. What is already strong — do not redesign

- **Timing model.** Two cutoff domains; one materialised `usable_from`; per-source inferred availability with `inferred_basis`; corrections never back-dated; the loader refusing inferred times at or after the cutoff; lag-sensitivity reruns in Doc 04 §14. This is correct and unusually honest.
- **Warehouse:**
  - stage → commit record → apply;
  - readers refuse while a commit is unapplied;
  - roll-forward recovery;
  - per-thread lock re-entry;
  - duplicate identity as a hard error;
  - hash-verified parts;
  - snapshot isolation;
  - crash tests at every boundary and a real two-thread race.

  With B4 fixed, this is production-grade for a personal system.
- **Canary design.** Sentinels are built so that each plausible wrong read selects one of them, and an empty read is never a pass. All 8 planted read defects are caught.
- **The compiler's architecture.** A closed schema, a real typed expression grammar, namespaced enums, runtime-state ownership, corporate-action completeness and duplicate-key rejection. B2 is a set of gaps in its rules, not its design.
- **Portfolio principles:**
  - the security's size is the largest claim, never the sum;
  - scarce capacity is filled in a deterministic order without an invented cross-strategy score;
  - a breach marks a claim valid-but-not-actionable rather than deleting it;
  - trims have a tolerance band;
  - quantities are capped at the worst permitted fill;
  - the stop is tested before it is updated, including on the fill day;
  - dividends are counted in return on the ex-date but spendable only on the payment date.
- **Validation mechanics:**
  - effective-dated costs and tax;
  - tax as a view, never a gate;
  - circuit-aware fills that test the open against the band;
  - an explicit missing-band haircut and exclusion of uncovered periods;
  - a sealed holdout with a per-lineage ledger;
  - a sensitivity rule that does not reward peaks;
  - coverage gaps excluded from evidence.
- **Data-truth rules.** Material inputs block. Surveillance is known "none" before a framework existed. Absent from a complete file is distinguished from not covered. The declared history window is a requirement, not a target.
- **Non-execution policy.** The *credential* itself must be read-only at the broker, or none is mounted and M15 is fed by statement import. This is the right bar.
- **Process.** Verifying claims by running code, the issue log with dispositions, and "every fix has a test that would have caught it". It is why this audit found adjacent gaps rather than contradictions of core design.

---

## 6. User-policy choices — not defects

These are yours to set, and I have not treated them as findings:

- every `OPEN` value in `portfolio_policy.yaml`;
- drawdown response;
- broker profile;
- surcharge;
- the restricted list;
- whether to accept the 22:30 inferred publication time and the batched re-pin defaults;
- the trial-log gate you are asked to confirm.

After A3, the card sizing parameters also stop being personal values. Measurement construction becomes part of each hypothesis, and your personal values live only in the policy file.

**On the open question "`mom_v1` end-to-end before `ltqv_v1`?" — I recommend yes:**

- it needs only exchange files, which you already have a parser for;
- it exercises the whole chain (A1–A3, B3, B7) with no dependence on XBRL depth or share-count history;
- `ltqv_v1` additionally waits on B5, B6 and the S3 depth measurement.

---

## 7. Material assumptions and risks that cannot yet be resolved

1. **Share-count history for the top-500 universe — this affects both strategies, not only `ltqv_v1`.** Market cap needs `shares_outstanding` point-in-time for about 12–16 years. Doc 02 §5 derives it from corporate actions and allotments but does not say what the starting count is. Free structured shareholding history may not reach far enough back. If coverage falls below 95%, the kill switch removes those dates entirely. **Measure this in S4 alongside XBRL depth.** The minimal spec fix is to define the seed as the first shareholding-pattern total (from its `usable_from`), with the count `missing` before that.
2. **Archive depth and semantics.** Delivery, band files, F&O eligibility and surveillance lists. Momentum's delivery and F&O gates *block* when data is missing, so their coverage sets the evaluable window directly.
3. **Back-calculated benchmark history** before each index's launch (Momentum 30, Quality 30).
4. **ISIN-change frequency** (B1), and symbol reuse.
5. **Human prior knowledge.** The thresholds were written by people (and a model) who have seen 2023–2026 markets. No ledger can un-see that. Treat the holdout as weaker evidence than its name suggests, and rely on shadow results.
6. **Automated download.** Whether scheduled downloading from NSE is technically and contractually sustainable is untested. This belongs to the Document 07 licence policy.
7. **Real-file parser behaviour, Parquet on the warehouse machine, and inferred publication times** — all Stage 0 facts, as you have them.

---

## 8. What should happen next

In order:

1. **Now, within S1b:**
   - fix B4 and parametrise the M2 suite over both codecs;
   - add `live_capture_start` (B3b);
   - adopt the quarantine policy (C5) and the ingestion index (C6);
   - start S1b the moment batch 1 arrives.
2. **During S2:**
   - specify identity across ISIN changes (B1);
   - rights valuation (C4);
   - the weekly and holiday rule (A2f).
3. **In the single Stage 0 re-pin you have already planned, together with H9, B7 and S0.10:**
   - closure pinning and lineage parentage (A4);
   - the evaluation-semantics section (A2);
   - model-portfolio construction and the split between measurement and personal sizing (A3);
   - the ROCE fix (B6);
   - linter rules (B2);
   - the momentum stop ATR (C3);
   - the void-event parameter (C9);
   - drift (D1).
4. **Add to your "before the first calibration run" gate** (Doc 01 §17):
   - the reference card evaluator and card-level golden cases (A1);
   - reference feature implementations for every feature the card under test reads, including the delivery-calibration sampling (B8);
   - boundary golden cases and mutation-score CI (C1);
   - `Decimal` gate evaluation (C2);
   - the pre-registered promotion rule with a power statement (B7).
5. **Before building M4–M6 for `ltqv_v1`:** the fundamentals assembly specification and golden cases (B5).
6. **Then take `mom_v1` end-to-end:** calibration → design evaluation → sealed holdout → shadow.

**What the validation phase must then prove, beyond what your Doc 04 already lists:**

1. **The engine interprets cards correctly.** The production engine passes the card-level golden cases *unmodified*, and each planted card mutant fails at least one.
2. **Backtest equals live.** A replay of a shadow-period decision from its run manifest reproduces the live output exactly. This includes a day with a late-published file and a day with a correction.
3. **Point-in-time equality boundary.** A row with `usable_from == cutoff` is used, and one a second later is not, in both domains.
4. **Construction is independent of personal policy.** Changing your portfolio policy changes recommendations but leaves every strategy-level metric unchanged.
5. **Identity continuity.** A split with an ISIN change, and a merger conversion, leave features, claims, stops, cooldowns and tax lots continuous.
6. **Evidence quality.** The promotion statistic clears its pre-registered hurdle, with the logged trial count applied, and the report states the minimum detectable alpha and the share of evidence resting on inferred availability.

Once items 1–4 of the "what should happen next" list are closed, I would regard the package as ready for structural freeze and formal validation. At that point further structural review would be low-value, and assurance effort should move entirely to executable conformance and real-data golden cases.

---

*Reproduce: `python3 audit/repro/reproduce_findings.py <path-to-unzipped equity-spec-kit-r5.4>` (about 30 s) and `python3 audit/repro/mutation_analysis.py <same path>` (a few minutes). `pip install pyarrow` enables B4.*
