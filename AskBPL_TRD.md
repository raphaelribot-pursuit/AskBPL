# Ask BPL — Technical Requirements Document (TRD)

| Field | Value |
|---|---|
| Document type | Technical Requirements Document (TRD) |
| Project | Ask BPL — AI Policy Assistant |
| Aligned to | BPL Ask BPL PRD v3 (April 29, 2026) |
| Version | 0.3 (Aligned to PRD v3) |
| Date | May 8, 2026 |
| BPL client lead | Selvon Smith — ssmith@bklynlibrary.org |
| Vizion engineering partner | Denward Lee Aulder |
| Primary audience | BPL IT (Selvon Smith — architecture validation); Vizion engineering (Denward Lee Aulder — implementation spec) |
| Status | Draft for client review |

> This document is part of the Ask BPL deliverable set. The PRD (v3, dated April 29, 2026) is the canonical scope document, approved by BPL. This document derives its scope from PRD v3 and does not exceed it. Engineering detail that goes beyond v3 is clearly labeled as Vizion-internal.

---

## 1. Introduction

### 1.1 Purpose

This Technical Requirements Document (TRD) translates the approved PRD v3 into a numbered, testable set of technical requirements. The TRD is the single artifact engineering builds against — every code path, configuration, and verification check ties back to a requirement ID listed here.

The TRD is designed to serve two audiences without forking:

- **Selvon Smith (BPL):** validate that what Vizion builds is exactly what BPL approved in v3, no more and no less. The requirement tables are the spine; each requirement names the verification method (Inspection, Test, or Demo) so Selvon can trace from PRD to acceptance.
- **Denward Lee Aulder (Vizion engineering):** an implementation spec. Where engineering detail goes beyond v3 — chunking strategy, retrieval thresholds, PII detector choice — it is marked as a callout labeled "Beyond v3 scope — Vizion-internal engineering note". Selvon is welcome to read these but does not need to approve them.

### 1.2 Scope alignment to PRD v3

This TRD covers the pilot only: 100-page Selvon-curated corpus, 10 testers across SME and non-expert groups, demo environment that does not touch BPL intranet, June 15 demo deliverable. The named pilot stack — Pinecone, OpenAI embeddings, Python orchestrator, Claude (BPL license, BPL-provided key), LangChain or LlamaIndex — is the basis for the requirements that follow.

> **v3 alignment.** PRD v3 explicitly defers the following to activation (post-pilot): SharePoint integration, BPL intranet embedding, BPL identity provider integration. These are engineered-ready in the pilot but not activated. The TRD treats them as configuration seams, not features.

### 1.3 Conventions

- **Requirement IDs:** `TRD-{AREA}-{N}`. AREA codes appear in §3 onward.
- **Priority:** P0 = required for pilot; P1 = desired but cuttable if scope tightens; P2 = activation-phase, listed for traceability.
- **Verification:** Inspection (review of code, config, or document); Test (automated or scripted); Demo (witnessed run with Selvon).

---

## 2. Architecture overview

The pilot is a single Python orchestrator backed by a Pinecone index, calling OpenAI embeddings for vectorization and Claude for generation. The orchestrator exposes an HTTP API consumed by the avatar modal in the demo environment.

### 2.1 Component map

| Component | Role |
|---|---|
| Avatar modal | Frontend widget rendered in the demo environment. Sends questions and feedback to the orchestrator over HTTPS. |
| Python orchestrator | Receives questions; runs PII gate, retrieval, generation, citation check; returns answer or refusal with routing. |
| PII gate | Pre-retrieval input filter. Rejects inputs containing PII categories listed in TRD-GRD-2. |
| Retrieval layer (LangChain or LlamaIndex) | Embeds the question (OpenAI) and queries Pinecone for top-K matching chunks. Hybrid retrieval is not required at 100 pages but the seam is open. |
| Generation (Claude) | Called with retrieval results and a closed-corpus system prompt. Uses BPL's license; BPL provides the API key. |
| Citation verifier | Post-generation check that every cited document corresponds to a chunk actually returned by retrieval. |
| Routing config | Static (build-time editable) policy-type → owning-team mapping. Selvon reviews and approves before the demo. |
| Logging & feedback store | Records request/response metadata, tester ratings, and routing outcomes. Anonymous sessions store no tester ID. |

