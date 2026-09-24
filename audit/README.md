# Independent assurance audit of equity-spec-kit r5.4

> **Not controlling, and not part of any release.** This folder is the history of one audit: its report and the scripts that reproduced its findings against **r5.4**. It is not bound by any `MANIFEST.json`, and nothing here verifies a later release; each release verifies itself with its own `run_all.py`. `repro/mutation_analysis.py` is **Unix-only**: it bounds each mutant with `signal.SIGALRM`, which Windows lacks. Both scripts were written and run on Linux only. Run them on Linux or macOS, against an unzipped r5.4, if you want to see the original findings reproduce.

| File | What it is |
| --- | --- |
| `Assurance-Report-r5.4.md` | The report: verdict, readiness by phase, findings A1–D4 with evidence and corrections, strengths, open risks, next steps |
| `repro/reproduce_findings.py` | Re-runs every executed finding against an unzipped package; modifies nothing |
| `repro/mutation_analysis.py` | Mechanical mutation analysis of `reference_sim.py` against the supplied golden cases |
| `mutation_analysis_output.txt` | Output of the mutation analysis on r5.4 (267 mutants, 179 killed) |

```bash
unzip equity-spec-kit-r5.4.zip -d /tmp/kit
pip install pyarrow            # optional: enables finding B4
python3 audit/repro/reproduce_findings.py /tmp/kit/equity-spec-kit-r5.4
python3 audit/repro/mutation_analysis.py  /tmp/kit/equity-spec-kit-r5.4
```

Environment used: Python 3.11.15, PyYAML 6.0.1, pyarrow 25.0.1.

**Resolution:** every finding is resolved in `equity-spec-kit` release r5.5, and carried into r5.6 (in this repository, and as `equity-spec-kit-r5.6.zip`). The disposition of each finding is in `equity-spec-kit/docs/Issue-Log-and-Traceability-r5-6.md` §12; the later review of r5.5 is in §13. The scripts in `repro/` target the r5.4 package; the fixes are guarded inside r5.5 by its own suites. For example, the A1 card edits are planted edits in `test_card_golden.py`, and the B2 bypasses are regression cases in `test_speclint.py`.
