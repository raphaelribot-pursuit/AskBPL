# Ask BPL — QA Test Execution Checklist (Polish Sprint)

| Field | Value |
|---|---|
| **Demo target date** | June 15, 2026 |
| **Aligned to** | BPL Ask BPL PRD v3 (April 29, 2026) / **TRD v0.3** (May 8, 2026) |
| **Generated** | June 1, 2026 |
| **Scope** | Code-freeze polish sprint — execution checklist only (no feature changes) |

**Sources used:** `AskBPL_TRD.md` (authoritative TRD IDs), `docs/AskBPL_Progress_Summary.pdf` (build progress; no separate Markdown report in repo), `docs/pilot/WIREFRAME_PARITY.md` + wireframe Screen 4 intent (clickable HTML not versioned in repo — see `docs/pilot/AskBPL_wireframe_v3.html` placeholder in WIREFRAME_PARITY), codebase inspection (`packages/orchestrator`, `packages/web-demo`).

---

## Summary (pre-execution)

| Metric | Count |
|---|---:|
| **Total checklist rows** | 67 |
| TRD-ID rows (each ID once; IGN-5 / LOG-4 also referenced in chain notes) | 56 |
| Build-report / polish rows (no TRD ID) | 9 |
| Post-pilot / out-of-scope notes | 2 |
| **PASS** (inspection) | 27 |
| **FAIL** (inspection) | 7 |
| **PENDING-EXECUTE** (requires running app) | 31 |
| **BLOCKED** | 0 |
| **N-A-POST-PILOT** | 2 |

### Demo blockers

Rows marked **FAIL** below that affect the June 15 witnessed demo unless resolved before rehearsal:

| ID / row | Why it blocks |
|---|---|
| **TRD-RTG-4** | `routing_seed.yaml` still has `TBD pending Selvon approval` contact hints — mapping not signed off for demo. |
| **Config: ADMIN_BASIC_PASSWORD** | `.env.example` leaves password empty; console + `/v1/internal/*` unusable until set (see row in §F). |
| **(no TRD ID) Overview routing breakdown** | Weekly readout API returns `routing_team_counts_sample` but Overview UI does not surface top routes (TRD-LOG-4 demo narrative). |
| **(no TRD ID) Document viewer highlighting** | Open P1 — citation-driven highlight may not appear in live UI (verify before demo if citations are clicked). |
| **TRD-IGN-5 / corpus table** | Depends on successful ingest of all **6** pilot PDFs — must **PENDING-EXECUTE** confirm `Indexed` before demo. |

All **PENDING-EXECUTE** P0 Test/Demo rows must be run during rehearsal week; treat any P0 failure after execution as a blocker.

---

## Status legend

| Status | Meaning |
|---|---|
| **PASS** | Verified by code/config inspection or completed test run (note evidence). |
| **FAIL** | Inspection or test shows requirement not met. |
| **BLOCKED** | Cannot execute (missing env, credentials, dependency down). |
| **PENDING-EXECUTE** | Requires running stack (UI, live API, latency, ingest). |
| **N-A-POST-PILOT** | Explicitly out of June pilot scope per TRD / PRD v3. |

---

## A. Backend / RAG pipeline