### 2.2 Request flow (happy path)

1. Tester opens the avatar modal and submits a question.
2. Orchestrator validates the session token, then runs the PII gate. If PII is detected, return `400 PII_DETECTED`.
3. Orchestrator embeds the question via OpenAI and retrieves top-K chunks from Pinecone.
4. If no chunk meets the grounding threshold, return a refusal with routing (no Claude call).
5. Otherwise, call Claude with the retrieval results and the closed-corpus system prompt.
6. Run the citation verifier on the response. If verification fails, refuse rather than return.
7. Return the answer with citations to the modal. Log the request, response, and any feedback.

> **Beyond v3 scope — Vizion-internal engineering note.** The citation verifier and the grounding threshold are implementation-level decisions not specified in v3. They exist because v3 requires every answer to be grounded and cited (TRD-GEN-3, GEN-4). The verifier is single-digit milliseconds and runs server-side; Selvon does not need to manage or approve its mechanics, only the requirement it satisfies.

---

## 3. Authentication & session

| ID | Pri | Requirement | Verify |
|---|---|---|---|
| TRD-AUTH-1 | P0 | Testers authenticate to the demo environment using Vizion-issued credentials (email + access code). Authentication occurs over HTTPS; credentials are never logged. | Inspection |
| TRD-AUTH-2 | P0 | On successful authentication, the orchestrator issues a session token bound to the tester ID (or an anonymous marker if the tester selected anonymity at sign-in). | Test |
| TRD-AUTH-3 | P0 | Every API call to the orchestrator must include the session token in the `Authorization` header. Calls without a valid token return 401. | Test |
| TRD-AUTH-4 | P0 | Session tokens expire after 8 hours of inactivity and must be re-issued via re-authentication. | Test |
| TRD-AUTH-5 | P2 | At activation, the auth seam defers to BPL's identity provider (Entra ID via SharePoint identity). Endpoint shapes do not change. | Inspection (post-pilot) |

> **Beyond v3 scope — Vizion-internal engineering note.** The session token is a signed JWT carrying `{ tester_id | anonymous, issued_at, expires_at }`. The signing key lives in the orchestrator's secrets store. The pilot does not use refresh tokens; testers re-authenticate after 8 hours. This is sufficient for a 6-week pilot with 10 testers and avoids managing a refresh-token revocation surface that BPL would need to inherit at activation.

---

## 4. Corpus ingestion

PRD v3 fixes the corpus at 100 pages curated by Selvon. Ingestion runs ahead of any tester sessions and re-runs whenever Selvon updates the curated set.

| ID | Pri | Requirement | Verify |
|---|---|---|---|
| TRD-IGN-1 | P0 | The system must accept curated documents in PDF, DOCX, and Markdown formats. Documents that fail to parse are surfaced in the build-team console (status: Failed) and not silently dropped. | Test |
| TRD-IGN-2 | P0 | Ingestion produces text chunks with metadata: source document, section heading (if present), policy type, and document version. Chunks are stored in Pinecone with these as metadata. | Inspection |
| TRD-IGN-3 | P0 | Each document carries exactly one policy type, drawn from the routing configuration. Documents without a valid policy type are rejected at ingest. | Test |
| TRD-IGN-4 | P0 | Re-ingestion is idempotent. Running it twice on an unchanged corpus produces the same index state. | Test |
| TRD-IGN-5 | P0 | The build-team console exposes ingestion status per document and the timestamp of the last successful run. | Demo |

> **Beyond v3 scope — Vizion-internal engineering note.** Chunking strategy is a build-time decision. Default is recursive split at 800 tokens with 100-token overlap, anchored to section headings where present. For a 100-page corpus, this produces ~300–400 chunks — small enough that no advanced indexing is required. The seam is open for finer chunking or hybrid retrieval if the pilot data shows retrieval misses.

---

## 5. Retrieval

