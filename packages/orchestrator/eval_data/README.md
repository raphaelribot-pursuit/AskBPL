# Ask BPL evaluation set and runner (PRD EVAL-3/5, Document 06)

## What is here
| File | Purpose |
|---|---|
| `client_questions.csv` | The client's 30 questions, **verbatim and in original order**, IDs `BPL-MS/UC/AL/CI/FR/VM-01..05`. Wording is frozen: a test fails if any question text changes. Do not edit it. |
| `regression_cases.csv` | Team-created cases (`REG-*`, `SEC-*`). Kept separate; never blended into the client 30 results. |
| `results/` | Run output (JSON + CSV). Git-ignored by default; commit a run only deliberately, as BASE-8 / AC-10 evidence. |

## Run it
From `packages/orchestrator`, venv active, `.env` loaded:

    askbpl-eval                         # client 30 + team cases, against the real pipeline (real API keys, small cost)
    askbpl-eval --set client            # only the 30
    askbpl-eval --only BPL-AL-03 REG-AL-02 --repeat 5   # model output varies: repeat risky cases
    askbpl-eval --replay eval_data/results/<run>.json   # re-score a recorded run offline: free, deterministic
    askbpl-eval --list                  # show the cases without asking anything

Needs the seeded demo tester (`askbpl-seed`) and documents ingested + `askbpl-apply-inventory` already run.
Each question is asked on its own with no chat history. Each live question writes anonymous telemetry rows to the
database, so run against a development database. Exit code is 1 if any case FAILS or ERRORS (REVIEW and BLOCKED do not).
The app's own log, including tracebacks, goes to `eval_data/results/eval_<time>_app.log`; the console shows only the report.

## How to read the result
| Status | Meaning |
|---|---|
| PASS | All automated checks hold. Marked *provisional* while the cited sources are not BPL-confirmed (authority pending / test index). |
| FAIL | Wrong outcome, missing or invalid citation, missing test-index label, a required fact absent, or forbidden text present. |
| REVIEW | A human must look: an out-of-scope question was answered (Document 06 s.5), or a blocked policy's question was answered. |
| BLOCKED | The question's own policy is not answerable (not stored, blocked, excluded). Reported as NOT EVALUABLE, never as a pass or a fail. |
| ERROR | The system itself failed (timeout, 5xx, upstream API error). Not a judgement on the answer: look at the app log and rerun. Counts against the exit code. |

**These are automated checks, not answer-correctness scores.** Correctness needs a BPL-validated reference answer and
the five 1-5 human dimensions (Accuracy, Grounding, Completeness, Clarity, Boundary handling), which are left **blank**
in the CSV for evaluators. No BPL-approved answer key exists yet.

## Reference records
`reference_status` is `PENDING` unless an engineer extracted a quote from the source PDF
(`ENGINEER_PREPARED_PENDING_BPL`: Annual Leave AL-01..04 and the matching regression cases). `must_include` /
`must_not_include` are simple keyword checks derived from that quote; they catch obvious errors, not subtle ones.
Bath Bilissalou owns the independent reference answers; replace `PENDING` rows as they are prepared and approved.

## Limits
- `--replay` cannot detect model drift (nothing is re-asked). Use a live run for that.
- Live runs vary run to run. One clean pass is weak evidence; use `--repeat`.
- A run records the commit, whether the working tree was dirty, the model names, the system-prompt hash and the
  retrieval settings, so results can be compared fairly across changes.