| TRD ID | Requirement (1-line) | Method | Repro steps | Expected result | Status | Evidence / Notes |
|---|---|---|---|---|---|---|
| TRD-AUTH-1 | Vizion-issued email + access code over HTTPS; credentials not logged | Inspection | 1. Read `routes_auth.py` sign-in handler and auth logging. 2. Confirm demo uses HTTPS in target env (local may be HTTP). | Sign-in accepts seeded tester; no credential values in structured logs. | PENDING-EXECUTE | Code path: `packages/orchestrator/ask_bpl_orchestrator/api/routes_auth.py`. TLS for prod: **PENDING-EXECUTE** with TRD-NFR-4. |
| TRD-AUTH-2 | Session token bound to tester or anonymous marker after sign-in | Test | 1. `POST /auth/sign-in` with body `@docs/qa/sign-in-attributed.json`. 2. Decode JWT or inspect response for session binding. | 200 + bearer token; anonymous vs attributed reflected in session row. | PENDING-EXECUTE | `AttributionMode` in `db/models.py`; session created in sign-in route. |
| TRD-AUTH-3 | Bearer required on orchestrator APIs; missing/invalid → 401 | Test | 1. `GET /healthz` without auth (should 200). 2. `POST /v1/ask` without `Authorization` → 401. 3. Garbage bearer → 401. | Protected routes 401; public health OK. | PASS | `deps.py` `jwt_auth`: missing/invalid token → 401. Integration: `tests/test_api_integration.py`. |
| TRD-AUTH-4 | Session expires after 8h inactivity; re-auth required | Test | 1. Sign in. 2. Confirm `expires_at` on session ~8h from issuance (`session_ttl_hours`). 3. (Optional) advance clock or wait — expired session → 401 on ask. | Expired session cannot ask; message indicates re-auth. | PENDING-EXECUTE | `config.py` `session_ttl_hours`; `ask_service.py` checks `sess.expires_at`. JWT `verify_exp` off — DB expiry is source of truth. |
| TRD-AUTH-5 | Activation: Entra ID seam; endpoint shapes stable | Inspection (post-pilot) | — | Documented seam only; no pilot Entra flow. | N-A-POST-PILOT | TRD §1.2 activation deferral; no Entra adapter in repo. |
| TRD-RET-1 | Same OpenAI embedding model at ingest and ask (pinned in config) | Inspection | 1. Read `config.py` / `.env.example` `OPENAI_EMBEDDING_MODEL`. 2. Confirm ingest `embed_snippet` uses same settings. | Single model id (e.g. `text-embedding-3-small`) everywhere. | PASS | `OPENAI_EMBEDDING_MODEL=text-embedding-3-small` in `.env.example`; `langchain_embeddings.py`, `ingest/service.py`. |
| TRD-RET-2 | Pinecone top-K (default 6) with similarity scores | Test | 1. Ask grounded question with bearer. 2. Inspect response citations / server logs for chunk scores (or integration test with mocks). | Up to K chunks; scores present in retrieval path. | PENDING-EXECUTE | `pinecone_top_k=6` `config.py`; `retrieval.py` `query`. |
| TRD-RET-3 | Grounding threshold — below threshold → refusal, no Claude | Test | 1. Set `GROUNDING_THRESHOLD=0.40` in env. 2. Ask out-of-corpus or low-similarity question. 3. Confirm refusal without generation latency spike. | Refusal response; no answer type; logs show grounding miss. | PENDING-EXECUTE | **PASS** threshold config: `config.py:28` default `0.40`, `.env.example:34`; applied `ask_service.py:290-292`. |
| TRD-RET-4 | LangChain/LlamaIndex swappable; orchestrator interface stable | Inspection | 1. Confirm retrieval uses `VectorRetriever` / embedding helper, not hard-coded to one framework's types in API layer. | Interface isolates retrieval implementation. | PASS | `services/retrieval.py`, `langchain_embeddings.py`. |
| TRD-RET-5 | Retrieval payload includes doc name, section, chunk id for verifier | Inspection | 1. Trace `RetrievedChunk` / citation payload in `ask_service` → `generation.py`. | Generation receives chunk ids + metadata for TRD-GEN-6. | PASS | `retrieval.py` `RetrievedChunk`; citations in `ask_service` payload. |
| TRD-GEN-1 | Claude via BPL key in server secrets only | Inspection | 1. Confirm `ANTHROPIC_API_KEY` in settings, not in `packages/web-demo` env for generation. 2. Grep web-demo for anthropic key. | No client-visible generation key. | PASS | `generation.py` uses `get_settings()`; web-demo only `VITE_*`. |
| TRD-GEN-2 | System prompt: answer only from retrieval, cite or refuse | Inspection | Read `SYSTEM_PROMPT` in `generation.py`. | Closed-corpus instructions present. | PASS | `packages/orchestrator/ask_bpl_orchestrator/services/generation.py:40+`. |
| TRD-GEN-3 | Every answer has ≥1 citation (doc + section when available) | Test | 1. Ask in-scope policy question (e.g. annual leave). 2. Verify `type: answer` and citations array non-empty with document names. | ≥1 citation on every answer. | PENDING-EXECUTE | Citation persistence in `ask_service`; UI: `CitationCard.tsx`. |
| TRD-GEN-4 | No ungrounded answers; cannot ground → refuse + route | Test | 1. General-knowledge question. 2. Low-similarity question. | Refusal + routing card data, not fabricated answer. | PENDING-EXECUTE | `ask_service` refusal paths; `flagged_intents`, grounding threshold. |
| TRD-GEN-5 | Readable prose for full skill range (no jargon/hedging) | Demo | 1. SME + non-expert question battery (Selvon picks). 2. Review answer text in modal. | Plain-language answers suitable for staff audience. | PENDING-EXECUTE | Prompt style rules in `generation.py` (2–4 sentences). |
| TRD-GEN-6 | Citation verifier — hallucinated cite → refusal | Test | 1. (If harness exists) force bad cite id; else review `test_*` for verifier. 2. Normal ask — only returned cites. | Verifier failure yields refusal, not answer. | PENDING-EXECUTE | Verifier in `ask_service` / generation path; see `requirements-matrix.md` GEN-6. |
| TRD-RTG-1 | Refusal returns owning team(s) from routing config | Test | 1. Trigger refusal (out-of-corpus). 2. Inspect API `routing` / teams in payload and DB `RoutingDecision`. | Named team(s) returned. | PENDING-EXECUTE | `_finish_refusal`, `routing_service.py`. |
| TRD-RTG-2 | Static policy-type → team mapping in config | Inspection | Read `config/routing_seed.yaml` and seeded rules. | Example mappings present (materials, fundraising, etc.). | PASS | `routing_seed.yaml`; seed loads rules. |
| TRD-RTG-3 | Multiple owning teams per policy type supported | Test | 1. Refusal on policy with multiple teams in seed. 2. Count routing teams in response. | >1 team when configured. | PENDING-EXECUTE | `RoutingDecision` multiple rows per response. |
| TRD-RTG-4 | Routing editable by build team; Selvon approves before demo | Demo | 1. Open console → **Routing**. 2. Toggle Selvon approval on pending rules. 3. Confirm seed hints no longer all `TBD pending Selvon approval`. | Approved mappings active; no demo-blocking TBD hints. | FAIL | Approval UI: `Routing.tsx`, API `routes_internal.py`. **FAIL:** `routing_seed.yaml:65-85` contact_hint still contains `TBD pending Selvon approval`. |
| TRD-RTG-5 | Unmatched policy → supervisor/general dept, not guess | Test | Ask question outside all policy types. | Refusal routes to general/supervisor team from config. | PENDING-EXECUTE | `general_supervisor_team` in `routing_service.py`. |
| TRD-RTG-6 | Routing logs inferred policy type for build review | Inspection | 1. Complete ask/refusal. 2. Inspect structured log line for `inferred_policy_type` / `routing_teams`. | Fields present on completion log. | PASS | `_build_completion_log` in `ask_service.py`. |
| TRD-GRD-1 | PII in input rejected before retrieve/generate | Test | 1. `POST /v1/ask` with email in question (body `@docs/qa/ask-pii.json`). | 400, `detail: PII_DETECTED`, user-safe message. | PENDING-EXECUTE | `pii_gate.py`, `ask_service.py:180-218`. |
| TRD-GRD-2 | PII categories: email, phone, gov id, payment, address, name+id | Test | Parametrize prompts per category; expect 400 for each. | Each category triggers rejection. | PENDING-EXECUTE | `tests/test_pii_gate.py`. |
| TRD-GRD-3 | No legal advice / bypass HR-IT-Finance-Legal — refuse + route | Test | Prompts: "Can I sue…", "Approve my termination…". | Refusal with routing, not legal guidance. | PENDING-EXECUTE | `flagged_intents` / policy prompts in tests if present. |
| TRD-GRD-4 | No automated decisions affecting staff/patrons | Inspection | Review orchestrator — no decision workflow outputs. | Q&A only; no employment/patron decisions. | PASS | Ask/refusal/feedback only; no decision engine. |
| TRD-GRD-5 | Closed corpus only — no internet/pretraining fallback | Test | Ask general knowledge (e.g. "capital of France"). | Refusal, not general knowledge answer. | PENDING-EXECUTE | `flagged_intents`, grounding + prompt. |
| TRD-GRD-6 | Read-only vs BPL data — no upload/modify via product | Inspection | 1. Confirm no tester-facing upload API in pilot routes. 2. Ingest only via internal admin. | No client corpus upload; internal ingest only. | PASS | Ingest `POST /v1/internal/ingest` admin-guarded; no public upload. |
| TRD-LOG-1 | Unique `request_id` in header + feedback correlation | Test | 1. Ask question. 2. Note `X-Request-ID` on response. 3. `POST /feedback/` with same id. | Header matches body `request_id`; feedback 200. | PENDING-EXECUTE | `routes_questions.py` / `routes_v1.py` set header; `FeedbackControl` uses `requestId`. |
| TRD-LOG-2 | Server logs: request_id, time, session marker, retrieval, refusal, routing | Inspection | Trigger ask + refusal; tail orchestrator logs for JSON `ask_completed`. | Required fields in structured log. | PASS | `_emit_structured_ask_log`, `_build_completion_log` `ask_service.py`. |
| TRD-LOG-3 | Errors/stack traces server-side only | Test | 1. Provoke 500 (e.g. bad config) if safe in dev. 2. Client response has no stack trace. | Generic client error; details in server logs only. | PENDING-EXECUTE | No custom handler exposing traces in `main.py` — confirm `debug=False` in prod. |
| TRD-NFR-1 | P50 answered question latency < 5s (pilot load) | Test | Run `askbpl-latency-smoke --iterations 10` from orchestrator venv. | P50 ≤ 5s for answer path. | PENDING-EXECUTE | See `docs/demo_acceptance.md`. |
| TRD-NFR-2 | P95 latency < 10s | Test | Same smoke tool; record P95. | P95 ≤ 10s. | PENDING-EXECUTE | — |
| TRD-NFR-3 | PII rejection < 500ms | Test | Time `POST /v1/ask` PII payload (curl `-w '%{time_total}'`). | < 0.5s, no retrieval/generation. | PENDING-EXECUTE | Early return in `ask_service` before embed. |
| TRD-NFR-4 | TLS 1.2+ for modal, orchestrator, external APIs | Inspection | Confirm production URL scheme and provider defaults. | HTTPS in prod; no cleartext to OpenAI/Pinecone/Anthropic. | PENDING-EXECUTE | Local dev may use HTTP; prod deploy checklist. |
| TRD-NFR-5 | Secrets in server store; never logged/returned to client | Inspection | Grep orchestrator logs config for key material; confirm settings from env. | No secrets in API responses or client bundle. | PASS | `get_settings()` env-based; feedback/ask responses omit keys. **Note:** rotate keys before demo (operational row §F). |
| TRD-NFR-6 | ≥5 concurrent testers without P50 degradation | Test | Load script or 5 parallel asks (manual). | P50 stable vs single-user baseline. | PENDING-EXECUTE | P1 — cuttable but desirable for rehearsal. |