| ID | Pri | Requirement | Verify |
|---|---|---|---|
| TRD-RET-1 | P0 | Each question is embedded using the same OpenAI embedding model used at ingest (model identifier pinned in config). | Inspection |
| TRD-RET-2 | P0 | Pinecone is queried for the top-K most similar chunks (default K=6). Results include similarity scores. | Test |
| TRD-RET-3 | P0 | The orchestrator applies a grounding threshold: if no chunk's similarity exceeds the threshold, the system returns a refusal without calling Claude. | Test |
| TRD-RET-4 | P0 | The retrieval layer (LangChain or LlamaIndex) is selected at build time. The orchestrator interface does not depend on the choice; either can satisfy these requirements. | Inspection |
| TRD-RET-5 | P1 | Retrieval results passed to generation must include source document name, section, and chunk identifier so the citation verifier can validate the response. | Inspection |

> **Beyond v3 scope — Vizion-internal engineering note.** The grounding threshold is calibrated during build against a small set of known-good and known-bad questions Selvon supplies. The threshold is held in config — not hardcoded — so it can be tuned during the pilot if refusal rates skew. Hybrid retrieval (BM25 + vector) is not required at 100 pages but the orchestrator interface is shaped to accept a lexical pass without surgery.

---

## 6. Generation & grounding

| ID | Pri | Requirement | Verify |
|---|---|---|---|
| TRD-GEN-1 | P0 | Generation is performed by Claude, accessed via BPL's existing license and a BPL-provided API key. The key is held only in the orchestrator's secrets store; it is not embedded in the modal or any client-visible config. | Inspection |
| TRD-GEN-2 | P0 | The system prompt instructs the model to answer only from the provided retrieval results, to cite sources, and to refuse otherwise. The system prompt is the canonical place where the closed-corpus guardrail is enforced at generation time. | Inspection |
| TRD-GEN-3 | P0 | Every answer must include at least one citation that names the source document and (where available) the section. | Test |
| TRD-GEN-4 | P0 | The system must not produce ungrounded answers under any normal operating condition. If grounding cannot be established, the system refuses and routes. | Test |
| TRD-GEN-5 | P0 | The output style must be readable across BPL's full skill range — no internal jargon, no engineering language, no legal hedging — per PRD v3. | Demo |
| TRD-GEN-6 | P0 | The citation verifier confirms every cited document in the response corresponds to a chunk that was actually returned by retrieval. Verification failures result in a refusal, not a returned answer. | Test |

---

## 7. Routing on refusal

Per PRD v3: routing is by policy type, not by department. A single policy type may map to one or more owning teams.

| ID | Pri | Requirement | Verify |
|---|---|---|---|
| TRD-RTG-1 | P0 | On refusal, the system returns a structured response identifying the owning team(s) for the policy area in question, drawn from the routing configuration. | Test |
| TRD-RTG-2 | P0 | The routing configuration maps policy types to owning team(s) — for example, `mission_statement → Legal`; `fundraising_policy → Development`; `data_retention → IT and Legal`. | Inspection |
| TRD-RTG-3 | P0 | Multiple owning teams per policy type are supported. | Test |
| TRD-RTG-4 | P0 | The routing configuration is editable by the Vizion build team during the pilot. Selvon reviews and approves the policy-type → owning-team mapping before the demo. | Demo |
| TRD-RTG-5 | P0 | If a question cannot be matched to any policy area in the configuration, the system refers the user to their supervisor or the most appropriate general department, rather than guessing. | Test |
| TRD-RTG-6 | P1 | Routing decisions are logged with the inferred policy type so the build team can review whether the inference is correct. | Inspection |

---

## 8. Guardrails

Guardrails are direct technical realizations of the PRD v3 guardrails section.

