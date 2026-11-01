# Proposal: claim-level grounding (GRD-11)

> **Status: proposal, not built.** Decision 2026-11-01 (team, option B): not built before the capstone code freeze. It
> is recorded as a known limit in `docs/HANDOVER.md` and handed to BPL as an option to invest in later. Nothing in the
> running system depends on this page. First written 2026-11-01 (patch 0037, on branch `design/grd-11-claim-grounding`);
> brought to `main` and expanded for BPL in patch 0046.

**For BPL readers:** sections 1, 4, 6 and 8 are enough to decide whether to invest. Sections 2, 3, 5 and 7 are for the
engineer who would build it.

**Requirements:** GRD-11 (each material claim is supported by an eligible retrieved passage); GRD-1 / NFR-1 (closed
corpus, no ungrounded answer); GRD-6 / UX-10 (show evidence); PRD acceptance item AC-17 (claim support: a sample of
answers spot-checked, zero unsupported material claims). **Baseline to compare against:**
`docs/BASELINE_2026-11-01_freeze.md`.

## 1. The problem, in plain terms

Ask BPL already guarantees that **every citation points to a passage it really retrieved** (`services/citation_verifier.py`).
It does **not** check that **each sentence of the answer is supported by those passages**. So an answer can cite the right
policy and still add one plausible sentence the policy never says. Staff are likely to read that sentence as policy.

Seen in answers that passed every automated check:

| Case | Sentence the policy does not support | Cited policy |
|---|---|---|
| ROB-W1-05 (2026-10-31) | "You'd need a colleague to handle that transaction for you." | Custodianship (says only that staff may not check out their own materials) |
| ROB-W1-03 (2026-10-31) | "...or reach out to a Slack admin if it truly warrants a full-channel alert." | Internal Communications (says only that admins may use @channel) |
| ROB-CF-01 (2026-11-01) | "BPL won't share your specific browsing records except as required by law" said to a **staff** member | Technology Use: a real sentence, but it is the **patron** rule; the staff policy says employees have no expectation of privacy |

The third row is a related failure: a supported sentence applied to the wrong audience. Probe ROB-CF-01 now fails on it
(patch 0044). Native citations (below) would make it visible, because the cited sentence would come from the public
policy; whether to block it is a rule to choose (section 4, phase 2).

**A caution against judging by eye:** a fourth sentence suspected while writing this note ("being sent home to change
means you generally won't be paid for that time", ROB-UI-02) turned out to be supported: the Dress Code says employees
sent home "generally will not be entitled to compensation for time spent away". Plausible-looking additions can be in the
policy, and real additions can look plausible. That is why phase 0 calibrates the check against people first.

**Further evidence, 2026-11-01 (GRD-7 attempt, patch 0061, not merged).** The team tried to keep the model's own
additions out of the answer by prompt alone: a separate, labelled "suggestion" field for anything the excerpts do
not state, with the answer limited to what they literally say. In three prompt revisions and 45 live answers the
model never used the field (`"suggestion": null` every time) and kept inferences in the answer, for example "Someone
else needs to handle that transaction for you" (ROB-W1-05; the Custodianship policy says only that staff may not
check out or check in their own materials). The model reads such steps as part of the policy. This supports option D's
row in section 3 (a prompt rule gives no assurance) and the case for a separate check (phase 0, then native
citations). The attempt is kept on branch `feat/grd7-suggestion-note` and in the project archive.

**Not in scope:** omissions. GRD-11 asks whether what is said is supported, not whether everything relevant is said
(for example, general discipline answers do not mention the Union Contract; probe ROB-W2-02 covers that separately).

## 2. What the Anthropic API offers natively (checked 2026-11-01)

From the Claude API documentation for search results and citations. **Re-check before building**: the API evolves.

