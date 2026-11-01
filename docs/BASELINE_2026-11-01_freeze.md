# Baseline record at the code freeze, 2026-11-01

PRD BASE-8. **This is the reference point for anyone changing Ask BPL after the capstone team's code freeze.** It
replaces `docs/BASELINE_2026-10-31.md` as the current baseline (that record stays as history). Compare new runs with
the two files below using `scripts/compare_runs.py`.

## Commit and environment

| | |
|---|---|
| Evaluated commit | `c0f1c48` (clean tree; merge of patch 0042) |
| Machine, runtimes, database, index | As in `docs/BASELINE_2026-10-31.md`: team Mac (macOS 27.2), Python 3.14.4, Node 26.12.0, PostgreSQL 16.15, Pinecone `askbpl-pilot` (dense, 1536, cosine) |
| Answer model / embeddings / retrieval | `claude-sonnet-4-6` / `text-embedding-3-small` / top_k 6, floor 0.40, strong 0.45 |
| Settings and role | `ALLOW_TEST_INDEX=true`, `PDF_READER=pdfium`; Staff default |

## Corpus

18 answerable test-index documents, 0 BPL-confirmed (`askbpl-corpus-report --strict`: nothing to reconcile). Unchanged
since `e3c8add`.

## Automated tests at the freeze

Backend **1494 passed, 1 skipped**; web **56 passed**; tsc and build clean.

## Live evaluation (`--repeat 3`, Staff default)

| File (`packages/orchestrator/eval_data/results/`) | Set | Result |
|---|---|---|
| `eval_20261101T181817Z_c0f1c48_live_default-staff.json` | client (30) + team (7) | client 26 PASS / 1 FAIL / 3 REVIEW / 0 BLOCKED; team 7/7; citations 134/134; PII and crisis pass |
| `eval_20261101T182713Z_c0f1c48_live_default-staff.json` | robustness (39) | 34 PASS / 5 FAIL; citations 119/119 |

The result files are git-ignored; copies are in the project archive (`evidence/eval_results/`). PASS is an automated
check, not proof an answer is correct; no person has scored these answers.

## Compared with the previous baseline (`e3c8add`), question by question

- **Client and team: 35 of 37 identical.** BPL-FR-01 failed 1 of 3 (the intermittent citation-check refusal: 2 in 14
  runs over 2026-10-31 and 2026-11-01). BPL-AL-05 refused 0 of 3 (was 1 of 3; known unstable).
- **Robustness: 30 of the 31 original cases identical;** ROB-MS-02 refused once in 3 (it accepts either outcome, still
  PASS). The 8 GRD-10 probes added in patch 0040 all PASS. The same 5 known FAILs.
- **Conclusion:** patches 0038 to 0042 changed no answer. (The gates they changed trigger only on the two security
  cases; the other patches were evaluation data, the web demo and documentation.)

## Known defects and open findings at the freeze

As listed in `docs/BASELINE_2026-10-31.md`, unchanged: ROB-ST-01, ROB-ST-04, ROB-MD-01, ROB-CF-01, ROB-W1-04; BPL-MS-05,
UC-05, AL-05 awaiting a BPL decision; BPL-FR-01 intermittent; union omission in general discipline answers; small
unsupported next steps (GRD-11); split words in SRC-02 and SRC-08. Fixed since the previous baseline: the crisis gate's
coverage and the web demo's crisis card (patches 0038, 0041).

## Probe definitions changed after this run (patch 0044)

ROB-MD-01 and ROB-CF-01 were narrowed to the staff audience (team decision 2026-11-01). Scored with the new definitions,
ROB-MD-01 passes and ROB-CF-01 fails because it gives staff the patron confidentiality rule. A comparison with the robustness
file above will therefore show ROB-MD-01 moving from FAIL to PASS; that is the definition change, not a change in answers.

## How to compare

```
cd packages/orchestrator
python ../../scripts/compare_runs.py eval_data/results/eval_20261101T181817Z_c0f1c48_live_default-staff.json <new client+team run>.json
python ../../scripts/compare_runs.py eval_data/results/eval_20261101T182713Z_c0f1c48_live_default-staff.json <new robustness run>.json
```
