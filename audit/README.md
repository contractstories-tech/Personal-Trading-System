# Independent assurance audit of equity-spec-kit r5.4

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

**Resolution:** every finding is resolved in `equity-spec-kit` release r5.5 (in this repository, and as `equity-spec-kit-r5.5.zip`). The disposition of each finding is in `equity-spec-kit/docs/Issue-Log-and-Traceability-r5-5.md` §12. The scripts in `repro/` target the r5.4 package; the fixes are guarded inside r5.5 by its own suites. For example, the A1 card edits are planted edits in `test_card_golden.py`, and the B2 bypasses are regression cases in `test_speclint.py`.
