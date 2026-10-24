# Ask BPL evaluation set and runner (PRD EVAL-3/5, Document 06)

## What is here
| File | Purpose |
|---|---|
| `client_questions.csv` | The client's 30 questions, **verbatim and in original order**, IDs `BPL-MS/UC/AL/CI/FR/VM-01..05`. Wording is frozen: a test fails if any question text changes. Do not edit it. |
| `regression_cases.csv` | Team-created cases (`REG-*`, `SEC-*`). Kept separate; never blended into the client 30 results. |
| `glossary_cases.csv` | Glossary probes (patch 0016): GLO-01..04. Run with `askbpl-eval --set glossary` (or `--only GLO-01`). **Never part of `--set all`**, so the client-30 and team-set baselines stay comparable. GLO-02 and GLO-03 are baseline probes for the unlisted-acronym decision: a FAIL there is evidence, not a regression. |
| `robustness_cases.csv` | GRD-12 robustness probes (patch 0017): `ROB-ST` similar titles and `ROB-ST-04` version drift (the two technology policies), `ROB-CF` and `ROB-MD` conflicting audiences and multi-document, `ROB-LD` long document, `ROB-MS` silent policy (no figure may be invented), `ROB-EX` and `ROB-TH` exceptions and thresholds, `ROB-UI` policies supplied but not indexed (wrong-policy substitution), `ROB-AC` acronyms. Run with `askbpl-eval --set robustness --repeat 3`. **Never part of `--set all`.** Every reference quote is checked verbatim against the supplied PDFs by a test. A FAIL here is evidence about the system, not automatically a defect: read the `note` column first. |
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

## Keyword checks: plain and `re:` tokens
`must_include` / `must_not_include` hold tokens separated by `|`. A plain token is a case-insensitive substring. A token
starting with `re:` is a case-insensitive regular expression (use it to catch an invented number of days or an age, which
substrings cannot). Alternation is allowed inside a group, e.g. `re:\b(\d+|two)\s+weeks\b`; a `|` outside any group or
bracket separates tokens. Only the question text is frozen, not these columns.

BPL-MS-05 and BPL-UC-05 carry such guards: the policies give no number of days and no age, so any figure in the answer
is invented and the case FAILs. An honest "the policy does not specify" answer still shows as REVIEW for a human.

## `must_cite_source` (optional column, patch 0017)
`SRC-nn` ids, `|`-separated. For an **answer**, the set of cited sources must equal this set. A citation to the neighbouring policy
(for example Technology Use cited for an employee question) fails, and so does a multi-document answer that cites only one of its
two sources. Refusals are not checked. The warning names what was cited and what was expected. A citation with no source id
cannot satisfy the rule. Older files without the column load unchanged. The client 30 do not use it.

## Score report (patch 0018)
`askbpl-score-report <run>_live.json --log <run>_app.log` joins a recorded run to its app log by `request_id` and shows each
ask's retrieval-gate scores next to its expected class. Read-only. See `docs/SCORE_REPORT.md`.

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