- **`search_result` content blocks** with `"citations": {"enabled": true}` can be sent directly in a user message. Each
  block has `source`, `title` and a `content` array of text blocks. No beta header. Supported on `claude-sonnet-4-6`
  (the model in use at the freeze) and on every current Claude model. The installed SDK (anthropic 1.12.0) has
  `SearchResultBlockParam` and `CitationsSearchResultLocation`.
- **The reply comes back as several `text` blocks.** A block that draws on a search result carries `citations` of type
  `search_result_location`, each with `search_result_index`, `start_block_index`, `end_block_index`, `cited_text` (the
  exact cited text), `source` and `title`. `cited_text` is not billed as output.
- **Granularity is the text block:** Claude cites whole blocks, never substrings. Splitting each excerpt into
  one-sentence blocks gives sentence-level citations.
- **Constraints:** citations are all-or-nothing per request; they cannot be combined with structured outputs
  (`output_config.format` returns a 400); `search_result` blocks may only appear in user messages; text only.
  `cache_control` can sit on a search result block.

## 3. Options considered

| | A. Native citations | B. Second-pass verifier model | C. Lexical or embedding match | D. Prompt rule only |
|---|---|---|---|---|
| How | Send excerpts as sentence-split `search_result` blocks; every text block of the answer must carry a citation | After generation, a second model labels each sentence supported / unsupported | Compare each sentence with the excerpts by word overlap or embedding similarity | Tell the model to state only what the excerpts say |
| Verifies support? | Partly: shows which sentence the model used and exposes uncited text; does not prove the paraphrase is faithful | Yes, as a judgment that can itself be wrong | Weakly: plain-English paraphrase defeats it | No; tried in patch 0006 and unsupported sentences still appear |
| Extra calls / latency | None | One extra call per answer (about 1-2 s) | Embedding calls, or none | None |
| Cost per question | About the same as today | Small (see section 6) | Negligible | None |
| Change to the answer format | Yes: the JSON contract becomes cited prose plus a refusal signal | None | None | Prompt only |
| Evidence for staff | Exact cited sentence per claim, so "Show evidence" can highlight it | Labels only | None | None |
| Main risk | Large behaviour change; needs full re-evaluation | Over-refusal if the judge is strict, misses if lenient | False alarms and silent misses | Gives no assurance |

## 4. Recommended plan (three phases; each is a separate decision)

**Phase 0: measure (no change to what staff see).** Build a claim-support check for the evaluation only: split each
recorded answer into sentences and have a judge model label each supported, unsupported, or not a claim (a referral, a
caveat). Calibrate it first: the team (or BPL reviewers) labels about 100 sentences from the freeze-baseline answers, and
the judge must agree on most of them, above all on "unsupported", before its numbers are trusted. **Output:** the
unsupported-sentence rate per answer on `c0f1c48`. This tells BPL how big the problem really is before anything is built.