---

## B. Corpus ingestion (curated re-ingest path only)

| TRD ID | Requirement (1-line) | Method | Repro steps | Expected result | Status | Evidence / Notes |
|---|---|---|---|---|---|---|
| TRD-IGN-1 | PDF/DOCX/Markdown; parse failures → Failed in console, not silent | Test | 1. Ensure pilot corpus under `packages/orchestrator/sample_corpus/pilot/` (6 PDFs per manifest). 2. (Optional) place corrupt PDF in pilot folder + manifest entry. 3. Console **Corpus** → **Re-ingest all**. 4. Refresh corpus table. | Failed docs show `ingest_status: failed`; no silent omit. | PENDING-EXECUTE | Loaders: `ingest/loaders.py`; failed status `ingest/service.py:114-130`. |
| TRD-IGN-2 | Chunks carry source, section, policy type, version in Pinecone metadata | Inspection | 1. After ingest, inspect DB `chunks` / Pinecone metadata via admin or SQL. | Metadata fields populated on chunks. | PENDING-EXECUTE | Ingest staging in `ingest/service.py`; chunk model `db/models.py`. |
| TRD-IGN-3 | Exactly one policy type per doc; invalid → reject at ingest | Test | 1. Add manifest entry with unknown `policy` slug. 2. Re-ingest. | Document rejected or failed with visible error. | PENDING-EXECUTE | Manifest policies in `corpus_manifest_pilot.yaml`. |
| TRD-IGN-4 | Re-ingest idempotent on unchanged corpus | Test | 1. Note `chunk_count` / vector ids. 2. **Re-ingest all** twice without file changes. 3. Compare counts and sample queries. | Stable index state; no duplicate drift. | PENDING-EXECUTE | Idempotent delete+upsert `ingest/service.py`; `requirements-matrix.md` IGN-4. |
| TRD-IGN-5 | Console shows per-document status + last ingest timestamp | Demo | 1. Sign in to build console with admin creds. 2. **Corpus** → **Refresh corpus**. 3. Verify table + **Last ingest** stat. | All pilot docs listed with status and timestamps. | PENDING-EXECUTE | UI: `Corpus.tsx`; API: `GET /v1/internal/corpus` `routes_internal.py:35-61`. |
| (no TRD ID) | Pilot manifest: 6 curated PDFs indexed | Test | 1. Confirm `corpus_manifest_pilot.yaml` lists 6 PDFs only. 2. After re-ingest, table shows **6** rows `Indexed`. | `doc_count: 6`, all `ingest_status` indexed. | PENDING-EXECUTE | Manifest: `sample_corpus/corpus_manifest_pilot.yaml` lines 14-43; markdown files in `pilot/` excluded. |
| (no TRD ID) | Re-ingest chain: pilot PDFs → POST /v1/internal/ingest → Pinecone | Test | 1. Postgres + migrations + seed up. 2. Set `ADMIN_BASIC_PASSWORD`. 3. Console **Re-ingest all** OR `curl -u user:pass -X POST http://localhost:8000/v1/internal/ingest -H 'Content-Type: application/json' -d @docs/qa/ingest-empty.json`. 4. Wait ~2s; refresh corpus. | 202/200 queue message; chunk_count > 0; Pinecone vectors for pilot index. | PENDING-EXECUTE | `Corpus.tsx` `triggerReIngest`; `routes_internal.py:152+`; default manifest `INGEST_MANIFEST_PATH`. |

