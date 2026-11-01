# Design note: claim-level grounding (GRD-11)

**Status:** proposal for team decision; no code. **Date:** 2026-11-01. **Requirements:** GRD-11 (each material claim
is supported by an eligible retrieved passage), GRD-1 / NFR-1 (closed corpus, no ungrounded answer), GRD-6 / UX-10
(show evidence), RTG-4 / RTG-7 (no invented contacts; neutral referral). **Baseline:** `docs/BASELINE_2026-10-31.md`.

## 1. The problem, with evidence

Today the model returns a JSON object (`answer`, `refuse`, `cited_chunk_ids`) and `verify_citations`
(`services/citation_verifier.py`) checks that every cited chunk was retrieved, that the model did not refuse, and that
the answer is not empty. Its own docstring says what it does not check: whether each claim is supported by the cited
passage. So an answer can cite the right chunk and still add a sentence that no passage says.

Seen on the 2026-10-31 baseline, in answers that passed every automated check:

| Case | Sentence the policy does not support | Cited policy |
|---|---|---|
| ROB-W1-05 | "You'd need a colleague to handle that transaction for you." | Custodianship (says only that staff may not check out their own materials) |
| ROB-W1-03 | "...or reach out to a Slack admin if it truly warrants a full-channel alert." | Internal Communications (says only that admins may use @channel) |

These are small, plausible, helpful-sounding additions. That is what makes them risky: staff read them as policy.