**Phase 1: native citations behind a setting (`GENERATION_CITATIONS`, off by default).**
- Send each retrieved chunk as one `search_result` block (`source` = chunk id, `title` = document title, `content` = the
  chunk's sentences as separate text blocks; the sentence splitter from patch 0014 exists).
- Map `search_result_index` back to the chunk id, so `verify_citations` and the eligibility guard keep working unchanged.
- Replace the JSON contract with cited prose plus a fixed refusal signal (for example a reply of exactly
  `INSUFFICIENT_EVIDENCE`). Native citations cannot be combined with structured outputs.
- Keep referrals and caveats out of the model's text: the referral card and the test-index label are already rendered by
  the server, so the answer can be fully cited.
- Evaluate with the setting on against the freeze baseline (`scripts/compare_runs.py` on both sets: no PASS-to-FAIL), plus
  the phase 0 rate, refusal rate on answerable questions, and latency.

**Phase 2: the rule for an uncited sentence (decide from phase 1 data).** (a) remove it before display; (b) show it
marked "not from the policy text"; (c) refuse the whole answer. (a) is the likely default; (c) is safest and most likely
to over-refuse. Add option B (a runtime judge) only if phase 1 leaves a measurable unsupported rate that citations alone
cannot catch.

**Why not B alone:** it leaves generation untouched and puts a second model in the critical path whose errors become
refusals or misses, without better evidence for staff. **Why not C:** answers are deliberately plain English.
**Why not D alone:** already tried.

## 5. What would change in the code (phase 1)

| File | Change |
|---|---|
| `packages/orchestrator/ask_bpl_orchestrator/services/generation.py` | Build `search_result` blocks instead of the `RETRIEVAL_BLOCK` JSON; new prompt for cited prose; parse text blocks and citations; refusal signal |
| `packages/orchestrator/ask_bpl_orchestrator/services/citation_verifier.py` | Rule unchanged; fed chunk ids mapped from citations; new count of uncited text blocks |
| `packages/orchestrator/ask_bpl_orchestrator/services/ask_service.py` | Pass the setting; log uncited-block counts (counts only) |
| API response and the web demo's citation card | Optional: return `cited_text` per claim so "Show evidence" highlights the exact sentence |
| `packages/orchestrator/ask_bpl_orchestrator/evals/` | Claim-support metric (phase 0); runs recorded with the setting on and off |

No database migration. Behind a setting, so the current path stays the default until BPL decides.

## 6. Effort and cost (estimates, for planning)

| | Effort (rough) | Running cost |
|---|---|---|
| Phase 0 | 2-3 hours of people labelling about 100 sentences; about 1 day of engineering for the judge script and the metric | Under $1 per full measurement with `claude-haiku-5-5` as judge ($0.10 / $0.50 per million tokens): about 228 answers x ~3,500 input tokens |
| Phase 1 | 2-4 engineering days including tests, then one full before/after evaluation (about $3.40 per run at today's model and prices) | About the same per question as today (no extra calls; `cited_text` is not billed) |
| Phase 2 | A BPL decision plus about half a day of engineering | None extra |

Estimates assume someone familiar with this repository and the working rules in `docs/HANDOVER.md` section 6. Prices are
the Anthropic list prices on 2026-11-01; check current pricing before budgeting.

## 7. How to start (for the engineer who picks this up)

1. Read this page, `docs/HANDOVER.md` sections 5-7, and `docs/BASELINE_2026-11-01_freeze.md`.
2. Re-check section 2 against the current Claude API documentation (search results, citations) and the installed SDK.
3. Phase 0 first, on a branch: write the judge as an evaluation tool (no product change), agree the ~100-sentence
   labelling with BPL, measure on the freeze-baseline answers, and record the rate.
4. Only if BPL decides to continue: phase 1 behind `GENERATION_CITATIONS=false`, with tests for the block construction,
   the citation-to-chunk mapping and the refusal signal; deliberately break each safeguard once.
5. Evaluate live, one change per run, against the freeze baseline; read the answers, not only the totals.
6. Record the change (patch, handoff, `docs/CHANGE_LOG.md` row) as every earlier change was.

## 8. What BPL would need to decide

1. Whether to invest in phase 0 (measurement) at all, and who labels the ~100 sentences.
2. After phase 0: whether the measured rate justifies phase 1.
3. After phase 1: the rule for uncited sentences (remove, mark, or refuse).
4. Whether answers may still carry a short referral sentence, or referrals come only from the server-rendered card.
5. The judge model for phase 0 (the current Haiku is the low-cost choice). Changing the answer model is a separate
   evaluated change, not part of this one.

## 9. Risks and limits

- **Citations show what the model says it used, not that it paraphrased faithfully.** Phase 0's judge measures
  faithfulness and can be wrong, which is why it is calibrated against people first.
- **A format change moves everything.** Refusal wording, length and tone may shift; compare question by question with
  the freeze baseline.
- **Over-refusal.** Strict enforcement can turn good answers into refusals; watch the refusal rate on answerable questions.
- **Unchanged by design:** retrieval, thresholds, eligibility, the role lens wording, and the PII and crisis gates.
