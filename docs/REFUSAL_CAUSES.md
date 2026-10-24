# Refusal causes (RTG-6, patch 0011)

Staff see one plain sentence. The log records the real cause. The two are kept apart on purpose:
the UX specification says not to show "why the model refused" with technical terms or classification labels.

## Causes and how each is detected

| Cause | Detected by | Staff see | Status |
|---|---|---|---|
| `absent_source` | No eligible chunk reached the similarity floor | "I could not find enough approved policy information to answer reliably." | Detected |
| `weak_evidence` | A chunk reached the floor but the margin rule failed, **or** the model declined | Same sentence as above (deliberately identical) | Detected |
| `ambiguous_authority` | Relevant vectors exist but their document may not be cited (unconfirmed, blocked, superseded) and they reach the floor | "...has not been confirmed as current..." | Detected |
| `legal_disciplinary_judgment` | Intent-guard legal patterns | "I cannot give legal advice or judge an individual..." | Detected, narrow patterns |
| `human_decision_required` | Intent-guard bypass/decision patterns | "That is a decision for a person..." | Detected, narrow patterns |
| `citation_unverified` | Answer drafted, but citations missing, not retrieved, or to an ineligible document | "I could not confirm an answer would match the approved policy text..." | Detected (not one of the eight) |
| `private_employee_details` | Intent-guard patterns for questions about what happened to **other people** ("has anyone been disciplined", "how many staff were fired", "who was suspended", "is my manager being investigated") | "I cannot share or discuss disciplinary or personnel matters involving individual employees..." | Detected (patch 0012), narrow patterns |
| `sensitive_content` | **Not detected yet** (PII and crisis gates have their own responses) | draft wording only | Next patch |
| `unverified_current_operations` | **Not detected yet** | draft wording only | Next patch |

All wording is DRAFT pending BPL approval (SAF-7) except the first sentence, which is the UX specification's own.

## Technical failures are no longer refusals

| Cause | HTTP | Previously |
|---|---|---|
| `retrieval_unavailable` (Pinecone error) | 503 | 200 refusal "couldn't locate relevant policy excerpts" |
| `generation_unavailable` (no model key) | 503 | 200 refusal |
| `model_output_invalid` (reply not a JSON object, or empty answer) | 502 | 200 refusal "could not safely verify citations" |

Body: `{"type": "error_unavailable", "detail": "service_unavailable", "message": "...", "request_id": "..."}`.
The frontend already shows `message` for 502/503/504. An outage can no longer score as a passing refusal in `askbpl-eval`
(it scores as `error`).

## Reading the log

Each completed ask logs one JSON line (`event: ask_completed`):

* `refusal_reason` is the cause above (replaces the old `NO_GROUNDING` / `CITATION_VERIFICATION_FAILED`). `PII_DETECTED` is unchanged.
* `refusal_stage`: `intent_guard`, `retrieval_gate`, `model`, `citation_check`, `retrieval`, `generation`.
* `technical_failure`: set only for the three technical causes; `refusal` is then `false`.

Since patch 0018 a question that reaches the retrieval gate also logs a separate `event: retrieval_gate` line with the gate's scores (best, second, chunks at the floor). It is log-only and shares the `request_id`. See `docs/SCORE_REPORT.md` and `askbpl-score-report`.

```bash
grep '"event": "ask_completed"' app.log | grep '"refusal_reason"'
```

Neither field is in the API response or stored in the database (no migration).

## Behaviour changes to know about

1. A model that explicitly refuses now returns `refusal_oo_corpus` with the not-enough-information sentence. Before, a refusal that also listed
   citations returned `refusal_citation_invalid`; that type is now used only for a real citation failure.
2. The three technical failures above are 5xx instead of 200.
3. `ALLOW_TEST_INDEX=false` (go-live): questions that matched test-index documents now refuse as `ambiguous_authority`, not `absent_source`.
4. A model reply that is a JSON array or string no longer crashes the request; it is `model_output_invalid`.

## Known limits

* Legal, private-details and human-decision detection is wording-based. A paraphrase can slip through, and a policy question phrased like a history question can be refused (it then gets the supervisor referral). The private-details patterns need a past-event auxiliary (has/was/did...), so "what happens if I violate this?" and "can an employee be fired for...?" are still answered.
* Order when several match: legal advice, then private details, then human decision. The first one chooses the wording.
* The guard refuses before retrieval, so it cannot tell which policy the question meant. It does not fix the separate problem of a question about a policy that is not indexed being answered from a neighbouring policy.
* `ambiguous_authority` only fires when the excluded vector still exists in Pinecone. A document that was never ingested (for example the scanned COI policy before activation) looks like `absent_source`.
* The absent/weak boundary uses `GROUNDING_THRESHOLD` (the floor). It was tuned on 8 documents (GRD-2); the split is only as good as that threshold.