A warning against judging by eye: a third sentence suspected while writing this note (ROB-UI-02, "being sent home to
change means you generally won't be paid for that time") turned out to be supported. The Dress Code says employees
sent home "generally will not be entitled to compensation for time spent away". Plausible-looking additions can be in
the policy, and real additions can look plausible, which is why Phase 0 calibrates the check against people.

**Not in scope:** omissions. GRD-11 asks whether what is said is supported, not whether everything relevant is said.
The union-staff omission (ROB-UI-03) is a completeness problem with its own fix and probe (ROB-W2-02).

## 2. What the Anthropic API offers natively

From the current Claude API documentation (search results, citations), checked 2026-11-01:

- **`search_result` content blocks** with `"citations": {"enabled": true}` can be sent directly in a user message. Each
  block has `source`, `title` and a `content` array of text blocks. No beta header. Supported on `claude-sonnet-4-6`
  (the model in use) and every current model. The installed SDK (anthropic 1.12.0) has `SearchResultBlockParam` and
  `CitationsSearchResultLocation`.
- **Claude's reply comes back as several `text` blocks.** A block that draws on a search result carries a `citations`
  list of `search_result_location` entries: `search_result_index`, `start_block_index`, `end_block_index`,
  `cited_text` (the exact text of the cited blocks), `source` and `title`. `cited_text` is not billed as output.
- **Granularity is the text block:** Claude cites whole blocks, never substrings. Splitting each excerpt into
  one-sentence blocks gives sentence-level citations.
- **Constraints:** citations are all-or-nothing per request; citations cannot be combined with structured outputs
  (`output_config.format`, which returns a 400); `search_result` blocks may only appear in user messages; text only.
  `cache_control` can sit on a search result block.

## 3. Options

| | A. Native citations | B. Second-pass verifier model | C. Lexical / embedding match | D. Prompt rule only |
|---|---|---|---|---|
| How | Send excerpts as `search_result` blocks split into sentences; every text block of the answer must carry a citation | After generation, a second model labels each answer sentence supported / unsupported against the excerpts | Compare each answer sentence with the excerpts by word overlap or embedding similarity | Tell the model to state only what the excerpts say and to take next steps only from the routing block |
| Verifies support? | Partly: proves *which* sentence the model says it used, and exposes uncited text. Does not prove the paraphrase is faithful | Yes, as a judgment; the judge can also be wrong | Weakly: plain-English paraphrase defeats overlap; similarity is not support | No; this was tried in 0006 and unsupported sentences still appear |
| Extra calls / latency | None | One extra model call per answer (about 1-2 s) | Embedding calls, or none for overlap | None |
| Cost per question | About the same as today | Small: a few thousand input tokens per check; on `claude-haiku-5-5` ($0.10 / $0.50 per MTok up to 100K) well under a tenth of a cent | Negligible | None |
| Change to the answer contract | Yes: the JSON contract (`answer` / `refuse` / `cited_chunk_ids`) is replaced by cited prose plus a refusal signal; prompt rewrite | None | None | Prompt only |
| Evidence for staff (GRD-6) | Exact cited sentences per claim: the "Show evidence" view can highlight them | Labels only | None | None |
| Main risk | A large model-behaviour change (refusals, tone, citation density all move); needs a full re-evaluation | Over-refusal if the judge is strict, missed claims if lenient; a second model to calibrate | False alarms on good paraphrase, silent misses | Gives no assurance; GRD-11 stays Not started |

## 4. Recommendation

**Use A as the mechanism, B as the measuring instrument, and decide the enforcement rule from data.** In order:

**Phase 0: measure first (no product change).** Build a claim-support check for the evaluation, not for staff: for each
recorded answer, split it into sentences and have a judge model label each one supported, unsupported, or not a
claim (a referral, a caveat). Calibrate the judge against people: the team labels a sample of about 100 sentences
from the baseline runs, and the judge must agree on most of them, above all on "unsupported", before its numbers are
trusted. Output: the baseline rate of unsupported sentences per answer on `e3c8add`, by case. This is the number the
next phases must move. It runs on recorded answers, so it costs only judge calls.

**Phase 1: native citations behind a setting (`GENERATION_CITATIONS`, off by default).**
- Send each retrieved chunk as one `search_result` block: `source` = chunk id, `title` = document title, `content` =
  the chunk's sentences as separate text blocks (the sentence splitter from patch 0014 already exists).
- Map `search_result_index` back to the chunk id, so `verify_citations` keeps working unchanged (cited chunks must be
  retrieved), and the eligibility guard still applies.
- Replace the JSON contract with cited prose plus a fixed refusal signal (for example the reply is exactly
  `INSUFFICIENT_EVIDENCE` when the excerpts do not answer). Native citations cannot be combined with structured
  outputs, so the reply cannot also be schema-constrained JSON.
- Take routing and caveats out of the model's text: the referral card (RTG) and the test-index label are already
  rendered by the server, so the model does not need to write "check with your supervisor". The answer is then
  supposed to be fully cited.
- Evaluate with the setting on against the baseline: `compare_runs.py` on both sets (no PASS-to-FAIL), the Phase 0
  unsupported rate, refusal rate on answerable questions, latency.

**Phase 2: the enforcement rule (team decision, from Phase 1 data).** What happens to an uncited sentence:
(a) remove it before display; (b) show it marked "not from the policy text"; (c) refuse the whole answer if any
sentence is uncited. (a) is the likely default; (c) is the safest and most likely to over-refuse. Add B as a runtime
check only if Phase 1 leaves a measurable unsupported rate that citations alone cannot catch (faithless paraphrase of a
cited sentence).

**Why not B alone:** it leaves the generation untouched and adds a second model in the critical path whose errors
become refusals or misses, without giving staff better evidence. **Why not C:** answers are deliberately plain
English, so overlap misses paraphrase and similarity does not mean support. **Why not D alone:** already tried (0006).

## 5. What would change in the code (Phase 1 only)

| File | Change |
|---|---|
| `services/generation.py` | Build `search_result` blocks instead of the `RETRIEVAL_BLOCK` JSON; new prompt for cited prose; parse text blocks and citations; refusal signal |
| `services/citation_verifier.py` | Unchanged rule; fed chunk ids mapped from citations. New: count of uncited text blocks |
| `services/ask_service.py` | Pass the setting; log uncited-block counts (counts only, as the glossary log does) |
| `api` response / web-demo citation card | Optional: return `cited_text` per claim so "Show evidence" highlights the exact sentence |
| `evals` | Claim-support metric (Phase 0); runs recorded with the setting on and off |

No migration. Behind a setting, so the current path stays the default until the team decides.

## 6. Decisions needed

1. Approve the phased plan, Phase 0 first.
2. Who labels the ~100 sentences for judge calibration, and by when.
3. Phase 2 rule: remove, mark, or refuse uncited sentences (decide after Phase 1 data).
4. Whether the answer may still carry a short referral sentence, or referrals come only from the server-rendered card.
5. Judge model for Phase 0. The current Haiku (`claude-haiku-5-5`) is the low-cost choice. The answer model
   (`claude-sonnet-4-6`) stays as it is: changing it would be its own evaluated change, not part of this one.

## 7. Risks and limits

- **Citations show what the model says it used, not that it paraphrased faithfully.** Phase 0's judge is what
  measures faithfulness; it can be wrong, which is why it is calibrated against people first.
- **A contract change moves everything.** Refusal wording, length and tone may shift; one change per run, and the
  Phase 1 run compares against `e3c8add` question by question.
- **Over-refusal.** Strict enforcement can turn good answers into refusals; the client set's refusal rate on answerable
  questions is watched in every run.
- **Unchanged by design:** retrieval, thresholds, eligibility, the role lens wording, PII and crisis gates.