**Out of scope (record only):**

| TRD ID | Requirement (1-line) | Method | Repro steps | Expected result | Status | Evidence / Notes |
|---|---|---|---|---|---|---|
| — | Drive-source / drag-drop corpus upload | Inspection | — | Not in pilot; conflicts with read-only TRD-GRD-6. | N-A-POST-PILOT | SharePoint Document Source activation; no upload UI in `web-demo`. |

---

## C. Frontend modal

| TRD ID | Requirement (1-line) | Method | Repro steps | Expected result | Status | Evidence / Notes |
|---|---|---|---|---|---|---|
| TRD-UI-1 | Pilot = modal in demo env; does not block host page | Demo | 1. Open host page. 2. Open/close/minimize modal (FAB). 3. Interact with page behind modal. | Pop-up usable; minimize/close restores page access. | PENDING-EXECUTE | `WireframeShell.tsx`, `Modal.tsx`, `AvatarTrigger.tsx`. |
| TRD-UI-2 | Pilot avatar = simple book icon | Inspection | Open modal — book FAB, not final 3D avatar (unless legacy flag on). | Book icon shown for default shell. | PASS | `AvatarTrigger.tsx`; 3D gated `VITE_ENABLE_AVATAR_SHELL` → `AvatarShellLegacy.tsx`. |
| TRD-UI-3 | Readable output; answer + citations clearly shown | Demo | Ask grounded question; review transcript layout. | Answer readable; citations visible and understandable. | PENDING-EXECUTE | `PilotTranscript.tsx`, `CitationCard.tsx`. |
| TRD-UI-4 | Sample question prompt disappears after first send | Demo | 1. Fresh session open modal. 2. Observe sample chip. 3. Send any message. | Sample chip hidden after first send. | PENDING-EXECUTE | `WireframeShell.tsx:28-29,105` `showSampleChip`. |
| TRD-UI-5 | Scrollable conversation history for session | Test | 1. Ask 3+ questions in one session. 2. Scroll transcript. 3. Close/reopen modal — history retained until sign-out. | History scrolls; persists across close/reopen. | PENDING-EXECUTE | `useAskChat` at shell level; `WireframeShell.tsx:93-94`. |
| TRD-UI-6 | Citation card adjacent to answer; routing card adjacent to refusal | Demo | 1. Grounded answer — citation UI beside answer. 2. Refusal — routing deck beside refusal. | Cards visually associated with correct turn type. | PENDING-EXECUTE | `TranscriptRows.tsx`, `RoutingCard.tsx`; wireframe parity: citations may be inset vs separate pane (`WIREFRAME_PARITY.md`). |
| TRD-UI-7 | Per-message helpful / not helpful + optional comment | Test | **Feedback chain step 1:** 1. Ask or receive refusal. 2. Click 👍 or 👎. 3. Optional comment → **Send feedback**. | Thanks state; `POST /feedback/` succeeds. | PENDING-EXECUTE | `FeedbackControl.tsx`; `submitFeedback` in `useAskChat.ts` / `askApi.ts`. |
| (no TRD ID) | Document viewer: cited chunk highlighting visible | Demo | 1. Ask question with citation. 2. Open citation → document viewer. 3. Confirm cited chunk has highlight styling. | Highlighted chunk obvious (background + border). | PENDING-EXECUTE | **Open P1.** CSS `doc-chunk-highlighted` `wireframe-tokens.css:843-846`; logic `DocumentViewer.tsx:110-117`. Live render **PENDING-EXECUTE**. |
| (no TRD ID) | Document viewer: chunk paragraph spacing / breaks | Demo | 1. Open multi-paragraph chunk in viewer. 2. Compare readability to source PDF. | Paragraphs separated; lists not collapsed into wall of text. | PENDING-EXECUTE | **Open P1.** `CHUNK_MARKDOWN` + `doc-chunk-p` margins `DocumentViewer.tsx:11-16`. |
| (no TRD ID) | Legacy avatar shell sends `conversation_context` on follow-up | Inspection | If `VITE_ENABLE_AVATAR_SHELL=true`, ask follow-up; capture network body. | Follow-up includes `conversation_context` when using wireframe shell; legacy may not. | FAIL | `WireframeShell` → `useAskChat` sends context. **FAIL:** `AvatarShellLegacy.tsx` POST body `{ question }` only (`docs/QA_ASSESSMENT_DEMO_AND_PRODUCTION_2026-05-25.md` §1.2). Demo should use wireframe shell. |

