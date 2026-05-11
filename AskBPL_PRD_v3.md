# Ask BPL — Product Requirements Document (PRD)

| Field | Value |
|---|---|
| Document type | Product Requirements Document (PRD) |
| Project | Ask BPL — AI Policy Assistant |
| Version | v3 (Working draft — approved scope) |
| Date | April 29, 2026 |
| BPL client lead | Selvon Smith — ssmith@bklynlibrary.org |
| Vizion engineering partner | Denward Lee Aulder |
| Status | Approved scope. This PRD is canonical for the Ask BPL document set. |

> This PRD is the source of truth for the Ask BPL pilot. All other documents in the set — TRD, ERD, SAD, API Specification, Security & Compliance, and SOW — derive their scope from this document and do not exceed it.

---

## 1. Overview

Ask BPL is an internal AI assistant that answers staff questions about Brooklyn Public Library policies and procedures. Staff currently spend significant time hunting through SharePoint, asking colleagues, or escalating to supervisors for answers that already exist in policy documentation. Ask BPL closes that gap by giving every staff member a fast, conversational way to find the right answer with a citation back to the source document.

When the system cannot answer from BPL's own documents, it does not fall back to general AI knowledge — it explicitly refuses and routes the staff member to the correct human contact within BPL. This is the principal reason BPL chose not to adopt Microsoft Copilot for this purpose: Copilot draws on general internet-scale training data and cannot guarantee that answers come from BPL's own documents.

---

## 2. Pilot Scope

The pilot is intentionally narrow to validate the system end-to-end before any expansion.

- **Corpus:** 100 pages of selected policy documents, curated by Selvon Smith.
- **Testers:** 10 staff members across multiple departments, selected by Selvon. Two groups:
  - **Subject matter experts (SMEs)** — staff who own or work directly with the policies being tested. They validate accuracy on documents they know.
  - **Non-experts** — staff who do not know the specific policies. They ask blind questions to see how the system handles unfamiliar users.
- **Environment:** Pilot runs as a demo / simulated environment. It is **not** deployed to the BPL intranet during the pilot. Intranet integration is post-pilot and handled by Michael's team.
- **Build window:** April 29 – June 8, 2026.
- **Demo:** June 15, 2026.

---

## 3. Users

### Primary users
- Public service staff at branch locations
- Supervisors and managers
- Administrative and support staff

### Secondary users
- HR, IT, Finance, Legal, and Development teams (as referrers and policy owners)
- New hires and recently promoted staff

### Top needs
1. Find the right, most current policy answer quickly using natural language.
2. Verify that the answer is grounded in an authoritative, up-to-date document.
3. Receive plain-language answers that work across the full staff skill range — from custodian to engineer, with no internal jargon, no engineering language, no legal hedging.
4. Be redirected to the correct human team when the question is out of scope.

---

## 4. Solution

### 4.1 Interface

A modal / pop-up overlay launched from the demo environment. For the pilot the avatar is a simple book icon — final avatar design and branding are deferred.

The modal:
- Sits one click away from wherever the staff member is working.
- Shows the answer and its citation side by side. Citations are clickable, opening the source document in a new tab while the chat session stays open.
- Supports per-message feedback (helpful / not helpful, with optional comment).

### 4.2 Routing

When the system refuses to answer, it must direct the user to a specific owning team — not deflect generically.

- **Routing is by policy type, not by department.** Each policy document carries a policy type (e.g., `gift_acceptance`, `data_retention`, `fundraising_policy`).
- **A single policy type may map to multiple owning teams.** For example: `mission_statement → Legal`; `fundraising_policy → Development`; `data_retention → IT and Legal`.
- The mapping is approved by Selvon before the demo and editable by the build team during the pilot based on real refusal patterns.
- If a question cannot be matched to any policy area, the system refers the user to their supervisor or the most appropriate general department — never a dead end.

### 4.3 Feedback

Feedback is built into the modal. Testers can submit feedback anonymously regardless of session attribution. Tester questions are logged to identify common patterns; this is the input that will drive default-handled responses and routing-matrix refinement.

---

## 5. Technical Direction

The pilot stack is confirmed:

