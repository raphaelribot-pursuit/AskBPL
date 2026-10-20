# Approved glossary (patch 0016; PRD GLO-1 to GLO-6)

Staff write acronyms the policies spell out ("DPS" in the question, "Department of Public Safety" in the policy). The
glossary lets the **search** bridge that gap, using only definitions BPL has approved. It cannot answer a question.

## What it does, and what it cannot do
- Only entries in `config/glossary.yaml` with `status: approved` are used. `draft` and `conflict` entries are kept for
  review and never match. An approved entry must have an expansion, a source, `approved_by` and `approved_on`, or the
  file is rejected (`askbpl-glossary-check` says which entry and why).
- When an approved term appears in a question, its expansion is **added to the search query only**:
  `What does DPS do? (DPS = Department of Public Safety)`. The model still receives the staff member's own words.
  Staff never see the expansion and it is never cited (GLO-6). The grounding gate is unchanged, so a glossary match
  cannot turn weak evidence into an answer.
- Short ALL-CAPS terms ("CBH", "MAC") match only in capitals and only as whole words, so "Mac" the computer or
  "MACHINE" never fire them. Phrases and aliases match in any case. List lower-case spellings as aliases.
- If the question already spells the expansion out, nothing is added. With no approved entries the query is identical
  to the question, byte for byte (the file ships that way).
- The follow-up rewriter is told never to expand or guess an acronym.
- **Unlisted acronyms are only counted in the log in this patch** (GLO-2 behaviour is a team decision, below). A
  `glossary` log line carries counts only: `matched_terms`, `unlisted_acronyms`, `unlisted_not_in_evidence`. It never
  contains the question or the acronym. `unlisted_not_in_evidence` counts question acronyms that appear in none of the
  retrieved policy text.
- A broken glossary file is logged as an error and treated as empty; questions are still answered.

## Owner and update process (GLO-3)
- **Owner of definitions:** BPL must name one (PRD input D-03). Until named, the glossary stays empty.
- **Review coordination:** Bath Bilissalou prepares the candidate list and collects BPL's decisions.
- **To add or change a term**
  1. BPL approves the term, expansion and source in writing.
  2. Edit `config/glossary.yaml` on a branch. Fill every field; keep disagreements as `status: conflict`.
  3. `askbpl-glossary-check` must print `OK`; `python -m pytest -q` must pass.
  4. Run `askbpl-eval --set glossary` and then `askbpl-eval --repeat 3`. Record the commit and results.
  5. Merge by the normal patch process. The file is read when the app starts; restart to pick up a change.
- Never approve a term because a workbook cell says "Verified" (GLO-5): both workbooks are drafts.

## Preparing the review list (read-only)

    askbpl-glossary-candidates --general "BPL_Acronyms_Institutional_Terms_ in general.xlsx" \
        --policy "BPL_Acronyms_and_Library_Terms_used in policies.xlsx" \
        --pdf "path/to/Policy.pdf" ... --eval-csv eval_data/client_questions.csv eval_data/regression_cases.csv \
        --acronyms-only --csv /tmp/glossary_review.csv

It ranks terms by use in the policies and eval questions (3 per eval question, 2 per mention in policy text, 1 per
spelled-out form), shows where the two workbooks disagree, which meanings are unknown and which rows lack a source,
and writes every candidate with **blank** review columns (decision, approved_expansion, aliases, owner, approved_by,
approved_on, notes). It approves nothing and never writes `glossary.yaml`. "Spelled out" counts the long form in policy
text, so a common word ("development" for DEV) inflates it: read the list, do not trust the score.

## Evaluating it (GLO-4)
`eval_data/glossary_cases.csv`, run with `askbpl-eval --set glossary` (never part of `--set all`, so the client-30
and team baselines stay comparable):
- GLO-01 an undefined acronym must not be given an invented expansion.
- GLO-02, GLO-03 invented acronyms (XQZ, BWQ): baseline probes for the unlisted-acronym decision. A FAIL means the
  system answered around an unknown acronym; that is evidence, not a regression.
- GLO-04 a before/after pair for DPS: run with an empty glossary, then after BPL approves DPS.
Cases that need an approved term (alias, case rule) are added when BPL approves one.

## Decisions still open
1. Which terms BPL approves, and who owns them.
2. What the assistant does with an unlisted acronym (GLO-2): (a) prompt wording only; (b) refuse with "I don't recognize
   that term" when a question acronym is unlisted and appears in no retrieved text; (c) (b) plus a new refusal cause.
   Recommendation: (b). Decide after reading the `glossary` log counts and GLO-02/03 results.
3. Expected class for the glossary eval cases.
4. Who owns the small allowlist of all-capital words that are not BPL acronyms (`common_words_allowlist`).

## Limits
- It only helps the search; it never defines a term for staff or counts as evidence.
- Passing tests show pipeline behaviour, not that answers are correct or that an approved definition is current.
- Whether it improves retrieval is unproven until a live `--repeat 3` run.