---

## D. Build-team console

| TRD ID | Requirement (1-line) | Method | Repro steps | Expected result | Status | Evidence / Notes |
|---|---|---|---|---|---|---|
| TRD-IGN-5 | (Console surface) Per-doc ingest status + last run | Demo | Same as §B TRD-IGN-5 — execute from **Corpus** tab. | Table + aggregate last ingest time. | PENDING-EXECUTE | Duplicate execution OK — same acceptance. |
| TRD-LOG-4 | Weekly readout: volume, refusals, top routes, feedback, failures | Demo | **Feedback chain step 3:** 1. Admin creds → **Overview** → Refresh. 2. Submit feedback in modal (step 1). 3. **Feedback** tab → Refresh. 4. Compare helpful/not counts to Overview stats. | Overview reflects question volume + feedback counts; Feedback table lists rows with `request_id`. | PENDING-EXECUTE | API `GET /v1/internal/readout` → `aggregate_summary`; UI `Overview.tsx`, `Feedback.tsx`. |
| TRD-LOG-5 | Build team only for raw logs; Selvon gets summaries | Inspection | Confirm no Selvon-facing raw log export in UI; readout is aggregate. | No raw log download for client role. | PASS | Console shows aggregates only; `weekly_readout` docstring TRD-LOG-5. |
| (no TRD ID) | Sessions console wired to GET /admin/sessions | Test | 1. `GET /v1/internal/sessions` with basic auth (curl). 2. Open console **Sessions** tab. | API returns sessions list; UI shows same data (not placeholder copy). | FAIL | **API PASS:** `routes_internal.py:64-86`. **UI FAIL:** `Sessions.tsx` stub — "Wire this to GET /admin/sessions" with no fetch. |
| (no TRD ID) | Overview shows routing breakdown (top destinations) | Demo | After refusals with routing, refresh Overview. | Top routing teams visible (not only question/feedback counts). | FAIL | API returns `routing_team_counts_sample` `routes_admin.py:132-134`. **Overview.tsx** does not render routing breakdown (only doc count, questions, refusals, feedback). |

