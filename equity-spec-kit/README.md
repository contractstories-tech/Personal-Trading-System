# Equity Opportunity System — spec kit, release r5.6

The controlling package: specifications, the machine registry, strategy cards and their lifecycle records, schemas, the executable references that fix what everything means, and the tools that check them.
**Integrity:** every file is bound by SHA-256 in `MANIFEST.json`. Anything not matching it is a draft.

## Contents

| Path | What it is |
| --- | --- |
| `docs/Overview-Spec-v5-6.md` | Product scope, principles, readiness gates |
| `docs/Core-Platform-Architecture-Doc-01-r9.md` | Modules, flows, evaluation semantics, state machines, boundaries |
| `docs/Data-Contract-Doc-02-r6.md` | Every table, field, source, timing rule and feature definition |
| `docs/Strategy-Pack-Doc-03-r8.md` | Strategy explanations; card sections generated from the YAML |
| `docs/Validation-Protocol-Doc-04-r5.md` | Simulation, costs, tax view, holdout, trials, promotion statistics, stress, acceptance |
| `docs/Issue-Log-and-Traceability-r5-6.md` | Disposition of every review finding (§12: the audit of r5.4; §13: the review of r5.5 on Windows) |
| `docs/Stage-0-Plan.md` | Stage 0 sources, layout, order of work, files to download |
| `registry.yaml` | 3.1.0: features, functions, enums, evaluation semantics, window conventions, session policy, scoring, identity, CA policy — every entry versioned |
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
| `golden/pipeline_cases.yaml`, `test_pipeline.py` | Whole populations through `reference_engine.run_pipeline` to the model portfolio and published claims; planted defects |
| `mutation_check.py`, `golden/mutation_allowlist.yaml` | Fixture adequacy: mutation of both reference modules; reviewed equivalent survivors |
| `schedules/*.yaml` | Dated cost and tax schedules |
| `eos/` | Product code. Stage 0 slice 1: PIT primitive, warehouse (with raw landing), canary, M2 price ingestion; `eos/fsio.py` holds every platform-specific file operation |
| `tests/test_m2.py` | M2: every case on every available codec and every platform path — crash at every batch boundary, a two-writer race, a writer killed holding the lock, raw landing, both read contracts, the backfill guard, quarantine, planted read-path defects |
| `tests/test_portability.py` | Portability regressions: explicit encodings, no POSIX-only calls outside `eos/fsio.py`, every suite under strict-encoding mode, LF-only UTF-8 files |
| `tests/test_manifest.py` | Manifest regressions: release label, README heading, stray hidden files |
| `tests/test_release.py` | Revision references, titles, release lines, README listing and every section reference agree |
| `run_all.py` | Runs every contract command with the current interpreter, on any OS, and logs the output to `run_all.log` |
| `requirements.txt`, `requirements-dev.txt` | Pinned runtime dependencies; plus pytest for the full contract |

## Execution contract

Python 3.12. Install the pinned dependencies, then run everything with one command. The same command works on Windows, Linux and macOS:

```bash
python -m pip install -r requirements-dev.txt     # PyYAML 6.0.3, pyarrow 25.0.1, pytest 9.1.1
python run_all.py                                 # every command below, with this interpreter; exit 0 = all passed
python run_all.py --require-parquet               # on the warehouse machine: also fail if Parquet could not run
```

On Windows, `py -3.12` in place of `python` selects the interpreter. `run_all.py` prints one line per command and keeps the full output in `run_all.log`, which is what to send back when something fails. The commands it runs, each of which must exit 0:

```bash
python make_manifest.py --verify                              # package integrity
python test_speclint.py                                       # linter regression suite + shape fuzz
python speclint.py                                            # lints every card, with its lifecycle status
python render_cards.py --check docs/Strategy-Pack-Doc-03-r8.md  # Doc 03 matches the YAML
python test_golden.py                                         # reference golden cases + planted defects
python test_features.py                                       # feature golden cases + planted defects + coverage
python test_card_golden.py                                    # card-level golden cases + planted card edits
python test_pipeline.py                                       # end-to-end golden cases + planted defects
python tests/test_m2.py                                       # M2 on every codec and platform path (--require-parquet on the warehouse machine)
python tests/test_manifest.py                                 # manifest regressions
python tests/test_release.py                                  # cross-document consistency
python tests/test_portability.py                              # portability regressions
python mutation_check.py                                      # fixture adequacy (about a minute on 4 cores)
```

`python -m pytest -q` runs the same suites (except `mutation_check.py`). Keep the files byte-exact: unzip the kit as delivered, and if you keep it in git, keep `* -text` in `.gitattributes`. A line-ending conversion changes the hashes, and `make_manifest.py --verify` names it.

**Counts at r5.6:**

- `test_speclint.py`: 118 cases, 2,004 malformed cards and no crash.
- `speclint.py`: both cards compile, as `experimental` per their lifecycle records.
- `test_golden.py`: 146 golden cases; 42 of 42 planted defects caught.
- `test_features.py`: 152 feature cases; 14 of 14 planted defects caught; every card-read feature covered.
- `test_card_golden.py`: 68 card cases; 12 of 12 planted card edits caught.
- `test_pipeline.py`: 4 end-to-end cases; 7 of 7 planted defects caught.
- `tests/test_m2.py`: 50 cases × 2 codecs × 2 platform paths (POSIX, Windows emulated) = 200 runs.
- `tests/test_portability.py`: 4 checks (static, bytes, CRLF naming, every suite under strict encoding).
- `mutation_check.py`: 589 mutation sites in `reference_sim.py` and `reference_features.py`, 87% killed, every survivor a reviewed equivalent.

## Certification

What has actually been run, and where. Nothing here is claimed beyond it.

| Environment | Result |
| --- | --- |
| Linux, CPython 3.11.15, PyYAML 6.0.3, pyarrow 25.0.1, pytest 9.1.1 (pinned venv) | `run_all.py --require-parquet --pytest`: every command passes |
| Linux, CPython 3.12.3, the same pins | `run_all.py --require-parquet --pytest`: every command passes |
| Windows code paths (`MoveFileExW` write-through, sharing-violation retry, `msvcrt` locking, no directory open), under the Linux emulation in `eos/fsio.py` (`EOS_PLATFORM=windows-sim`) | Every M2 case passes on both codecs. This proves the Windows branch is taken and behaves as Windows would where the emulation models it. **It is not a Windows run** |
| Default-encoding independence (`-X warn_default_encoding -W error::EncodingWarning`, stdout as cp1252) | Every suite passes |
| **Windows, CPython 3.12 (the warehouse machine)** | **Not yet run.** This is the gate before any warehouse data is trusted: `py -3.12 run_all.py --require-parquet` on that machine |

## Changing things

- **A card:** edit the YAML, run the linter and every suite, regenerate Doc 03's card sections, bump the card version, then register it: `python register_card.py strategies/<card>.yaml --by <you> --reason "..."`. It stamps the real time. A changed card is a new version with a new hash; a run can use only a registered version.
- **The registry:** edit it and run `python speclint.py`. Only cards whose closure the edit touched fail, each printing its new closure hash (`python speclint.py --closure` shows them all). A new value in an enum a card only uses as a field value (a weekday, a horizon) re-pins nothing. A feature whose formula reads another registry block declares it in `depends_on`. Re-validate each such card, version it if its meaning changed, re-pin it and register it. Add a regression or golden case for the defect the change prevents.
- **A strategy's status:** only through a lifecycle transition record with the evidence the schema requires — never in the card.
- **A golden case or reference:** a new `mutation_check.py` survivor means a missing case. Add the case; widen `golden/mutation_allowlist.yaml` only for a mutant that truly cannot be distinguished, with its reason.