| ID | Pri | Requirement | Verify |
|---|---|---|---|
| TRD-GRD-1 | P0 | PII detected in user input must cause the input to be rejected before retrieval or generation. The rejection message must explain why and direct the user to rephrase without PII. | Test |
| TRD-GRD-2 | P0 | PII categories rejected include at minimum: full names paired with other identifiers, email addresses, phone numbers, government IDs, payment data, and home addresses. | Test |
| TRD-GRD-3 | P0 | The system must not provide legal advice and must not be used to bypass HR, IT, Finance, or Legal processes. Prompts that ask for these are refused with routing. | Test |
| TRD-GRD-4 | P0 | The system must not perform automated decision-making that affects staff or patrons. | Inspection |
| TRD-GRD-5 | P0 | The system answers only from the vetted policy corpus. No general internet knowledge, no model-pretraining fallback. | Test |
| TRD-GRD-6 | P0 | The system is read-only with respect to BPL data. It cannot edit, upload, or modify any document in the corpus or in any BPL system. | Inspection |

> **Beyond v3 scope — Vizion-internal engineering note.** PII detection runs at input as a pre-retrieval gate. Detector candidates include Microsoft Presidio (open-source, NER + recognizers) and a lightweight regex+NER ensemble. Detector choice is finalized at build time with reference to the false-positive rate on a sample of realistic BPL questions Selvon supplies. The detector is swappable without touching the orchestrator interface.

---

## 9. Interface (avatar modal)

| ID | Pri | Requirement | Verify |
|---|---|---|---|
| TRD-UI-1 | P0 | The pilot interface is a modal/pop-up presented to testers in the demo environment. The post-pilot embedding into the BPL intranet policy page is an activation step, not a pilot deliverable. | Demo |
| TRD-UI-2 | P0 | The avatar is a simple book icon for the pilot. Final design is a downstream decision and not in pilot scope. | Inspection |
| TRD-UI-3 | P0 | Output must be readable across BPL's full skill range. The interface must show the answer and the citation(s) clearly. | Demo |
| TRD-UI-4 | P0 | The modal supports a sample-question prompt for first-time users that disappears after the first send. | Demo |
| TRD-UI-5 | P0 | Conversation history is scrollable within the modal for the duration of the session. | Test |
| TRD-UI-6 | P0 | Each answer must surface its citation card adjacent to the answer text. Refusals must surface the routing card adjacent to the refusal text. | Demo |
| TRD-UI-7 | P0 | Per-message feedback (helpful / not helpful, with optional comment) is supported on every answer and refusal. | Test |

---

## 10. Privacy, anonymity, and data handling