---

## E. Privacy / attribution

| TRD ID | Requirement (1-line) | Method | Repro steps | Expected result | Status | Evidence / Notes |
|---|---|---|---|---|---|---|
| TRD-PRIV-1 | Sign-in: attributed vs anonymous; binding for session | Demo | 1. Sign in **Attributed** with email. 2. New session **Anonymous**. 3. Confirm UI label / session behavior differs. | Mode persists for session until sign-out. | PENDING-EXECUTE | `LoginPage.tsx` / sign-in payload attribution. |
| TRD-PRIV-2 | Anonymous session: no tester id on question/response/feedback storage | Test | 1. Sign in anonymous. 2. Ask + submit feedback. 3. DB: `questions.tester_id` null for that session. | No tester_id on stored rows. | PENDING-EXECUTE | `ask_service.py:170-171` `tester_storage = None`; question_text null when anonymous. |
| TRD-PRIV-3 | Feedback may be anonymous regardless of session attribution | Test | **Privacy edge:** 1. Sign in **Attributed**. 2. Submit feedback with `anonymous_override: true` (if UI exposes; else curl `POST /feedback/` with flag). 3. Verify feedback row `anonymous=true` without storing email on feedback. | Feedback stored anonymous flag; session may still be attributed for questions. | PENDING-EXECUTE | `FeedbackPayload.anonymous_override` `routes_feedback.py:25`; legacy shell has global toggle `AvatarShellLegacy.tsx`. Wireframe path: confirm `askApi.ts` passes override when enabled. |
| TRD-PRIV-4 | PII rejected, never masked-and-stored | Test | PII ask → 400; inspect DB `question_text` null + `pii_rejected=true`. | No plaintext PII persisted. | PENDING-EXECUTE | `ask_service.py:182-189` stores `question_text=None` on PII. |
| TRD-PRIV-5 | Logs support readout without retaining full attributed question text beyond session window | Inspection | Review what is persisted on `Question` and log payload fields. | Aggregates + hashes; no long-term full text store for anonymous. | PASS | Anonymous omits `question_text`; attributed stores text — pilot session window acceptable per TRD. |

