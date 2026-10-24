# Score report: evidence for the retrieval-gate thresholds (patch 0018, PRD GRD-2)

**What it is.** `askbpl-score-report` is a read-only command. It joins a recorded `askbpl-eval` run to the app log it
wrote and shows, for every ask, what the retrieval gate saw next to what the case expected. It exists so the team can
judge the thresholds (floor 0.40, strong 0.45) from data instead of from one case at a time.

**What it does not do.** It changes no threshold, prompt, glossary, database row or configuration. It never opens the
database (a test checks this). It does not say what the thresholds should be.

## The gate in one paragraph
After the search, a question goes on to the model only if **two or more chunks score at or above the floor (0.40)** or
**the best chunk scores at or above the strong threshold (0.45)**. Otherwise it is refused as `weak_evidence` or
`absent_source` at the `retrieval_gate` stage, and no model call is made. The values live in `config.py`
(`grounding_threshold`, `grounding_strong_threshold`).

## What 0018 added to the log
One new log line per question that reaches the gate: `{"event": "retrieval_gate", ...}` with `request_id`,
`chunks_returned`, `top_score`, `second_score`, `chunks_at_floor`, `floor`, `strong`, `passed`, `passed_by`
(`strong`, `two_at_floor` or null). Numbers and flags only: no question text, no chunk text, no title (a test checks
the exact set of fields). It reports the gate's decision and takes no part in it. Before 0018 the log had only
`top_score`; that is why an old log cannot show the second score.

## Run it
From `packages/orchestrator`, venv active. Use a **live** results file and the app log written by the same run (same
timestamp in the file names under `eval_data/results/`).

    askbpl-score-report eval_data/results/<run>_live.json --log eval_data/results/<run>_app.log
    askbpl-score-report a_live.json b_live.json --log a_app.log b_app.log     # several runs together
    askbpl-score-report <run>_live.json --log <run>_app.log --summary-only --csv /tmp/scores.csv

Options: `--floor` and `--strong` override the values recorded in the results file; `--summary-only` skips the per-ask
table; `--csv` writes the table. Exit code 0 means it ran (findings are not errors); 2 means it could not read its input.

## How to read it
1. **Per-ask table.** `expect` is what the case wants, `outcome` what happened, `status` the runner's own verdict
   (same scorer). `top`, `second`, `at_floor` come from the log; `-` means the log predates 0018.
2. **Best score by outcome.** Four groups: answered as expected; **refused when an answer was expected (over-refusal)**;
   refused at the gate when a refusal was expected (the group to protect); answered when a refusal was expected.
   Refusals made later (by the model or the citation check) are counted separately: they are not about thresholds.
3. **Over-refusals.** Each with `to_strong` (how far the best score is under 0.45) and `to_2nd_chunk` (how far the
   second-best score is under 0.40): the two ways through the gate.
4. **What-if.** For cut-offs from the floor to the strong threshold: how many recorded over-refusals a lower
   single-chunk cut-off would have admitted, and how many recorded expected refusals it would have admitted too. If the
   highest-scoring expected refusal scores above some over-refusals, the report says the groups overlap: score alone
   cannot separate them on this data.

## Limits (read before using it in a decision)
- It reports recorded runs only. A small sample, and the expected classes of AL-05, MS-05, UC-05 and the silent-policy
  probes are still open decisions, so "expected refusal" is not settled for all of them.
- Admitting a run only lets the model see the evidence. The model can still refuse, and an admitted answer can still be
  wrong. Judge admitted cases by reading them.
- Scores are embedding similarities. Changing the embedded text (for example adding the policy title) changes every
  score and makes earlier runs incomparable.
- Any threshold change is a model-facing change: one change per run, a full before-and-after run of the client 30, the
  team 7 and the robustness set (`--repeat 3`), and a decision logged first.

## Suggested use for GRD-2
Run the client 30 plus team 7, then the robustness set, with a build that includes 0018 (so the log has the gate line).
Keep the three result and log pairs together. The cases to protect in any change: ROB-UI-01 to 04, GLO-02, GLO-03 and
the BPL-xx-05 cases. Record the numbers in the baseline record (BASE-8) whether or not anything is changed.