| ID | Pri | Requirement | Verify |
|---|---|---|---|
| TRD-PRIV-1 | P0 | At sign-in, testers select attribution (email logged) or anonymity (no email recorded for the session). The choice is binding for the session. | Demo |
| TRD-PRIV-2 | P0 | When anonymity is selected, the orchestrator stores no identifying metadata against the question, response, or feedback for that session. | Test |
| TRD-PRIV-3 | P0 | Feedback may be submitted anonymously regardless of session attribution. | Test |
| TRD-PRIV-4 | P0 | PII in user input is rejected, never masked-and-stored. PII in retrieved corpus content is out of scope (Selvon's curation responsibility). | Inspection |
| TRD-PRIV-5 | P0 | Logs retain enough information to support the weekly readout (request count, refusal count, routing decisions, feedback ratings) but not the full text of attributed questions beyond the session window. | Inspection |

---

## 11. Logging & observability

| ID | Pri | Requirement | Verify |
|---|---|---|---|
| TRD-LOG-1 | P0 | Each request is assigned a unique `request_id` surfaced in response headers and used for feedback correlation. | Test |
| TRD-LOG-2 | P0 | The orchestrator logs `request_id`, timestamp, anonymized session marker, retrieval hit/miss, refusal reason (if any), and routing decision (if any). | Inspection |
| TRD-LOG-3 | P0 | Errors and stack traces are logged server-side only. They are never returned to the modal client. | Test |
| TRD-LOG-4 | P0 | The build-team console aggregates these logs into the weekly readout: question volume, refusal rate, top routing destinations, feedback ratings, and any failures. | Demo |
| TRD-LOG-5 | P0 | Logs and aggregates are available to the build team only during the pilot; Selvon receives derived summaries in the readout, not raw log access. | Inspection |

---

## 12. Non-functional requirements

| ID | Pri | Requirement | Verify |
|---|---|---|---|
| TRD-NFR-1 | P0 | P50 end-to-end latency for an answered question (PII pass → retrieve → generate → return) under 5 seconds for the 100-page corpus and 10-tester load. | Test |
| TRD-NFR-2 | P0 | P95 end-to-end latency under 10 seconds. | Test |
| TRD-NFR-3 | P0 | PII-rejected requests return in under 500ms (no retrieval, no generation). | Test |
| TRD-NFR-4 | P0 | All traffic between modal, orchestrator, and external APIs (OpenAI, Pinecone, Anthropic) is over HTTPS/TLS 1.2 or higher. | Inspection |
| TRD-NFR-5 | P0 | Secrets (API keys, signing keys) are held in a server-side secrets store and never logged or returned to the client. | Inspection |
| TRD-NFR-6 | P1 | Concurrent question handling: at least 5 simultaneous testers without degradation in P50 latency. | Test |

---

## 13. Acceptance criteria for June 15 demo

The pilot is accepted when the following criteria are met in a witnessed run with Selvon:

- All P0 requirements pass their stated verification method.
- Five SME questions and five non-expert questions selected by Selvon are answered correctly with valid citations, or refused-and-routed with the correct owning team.
- At least one PII-bearing input is rejected with the correct error message in under 500ms.
- At least one out-of-corpus question is refused with a routing card pointing to the right team.
- The weekly readout content (volume, refusal rate, top routes, feedback ratings) is shown live from the console.
- Selvon's curated 100-page corpus is the only loaded corpus, and the system demonstrably refuses general-knowledge questions outside it.

---

## 14. Traceability matrix (PRD v3 → TRD)

| PRD v3 section | TRD requirements |
|---|---|
| Closed corpus, grounded answers, refusal otherwise | TRD-GEN-2, GEN-3, GEN-4, GEN-6, GRD-5 |
| Routing by policy type to owning team(s) | TRD-RTG-1 through RTG-6 |
| PII rejected at input (not masked) | TRD-GRD-1, GRD-2, PRIV-4 |
| Anonymity respected end-to-end | TRD-PRIV-1 through PRIV-3 |
| No legal advice; no automated decisions; read-only | TRD-GRD-3, GRD-4, GRD-6 |
| Output readable across skill range; clear citation | TRD-GEN-5, UI-3, UI-6 |
| Stack: Pinecone + OpenAI embeddings + Python + Claude (BPL key) + LangChain/LlamaIndex | TRD-GEN-1, RET-1 through RET-4 |
| 100-page Selvon-curated corpus | TRD-IGN-1 through IGN-5 |
| 10 testers (SME + non-expert) | TRD-AUTH-1 through AUTH-4, PRIV-1 |
| Demo environment that does not touch BPL intranet | TRD-AUTH-1 (Vizion-issued credentials), TRD-UI-1 (modal in demo env) |
| June 15 demo | TRD §13 acceptance criteria |
| SharePoint integration engineered-ready, activated post-approval | TRD-AUTH-5 (P2), §1.2 v3 alignment callout |

---

## Appendix A. Glossary

- **Grounding:** the principle that every answer is derived from a retrieved chunk of the curated corpus.
- **Closed corpus:** the system answers only from BPL's loaded policies; no general internet knowledge or model-pretraining fallback.
- **Citation verifier:** a server-side check that every cited document in a response corresponds to a chunk actually returned by retrieval. Hallucinated citations cause refusal.
- **Grounding threshold:** the minimum similarity score required for retrieval to be considered sufficient to attempt an answer. Below threshold the system refuses without calling Claude.
- **Routing configuration:** a static (build-time editable) mapping from policy type to one or more owning team(s). Approved by Selvon before the demo.
- **PII gate:** the pre-retrieval input filter that rejects questions containing personally identifiable information.
- **Anonymous session:** a tester session in which no email or tester ID is recorded against questions, responses, or feedback.
- **Activation:** the post-pilot phase in which Vizion hands off the engineered-ready system to Michael's team to flip from demo to BPL-intranet-embedded. Out of pilot scope.