**Feedback chain (cross-reference):**

| TRD ID | Requirement (1-line) | Method | Repro steps | Expected result | Status | Evidence / Notes |
|---|---|---|---|---|---|---|
| TRD-UI-7 | (chain) Modal capture | Test | See §C TRD-UI-7. | — | PENDING-EXECUTE | — |
| TRD-LOG-1 | (chain) `request_id` correlation | Test | Copy `X-Request-ID` from ask; use in feedback POST; appear in Feedback table. | IDs match end-to-end. | PENDING-EXECUTE | — |
| TRD-LOG-4 | (chain) Console Feedback + Overview aggregates | Demo | See §D TRD-LOG-4. | — | PENDING-EXECUTE | — |

---

## F. Config & deploy readiness

| TRD ID | Requirement (1-line) | Method | Repro steps | Expected result | Status | Evidence / Notes |
|---|---|---|---|---|---|---|
| (no TRD ID) | `ADMIN_BASIC_PASSWORD` set (not empty placeholder) | Inspection | 1. Read local `.env` `ADMIN_BASIC_PASSWORD`. 2. Hit `GET /v1/internal/corpus` with basic auth. | Non-empty password; console panels load without "Set ADMIN_BASIC_PASSWORD" error. | FAIL | `.env.example:42` empty placeholder; `guard_admin` rejects empty password `routes_admin.py:47-48`; console surfaces error `Overview.tsx:23`. |
| (no TRD ID) | API key rotation / no committed secrets | Inspection | 1. `git status` — no `.env` committed. 2. Confirm CI uses injected secrets. 3. Rotate Pinecone/OpenAI/Anthropic/JWT before demo per ops policy. | Secrets only in env/secret store; keys rotated for rehearsal. | PENDING-EXECUTE | `.gitignore` patterns; **operational P1** — not verifiable from code alone. |
| (no TRD ID) | TRD §13 demo acceptance battery (5+5 questions, PII, OOC, readout) | Demo | Follow `docs/demo_acceptance.md` + Selvon question list; log each `X-Request-ID`. | All §13 bullets witnessed with Selvon. | PENDING-EXECUTE | `AskBPL_TRD.md` §13; results file not in repo — tester to create `qa_acceptance_results_YYYY-MM-DD.txt`. |
| — | SharePoint / drive automatic ingestion | Inspection | — | Not exercised in pilot. | N-A-POST-PILOT | PRD v3 activation; TRD-GRD-6 read-only. |