| Layer | Choice |
|---|---|
| Vector database | **Pinecone** |
| Embeddings | **OpenAI** |
| Orchestration | **Python** |
| Generation | **Claude** (via BPL's existing license; BPL-provided API key) |
| Retrieval framework | **LangChain** or **LlamaIndex** (selected at build time) |

### BPL environment
- Microsoft 365, SharePoint, and Copilot already in use.
- Primary workstation OS is Windows, with some Mac. The pilot is OS-agnostic.

### SharePoint integration
SharePoint integration is **engineered-ready during the pilot, not activated**. The build is architected so that integration into BPL's SharePoint-based intranet is a clean, one-click operation when Michael's team is ready, executed as a configuration change rather than a rebuild. This is also a security requirement: the pilot is built externally and must integrate safely without crashing the intranet.

---

## 6. Guardrails

The following are non-negotiable. The system enforces every one of them.

- **Closed corpus.** Answers come only from BPL's vetted policy documents. No general internet knowledge, no model-pretraining fallback.
- **Grounded answers with citations.** Every answer cites the source document and section. Hallucinated citations are caught server-side and become refusals.
- **Refuse rather than guess.** If the corpus cannot support an answer, the system refuses and routes — never invents one.
- **PII rejected at input.** If a tester pastes personal information (names with other identifiers, emails, phone numbers, government IDs, payment data, addresses), the system rejects the input and asks them to rephrase. PII is not masked-and-stored; it is rejected.
- **No legal advice.** The system does not interpret law or provide legal counsel.
- **No bypassing HR / IT / Finance / Legal.** The system points to the correct team rather than substituting for them.
- **No automated decisions.** The system does not take actions that affect staff or patrons.
- **Read-only.** The system cannot edit, upload, or modify any BPL document or system.
- **Anonymity respected end-to-end.** When a tester selects anonymous attribution at sign-in, no email or tester ID is recorded against their questions, responses, or feedback for that session.

---

## 7. Out of Scope (Pilot)

The following are deliberately excluded from the pilot. Several are acknowledged as future scope.

- **Procedures coverage.** Pilot covers policies only; procedures expansion is future scope.
- **Patron-facing assistant.** Staff-only for the pilot.
- **Desktop / cross-application assistant.** Future scope.
- **BPL intranet deployment.** Post-pilot, handled by Michael's team after the demo and BPL's security review.
- **Document editing or uploads from within the system.**
- **Document vetting** — corpus curation is a human procedure handled by Selvon.
- **Rebuilt access control.** Identity defers to BPL's existing stack at activation; the pilot uses Vizion-issued credentials.
- **Custom model training or fine-tuning.**

---

## 8. Success Criteria

The pilot is successful if all of the following hold at the June 15 demo:

1. **Speed.** Cited answers return quickly enough to be useful in line-of-work conditions. (TRD codifies: P50 < 5s, P95 < 10s.)
2. **Accuracy on first try.** Selvon-selected SME and non-expert questions are answered correctly with valid citations.
3. **Refusal correctness.** Out-of-corpus questions are refused with a routing card pointing to the right team.
4. **PII rejection.** PII-bearing inputs are rejected at the gate with the correct message.
5. **Latest-version surfacing.** When duplicate or superseded versions exist in the corpus, the system surfaces the most current.
6. **Selvon and Pursuit leadership approve transition** from pilot to activation scope.

---

## 9. Roadmap & Cadence

| Milestone | Date |
|---|---|
| Build window opens | April 29 |
| Standing check-in starts (Tuesdays at 3:00 PM, 45 min) | June 5 |
| Friday Loom updates to Selvon and Dason | Weekly, beginning May 1 |
| Final build | May 30 |
| Final review with Pursuit | June 8 |
| **Demo** | **June 15** |

Standing check-ins are cancellable if no review is needed that week.

---

## 10. Future Scope (Post-Pilot)

Acknowledged during the April 29 session and explicitly outside the MVP build:

- **Desktop assistant** — cross-application availability beyond the intranet modal.
- **Procedures coverage** in addition to policies.
- **Patron-facing assistant** in branches.
- **Multi-tenant template** — the architecture is portable to other nonprofits with their own document sets.
- **Proactive alerts** — notifying departments when their policies are approaching expiration or due for review.

---

## 11. Document Set Cross-References

This PRD should be read alongside:

- **TRD** — translates these requirements into testable technical specs.
- **ERD** — defines the data model that supports these requirements.
- **SAD** — describes the system architecture that satisfies the TRD.
- **API Specification** — defines the contracts between the modal, the orchestrator, and admin functions.
- **Security & Compliance Document** — details how the privacy, access, and audit requirements above are enforced.
- **SOW** — codifies scope, timeline, deliverables, and pricing for the pilot engagement.
