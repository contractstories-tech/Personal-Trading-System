# Equity Opportunity System — spec kit, release r5.4

The controlling package: specifications, the machine registry, strategy cards, schemas and the tools that check them.
**Integrity:** every file is bound by SHA-256 in `MANIFEST.json`. Anything not matching it is a draft.

## Contents

| Path | What it is |
| --- | --- |
| `docs/Overview-Spec-v5-4.md` | Product scope, principles, readiness gates |
| `docs/Core-Platform-Architecture-Doc-01-r7.md` | Modules, flows, state machines, boundaries |
| `docs/Data-Contract-Doc-02-r4.md` | Every table, field, source, timing rule and feature definition |
| `docs/Strategy-Pack-Doc-03-r6.md` | Strategy explanations; card sections generated from the YAML |
| `docs/Validation-Protocol-Doc-04-r3.md` | Simulation, costs, tax view, holdout, trials, stress, acceptance |
| `docs/Issue-Log-and-Traceability-r5-4.md` | Disposition of every review finding |
| `docs/Stage-0-Plan.md` | Stage 0 sources, layout, order of work, files to download |
| `registry.yaml` | Feature, function, enum, class, trigger and policy vocabularies (v2.2.0) |
| `policies/market_universe.yaml` | Universe policy: N = 500 and its buffers |
| `policies/source_policy.yaml` | Sources, per-source backfill availability rules, ingestion quality thresholds |
| `strategies/*.yaml` | The only executable source of each strategy |
| `schemas/card.schema.json` | Closed strategy-card schema |
| `schemas/run_manifest.schema.json` | Identity of a run |
| `schemas/portfolio_policy.schema.json`, `portfolio_policy.yaml` | Your policy; values OPEN until you set them |
| `schemas/strategy_lifecycle_transition.schema.json` | The only way a strategy's status changes; evidence enforced per edge |
| `schemas/holdout_ledger.schema.json` | Per-lineage record of historical dates already exposed to research |
| `schemas/market_universe_policy.schema.json` | Shape of the universe policy |
| `speclint.py` | Card compiler: closed schema, then semantics |
| `test_speclint.py` | 92 regression cases, schema-contract tests and a shape fuzz |
| `render_cards.py` | Generates Doc 03's card sections; `--check` enforces parity |
| `make_manifest.py` | Writes or verifies `MANIFEST.json` |
| `reference_sim.py` | Reference implementation of Document 04's semantics |
| `golden/golden_cases.yaml` | 81 hand-computed golden cases |
| `test_golden.py` | Runs them, and plants 32 defects that must all be caught |
| `schedules/*.yaml` | Dated cost and tax schedules |
| `eos/` | Product code. Stage 0 slice 1: PIT primitive, warehouse, canary, M2 price ingestion |
| `tests/test_m2.py` | 38 M2 cases: crash at every batch boundary, a two-writer race, both read contracts, and 8 planted read-path defects the canary must catch |
| `tests/test_manifest.py` | Manifest regressions: release label, README heading, stray hidden files |
| `tests/test_release.py` | Every document revision reference, title, README listing and release label agree |

## Execution contract

Python 3.12; dependencies pinned in `requirements.txt` (PyYAML only).

```bash
python3 make_manifest.py --verify                              # package integrity
python3 test_speclint.py                                       # 92 cases + 1,860-card fuzz (or: python3 -m pytest -q)
python3 speclint.py                                            # lints every card in strategies/
python3 render_cards.py --check docs/Strategy-Pack-Doc-03-r6.md  # Doc 03 matches the YAML
python3 test_golden.py                                         # 81 golden cases + 32 planted defects
python3 tests/test_m2.py                                       # 38 M2 cases (add --require-parquet on the warehouse machine)
python3 tests/test_manifest.py                                 # manifest regressions
python3 tests/test_release.py                                  # cross-document consistency
```

All eight must exit 0. On the machine holding the warehouse, `pyarrow` is also required and `tests/test_m2.py --require-parquet` must pass.

## Changing things

- **A card:** edit the YAML, run the linter and the suite, regenerate Doc 03's card sections, bump the card version, then re-run the manifest.
- **The registry:** edit it, update every card's pinned `sha256` (the linter fails them otherwise), add a regression case for the defect the change prevents.
- **A strategy's status:** only through a lifecycle transition record with the evidence the schema requires.
