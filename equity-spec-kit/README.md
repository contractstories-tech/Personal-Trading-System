# Equity Opportunity System — spec kit, release r5.9

The controlling package: specifications, the machine registry, strategy cards and their lifecycle records, schemas, the executable references that fix what everything means, and the tools that check them.
**Integrity:** every file is bound by SHA-256 in `MANIFEST.json`. Anything not matching it is a draft.

## Contents

| Path | What it is |
| --- | --- |
| `docs/Overview-Spec-v5-9.md` | Product scope, principles, readiness gates |
| `docs/Core-Platform-Architecture-Doc-01-r11.md` | Modules, flows, evaluation semantics, state machines, boundaries |
| `docs/Data-Contract-Doc-02-r8.md` | Every table, field, source, timing rule and feature definition |
| `docs/Strategy-Pack-Doc-03-r8.md` | Strategy explanations; card sections generated from the YAML |
| `docs/Validation-Protocol-Doc-04-r7.md` | Simulation, costs, tax view, holdout, trials, promotion statistics, stress, acceptance |
| `docs/Issue-Log-and-Traceability-r5-9.md` | Disposition of every review finding (§12: r5.4 audit; §13: r5.5 Windows review; §14: r5.7 post-audit corrections; §15: r5.8 real-NSE corrections; §16: r5.9 market-data completion) |
| `docs/Stage-0-Plan.md` | Stage 0 sources, layout, order of work, files to download |
| `START-HERE.md` | Non-normative release status and handover note; controlling artefacts win on any conflict |
| `registry.yaml` | 3.1.0: features, functions, enums, evaluation semantics, window conventions, session policy, scoring, identity, CA policy — every entry versioned |
| `policies/market_universe.yaml` | Universe policy: N = 500 and its buffers |
| `policies/source_policy.yaml` | 1.4.0: sources, per-source backfill availability, backfill guard, ingestion quality/quarantine thresholds, and NSE security-master policy |
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
| `mutation_check.py`, `golden/mutation_allowlist.yaml` | Fixture adequacy: mutation of simulation, feature and engine references; reviewed equivalent survivors only |
| `schedules/*.yaml` | Dated cost and tax schedules |
| `eos/` | Product code. Stage 0: PIT primitive, warehouse/raw landing, UDiFF and legacy price ingestion, delivery ingestion, NSE MII security-master ingestion, source/canonical price resolution and no-trade state resolution; r5.9 delivery cross-check, source catalogue, acquisition and coverage tools; `eos/fsio.py` holds every platform-specific file operation |
| `tests/test_m2.py` | M2/security-master: every case on every available codec and platform path — crash safety, raw landing, PIT reads, reissues/tombstones, UDiFF source identity, multi-series rows, MII master semantics, canonical prices and explicit no-trade states |
| `tests/test_catalog.py` | NSE source catalogue/acquisition/coverage regressions; capture-only sources can never become strategy coverage |
| `coverage_report.py`, `fetch_nse.py` | Read-only source-coverage reporting and conservative byte acquisition from the explicit NSE catalogue |
| `tests/test_portability.py` | Portability regressions: explicit encodings, no POSIX-only calls outside `eos/fsio.py`, every suite under strict-encoding mode, LF-only UTF-8 files |
| `tests/test_manifest.py` | Manifest regressions: release label, README heading, stray hidden files |
| `tests/test_release.py` | Revision references, titles, release lines, README listing and every section reference agree |
| `run_all.py` | Runs every contract command with the current interpreter, on any OS, and logs the output to `run_all.log` |
| `requirements.txt`, `requirements-dev.txt` | Pinned runtime dependencies (including the timezone database needed by PyArrow on clean Windows); plus pytest for the full contract |

## Execution contract

Python 3.12. Install the pinned dependencies, then run everything with one command. The same command works on Windows, Linux and macOS:

```bash
python -m pip install -r requirements-dev.txt     # PyYAML 6.0.3, pyarrow 25.0.1, tzdata 2026.4, pytest 9.1.1
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
python tests/test_catalog.py                                # source catalogue, acquisition and coverage
python tests/test_manifest.py                                 # manifest regressions
python tests/test_release.py                                  # cross-document consistency
python tests/test_portability.py                              # portability regressions
python tests/test_mutation.py                                 # mutation-worker infrastructure self-test
python mutation_check.py                                      # fixture adequacy (about a minute on 4 cores)
```

`python -m pytest -q` runs the same suites (except `mutation_check.py`). Keep the files byte-exact: unzip the kit as delivered, and if you keep it in git, keep `* -text` in `.gitattributes`. A line-ending conversion changes the hashes, and `make_manifest.py --verify` names it.

**Counts at r5.9 build:**

