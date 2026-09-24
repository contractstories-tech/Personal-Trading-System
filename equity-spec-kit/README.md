# Equity Opportunity System — spec kit, release r5.5

The controlling package: specifications, the machine registry, strategy cards and their lifecycle records, schemas, the executable references that fix what everything means, and the tools that check them.
**Integrity:** every file is bound by SHA-256 in `MANIFEST.json`. Anything not matching it is a draft.

## Contents

| Path | What it is |
| --- | --- |
| `docs/Overview-Spec-v5-5.md` | Product scope, principles, readiness gates |
| `docs/Core-Platform-Architecture-Doc-01-r8.md` | Modules, flows, evaluation semantics, state machines, boundaries |
| `docs/Data-Contract-Doc-02-r5.md` | Every table, field, source, timing rule and feature definition |
| `docs/Strategy-Pack-Doc-03-r7.md` | Strategy explanations; card sections generated from the YAML |
| `docs/Validation-Protocol-Doc-04-r4.md` | Simulation, costs, tax view, holdout, trials, promotion statistics, stress, acceptance |
| `docs/Issue-Log-and-Traceability-r5-5.md` | Disposition of every review finding (§12: the independent audit of r5.4) |
| `docs/Stage-0-Plan.md` | Stage 0 sources, layout, order of work, files to download |
| `registry.yaml` | 3.0.0: features, functions, enums, evaluation semantics, window conventions, scoring, identity, CA policy — every entry versioned |
| `policies/market_universe.yaml` | Universe policy: N = 500 and its buffers |
| `policies/source_policy.yaml` | 1.2.0: sources, per-source backfill availability, backfill guard, ingestion quality and quarantine thresholds |
| `strategies/*.yaml` | The only executable source of each strategy (schema v6; no status inside) |
| `lifecycle/transitions/*.json`, `lifecycle/reports/` | The only source of each card version's status, with its evidence |
| `register_card.py` | Registers a card version as experimental (none → experimental record) |
| `schemas/card.schema.json` | Closed strategy-card schema |
| `schemas/run_manifest.schema.json` | Identity of a run, including each card's closure hash and lifecycle record |
| `schemas/portfolio_policy.schema.json`, `portfolio_policy.yaml` | Your policy; values OPEN until you set them |
| `schemas/strategy_lifecycle_transition.schema.json` | The only way a status changes; evidence enforced per edge |
| `schemas/holdout_ledger.schema.json` | Per-lineage record of historical dates exposed to research, with inherited exposure |
| `schemas/market_universe_policy.schema.json` | Shape of the universe policy |
| `speclint.py` | Card compiler: closed schema, then semantics against the card's registry closure |
| `test_speclint.py` | Regression cases for every defect any review found, schema contracts, closure scope, lifecycle, shape fuzz |
| `render_cards.py` | Generates Doc 03's card sections; `--check` enforces parity |
| `make_manifest.py` | Writes or verifies `MANIFEST.json` |
| `reference_sim.py`, `golden/golden_cases.yaml`, `test_golden.py` | Simulation, costs, tax, corporate actions, PIT reads, scoring, promotion statistics; planted defects |
| `reference_features.py`, `golden/feature_cases.yaml`, `test_features.py` | Every feature and forensic flag a card reads; planted definition defects; coverage check |
| `reference_engine.py`, `golden/card_cases.yaml`, `test_card_golden.py` | The cards' own expressions executed; planted card edits |
| `mutation_check.py`, `golden/mutation_allowlist.yaml` | Fixture adequacy: mutation of both reference modules; reviewed equivalent survivors |
| `schedules/*.yaml` | Dated cost and tax schedules |
| `eos/` | Product code. Stage 0 slice 1: PIT primitive, warehouse, canary, M2 price ingestion |
| `tests/test_m2.py` | M2: every case on every available codec — crash at every batch boundary, a two-writer race, both read contracts, the backfill guard, quarantine, planted read-path defects |
| `tests/test_manifest.py` | Manifest regressions: release label, README heading, stray hidden files |
| `tests/test_release.py` | Revision references, titles, release lines, README listing and every section reference agree |

## Execution contract

Python 3.12; dependencies pinned in `requirements.txt` (PyYAML; `pyarrow` on the warehouse machine).

```bash
python3 make_manifest.py --verify                              # package integrity
python3 test_speclint.py                                       # linter regression suite + shape fuzz
python3 speclint.py                                            # lints every card, with its lifecycle status
python3 render_cards.py --check docs/Strategy-Pack-Doc-03-r7.md  # Doc 03 matches the YAML
python3 test_golden.py                                         # reference golden cases + planted defects
python3 test_features.py                                       # feature golden cases + planted defects + coverage
python3 test_card_golden.py                                    # card-level golden cases + planted card edits
python3 tests/test_m2.py                                       # M2 on every available codec (add --require-parquet on the warehouse machine)
python3 tests/test_manifest.py                                 # manifest regressions
python3 tests/test_release.py                                  # cross-document consistency
python3 mutation_check.py                                      # fixture adequacy (a few minutes)
```

All must exit 0. `python3 -m pytest -q` runs the same suites (except `mutation_check.py`). On the machine holding the warehouse, `tests/test_m2.py --require-parquet` must also pass.

**Counts at r5.5:**

- `test_speclint.py`: 115 cases, 2,004 malformed cards and no crash.
- `test_golden.py`: 143 golden cases; 42 of 42 planted defects caught.
- `test_features.py`: 152 feature cases; 14 of 14 planted defects caught; every card-read feature covered.
- `test_card_golden.py`: 52 card cases; 12 of 12 planted card edits caught.
- `tests/test_m2.py`: 45 cases × 2 codecs.
- `mutation_check.py`: 588 mutation sites, 87% killed, every survivor a reviewed equivalent.

## Changing things

- **A card:** edit the YAML, run the linter and every suite, regenerate Doc 03's card sections, bump the card version, then register it: `python3 register_card.py strategies/<card>.yaml --by <you> --reason "..."`. A changed card is a new version with a new hash; a run can use only a registered version.
- **The registry:** edit it and run `python3 speclint.py`. Only cards whose closure the edit touched fail, each printing its new closure hash (`python3 speclint.py --closure` shows them all). Re-validate each such card, version it if its meaning changed, re-pin it and register it. Add a regression or golden case for the defect the change prevents.
- **A strategy's status:** only through a lifecycle transition record with the evidence the schema requires — never in the card.
- **A golden case or reference:** a new `mutation_check.py` survivor means a missing case. Add the case; widen `golden/mutation_allowlist.yaml` only for a mutant that truly cannot be distinguished, with its reason.