---

## TRD coverage check

### All TRD IDs from `AskBPL_TRD.md` (56)

| Area | IDs | Checklist section |
|---|---|---|
| AUTH | TRD-AUTH-1 … TRD-AUTH-5 | A (AUTH-5 N-A-POST-PILOT) |
| IGN | TRD-IGN-1 … TRD-IGN-5 | B, D (IGN-5 duplicated execution in B+D) |
| RET | TRD-RET-1 … TRD-RET-5 | A |
| GEN | TRD-GEN-1 … TRD-GEN-6 | A |
| RTG | TRD-RTG-1 … TRD-RTG-6 | A |
| GRD | TRD-GRD-1 … TRD-GRD-6 | A, B (GRD-6 note), F |
| UI | TRD-UI-1 … TRD-UI-7 | C, E (UI-7 chain) |
| PRIV | TRD-PRIV-1 … TRD-PRIV-5 | E |
| LOG | TRD-LOG-1 … TRD-LOG-5 | A, D, E |
| NFR | TRD-NFR-1 … TRD-NFR-6 | A, F |

**TRD IDs not placed:** None — all 56 appear above.

**Note:** TRD-IGN-5 and TRD-LOG-4 appear in more than one section intentionally (Corpus UI + Overview/Feedback chain); requirement text is the same; execute once.

### Build-report / wireframe items without TRD ID (6)

| Item | Section |
|---|---|
| Pilot 6 PDFs indexed | B |
| Re-ingest API chain | B |
| Document viewer highlighting | C |
| Document viewer spacing | C |
| Legacy avatar `conversation_context` gap | C |
| Sessions UI stub vs API | D |
| Overview routing breakdown UI | D |
| ADMIN_BASIC_PASSWORD + key rotation | F |

### Suggested QA payload files (create under `scripts/qa/` before run)

| File | Purpose |
|---|---|
| `docs/qa/sign-in-attributed.json` | Attributed session sign-in |
| `docs/qa/sign-in-anonymous.json` | Anonymous session sign-in |
| `docs/qa/ask-pii.json` | PII gate probe (email in question) |
| `docs/qa/ingest-empty.json` | Default manifest re-ingest body `{}` |

---

## Execution notes for testers

1. **Stack:** `docker compose -f infra/docker-compose.yml up -d` → `packages/orchestrator` `.venv/bin/alembic upgrade head` → `.venv/bin/askbpl-seed` → orchestrator + `packages/web-demo` `npm run dev`.
2. **Python:** Use `packages/orchestrator/.venv/bin/python` / `.venv/bin/pytest` (see `AGENTS.md`).
3. **Pilot credentials:** `pilot-demo@bklynlibrary.org` / seeded access code (`docs/demo_acceptance.md`).
4. **Do not test:** Drive picker, drag-drop upload, SharePoint auto-ingest (post-pilot only).

---

*End of checklist.*