- `test_speclint.py`: 119 cases, 2,004 malformed cards and no crash.
- `speclint.py`: both cards compile as `experimental` per their lifecycle records.
- `test_golden.py`: 146 golden cases; 42 of 42 planted defects caught.
- `test_features.py`: 152 feature cases; 14 of 14 planted feature defects caught; every card-read feature covered.
- `test_card_golden.py`: 68 card cases; 12 of 12 planted card edits caught.
- `test_pipeline.py`: 6 end-to-end cases; 9 of 9 planted defects caught.
- `tests/test_m2.py`: **66 cases** on every available codec and both platform paths. The build environment ran 132/132 on JSONL (66 × POSIX + Windows-sim); Parquet remains the native-Windows acceptance run.
- r5.8 inherited real-derived M2 goldens include a 3,637-row UDiFF shape, legitimate EQ+BL same-ISIN observations, MII master classification, effective-session look-ahead protection, no-trade resolution, schema drift and reissue tombstones.
- `tests/test_catalog.py`: 3/3 source-catalogue/acquisition/coverage checks pass.
- `python -m pytest -q`: 19 passed.
- `tests/test_mutation.py`: mutation infrastructure self-test passes.
- `mutation_check.py`: 673 sites; 592 killed, 2 mutant timeouts, 79 reviewed equivalents, 0 unexplained survivors and 0 infrastructure errors.

## Certification

What has actually been run, and where. Nothing here is claimed beyond it.

| Environment | Result |
| --- | --- |
| Linux, CPython 3.11.15, PyYAML 6.0.3, pyarrow 25.0.1, pytest 9.1.1 (**r5.6 historical certification**) | `run_all.py --require-parquet --pytest`: every r5.6 command passed |
| Linux, CPython 3.12.3, the same pins (**r5.6 historical certification**) | `run_all.py --require-parquet --pytest`: every r5.6 command passed |
| Windows code paths (`MoveFileExW` write-through, sharing-violation retry, `msvcrt` locking, no directory open), under the Linux emulation in `eos/fsio.py` (`EOS_PLATFORM=windows-sim`) | Every M2 case passes on both codecs. This proves the Windows branch is taken and behaves as Windows would where the emulation models it. **It is not a Windows run** |
| Default-encoding independence (`-X warn_default_encoding -W error::EncodingWarning`, stdout as cp1252) | Every suite passes |
| **Windows 11, CPython 3.12.10, PyYAML 6.0.3, pyarrow 25.0.1, pytest 9.1.1 (r5.6 baseline, 24 September 2026)** | `run_all.py --require-parquet`: **ALL PASSED** on the native Windows code path after `tzdata` was installed manually. That run identified the clean-install defect corrected here: r5.6 did not declare `tzdata`. |
| **r5.7 clean-install Windows acceptance (25 September 2026)** | Fresh Windows 11 / Python 3.12.10 environment, installing only the declared requirements outside the manifest-bound package: `run_all.py --require-parquet` ended **ALL PASSED**. PyYAML 6.0.3, PyArrow 25.0.1, pytest 9.1.1 and `tzdata 2026.4` were installed from the declared files; `pip check` reported no broken requirements. |
| **r5.8 build environment** | All non-Parquet contract suites and the expanded r5.8 M2/security-master regressions pass; the regular 673-site mutation campaign is clean. The build environment has no PyArrow/network installation path, so r5.8 itself still requires the same fresh native-Windows `run_all.py --require-parquet` acceptance before it is certified. |
| **r5.9 build environment** | `run_all.py`: **ALL PASSED** on the available Linux environment; M2 132/132 on JSONL (66 cases × POSIX/Windows-sim), source catalogue 3/3, portability 4/4, mutation 673 sites with 0 unexplained survivors/0 infrastructure errors, pytest 19 passed. PyArrow is not installed here, so Parquet/native-Windows and genuine MTO/full-bhav/price-band/network acceptance remain external. |

### r5.9 market-data completion scope

r5.9 starts from the r5.8 code-complete price/security-reference release and does not rewrite it in place. It hardens the primary NSE MTO delivery parser (header date/count and reported-percentage checks), adds the full bhavcopy delivery fields as an independent validation source, retains raw MII price-range/tick evidence without pretending that historical band state is already solved, adds an explicit NSE source catalogue plus conservative byte downloader, and adds date-by-date coverage reporting. The current official price-band list is captured immutably with provenance but remains **non-semantic** until its historical date/effective-session and tick-rounding rules are proven from real files; capture cannot create source coverage or a `band_close_state`.

r5.8 remains the immediate predecessor and r5.7 remains the last native-Windows/Parquet certified release until the newer package is externally accepted.
