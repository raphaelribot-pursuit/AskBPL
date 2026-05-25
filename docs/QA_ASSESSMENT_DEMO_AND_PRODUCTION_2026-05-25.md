# QA Assessment — Demo Readiness & Production Scalability

**Date:** 2026-05-25  
**Scope:** Read-only inspection of `packages/orchestrator` + `packages/web-demo` + `infra` + `.github/workflows`. No code changes. Browser UI not exercised in this session.

---

## PHASE 1: DEMO READINESS

### §1.1 Acceptance Battery

| Check | Status | Notes |
|-------|--------|-------|
| (a) Results file exists (`qa_acceptance_results_2026-05-25.txt` or `/tmp/qa_results.txt`) | ❌ | No matching file in repo; glob found none. |
| (b) B1–B5 SME: answer + citations | ⚠️ | Cannot cross-check without saved battery output. |
| (c) C1–C5 non-expert: answer + citations | ⚠️ | Same. |
| (d) D1 PII: 400 + PII_DETECTED | ✅ | `ask_service.py` returns 400, `detail: PII_DETECTED`, `type: error_pii`; structured log `refusal_reason: PII_DETECTED`. |
| (e) D2 out-of-corpus: refusal + routing | ✅ | Refusal path + `RoutingDecision` persistence + `_finish_refusal` / routing teams in logs (code path). |
| (f) D3–D4 general knowledge: refusal | ✅ | `flagged_intents` + low grounding paths lead to refusals (code path). |
| Sample live curl vs battery | ⚠️ | Not re-run here (no bearer token in agent env). API was reachable: `GET /healthz` returned 200 + `X-Request-ID`. |

### §1.2 Conversational Follow-up

| Check | Status | Notes |
|-------|--------|-------|
| (a) API accepts `conversation_context` on `/questions/ask` | ✅ | `AskBody` + `routes_questions.py`; max 4 turns. |
| (b) Query rewriter produces standalone query | ✅ | `rewrite_follow_up()` + `ask_service` uses it when Anthropic key set. |
| (c) PII gate scans context turns | ✅ | `combined_text` joins question + all context contents before `rejects_input`. |
| (d) `useAskChat.ts` sends `buildConversationContext()` | ✅ | Passes context into `askQuestion` → JSON `conversation_context` on `/v1/ask`. |
| (e) `AvatarShellLegacy.tsx` wired for context | ❌ | `ShellBody` POST body is `{ question: text }` only — **no** `conversation_context`. |
| Follow-up curl test (Materials follow-up) | ⚠️ | Not executed (auth). Logic supports it on canonical `/questions/ask` + `/v1` aliases when client sends context. |

### §1.3 Frontend — Modal UI (browser)

| Check | Status | Notes |
|-------|--------|-------|
| 1.3.1–1.3.13 (TRD-UI / AUTH / GRD items) | ⚠️ | **Not verified in browser** this session. `HostPage.tsx`, `WireframeShell.tsx`, `LoginPage.tsx` implement the advertised flows in code; visual/UX parity requires manual pass. |

### §1.4 Build-team Console (browser)

| Check | Status | Notes |
|-------|--------|-------|
| 1.4.1–1.4.10 | ⚠️ | **Not verified in browser**. Code: `ConsoleLayout`, `Overview`, `Corpus` (stats + **Re-ingest all** → `triggerReIngest`), `Routing`, `Sessions`, `Feedback`, `Settings` + Basic Auth fields. |

### §1.5 Logging & Observability

| Check | Status | Notes |
|-------|--------|-------|
| 1.5.1 `event=ask_completed` JSON line | ✅ | `_emit_structured_ask_log` + `_build_completion_log`. |
| 1.5.2 `request_id`, `retrieval_hit`, `refusal`, `latency_ms` | ✅ | Present in `_build_completion_log`. |
| 1.5.3 PII → `refusal_reason=PII_DETECTED` | ✅ | Logged before 400 response. |
| 1.5.4 Routing: `inferred_policy_type` + `routing_teams` | ✅ | Fields on completion log payload. |
| 1.5.5 Query rewrite → `event=query_rewrite` | ✅ | Emitted with `original` / `rewritten` / `request_id`. |
| 1.5.6 500 → generic client message | ⚠️ | No custom global exception handler in `main.py`; **default FastAPI/Starlette behavior** — production should confirm `debug=False` and no stack leakage. |
| 1.5.7 `request_id` in response | ✅ | `JSONResponse` sets `X-Request-ID`; middleware also sets header on all responses. |

### §1.6 PII Gate Edge Cases

| Check | Status | Notes |
|-------|--------|-------|
| 1.6.1 Email | ✅ | Pattern `email_address` category (implementation uses **`email_address`**, not the string `"email"`). |
| 1.6.2 Phone | ✅ | `phone_number` regex in `pii_gate.py`. |
| 1.6.3 SSN-like | ✅ | `government_id_ssn_like`. |
| 1.6.4 PII only in context | ✅ | Combined scan + `tests/test_api_integration.py` covers context PII. |
| 1.6.5 Clean question not rejected | ✅ | Only rejects when patterns hit. |
| 1.6.6 Response does not echo PII | ✅ | 400 payload uses generic `message`; stored `question_text` is `NULL` on PII row. |

### §1.7 Auth Edge Cases

| Check | Status | Notes |
|-------|--------|-------|
| 1.7.1 No `Authorization` → 401 | ✅ | `deps.py`: "Missing bearer token". |
| 1.7.2 Expired token/session | ⚠️ | JWT decode uses `verify_exp: False`; **session DB `expires_at`** enforces expiry → `401` `"Session expired"`. Misleading if caller expects JWT-only expiry without DB hit — functionally blocked. |
| 1.7.3 Garbage token → 401 | ✅ | `"Invalid token"` / payload errors. |
| 1.7.4 Anonymous: no `tester_id` on `Question` | ✅ | `tester_storage = None` when anonymous attributed path. |
| 1.7.5 Anonymous feedback | ⚠️ | `anonymous_override` toggles stored flag only; JWT still identifies session — **no PII-free cryptographic anonymity** vs attributed; acceptable for pilot if TRD accepts session-scoped feedback. |

### §1.8 Corpus Exclusivity

| Check | Status | Notes |
|-------|--------|-------|
| 1.8.1 `INGEST_MANIFEST_PATH` → pilot YAML | ✅ | `Settings.ingest_manifest_path` default **`sample_corpus/corpus_manifest_pilot.yaml`**; `/internal/ingest` falls back to same. |
| 1.8.2 Markdown in `pilot/` not in pilot manifest | ✅ | **`corpus_manifest_pilot.yaml`** lists **6 PDFs only**; `pilot/` also contains `.md` files **not** listed. |
| 1.8.3 Gift acceptance question | ⚠️ | **Not re-run live** here; expects refusal if corpus/grounding correct (depends on deployed index). |
| 1.8.4 Data retention question | ⚠️ | Same. |

### §1.9 Known Issues (document only)

| # | Status | Notes |
|---|--------|-------|
| 1.9.1 passlib/bcrypt warning | ✅ | Cosmetic; bcrypt pin often used in dev (`passlib` + bcrypt 5.x friction). |
| 1.9.2 `pinecone_bulk_delete` / empty index / 404 | ⚠️ | `index.delete(ids=...)` **no try/except** — SDK-dependent failure risk. |
| 1.9.3 Stale markdown in `pilot/` | ✅ | Present on disk (`gift_acceptance.md`, etc.); excluded from pilot manifest. |
| 1.9.4 `AvatarShellLegacy` context | ✅ | Confirmed: no `conversation_context` in fetch body. |
| 1.9.5 `contact_hint` TBD | ✅ | **`config/routing_seed.yaml`** contains "TBD pending Selvon approval" on several teams. |
| 1.9.6 `section_heading` null | ⚠️ | **Chunk model** supports `section_heading`; chunking path may leave null if extractor doesn’t fill — cite as QA observation. |
| 1.9.7 `ADMIN_BASIC_PASSWORD` placeholder | ⚠️ | **Do not inspect `.env`** in-repo; `.env.example` / console UI expects real password — operator must verify before demo. |

### Demo Readiness Summary (Phase 1)

| Metric | Count |
|--------|------:|
| Total checks (excluding duplicated “known issues”) | ~53 |
| ✅ PASS | ~28 |
| ⚠️ PARTIAL / NOT RUN | ~22 |
| ❌ FAIL | ~3 |

- **Fails:** Missing acceptance artifact file; **Legacy avatar shell omitting conversation context**; reliance on manual UI verification.
- **Demo verdict:** **CONDITIONALLY READY** — core API, PII/logging/corpus wiring look aligned with TRD; **complete demo sign-off requires** persisted battery file + manual UI/console pass + **`VITE_ENABLE_AVATAR_SHELL` path** audited (legacy shell misses follow-ups).

---

## PHASE 2: PRODUCTION SCALABILITY

Effort key: **S** small (~days), **M** medium (~weeks), **L** large (multi-week / programme).

### §2.1 Infrastructure & Deployment

| Check | Status | Gap description | Effort |
|-------|--------|-----------------|--------|
| 2.1.1 Prod deployment definition | ⚠️ | `infra/docker-compose.yml` has **Postgres only** — no orchestrator Dockerfile, no prod orchestration IaC found. | **M** |
| 2.1.2 Uvicorn workers | ⚠️ | `main.__main__` runs **single** `uvicorn` process; scale-out pattern undefined. | **S**–**M** |
| 2.1.3 HTTPS/TLS | 🔮 | Local HTTP; nginx/ALB/Caddy config not in repo. | **M** |
| 2.1.4 Managed DB + pooling | ⚠️ | `create_async_engine` default pool only; **no pgbouncer**/pool size tuning; migration to managed PG is config + ops. | **M** |
| 2.1.5 Secrets store | ⚠️ | **`get_settings()` lru_cached** → env read at startup; **no Vault/Secrets Manager** integration. Rotation = **restart**. | **M** |
| 2.1.6 CI/CD | ⚠️ | `.github/workflows/ci.yml` runs ruff/pytest/npm — **no container build/deploy** stage. | **M** |
| 2.1.7 Health checks | ⚠️ | **`/healthz`** trivial OK; **`/readyz`** checks **Postgres only** — not Pinecone/OpenAI connectivity. | **S** |

### §2.2 Authentication & Identity

| Check | Status | Gap description | Effort |
|-------|--------|-----------------|--------|
| 2.2.1 Swappable IdP abstraction | ⚠️ | **`authenticate_tester` + bcrypt** on `/auth/sign-in`; no adapter/interface for Entra. | **L** |
| 2.2.2 JWT claims shape | ⚠️ | `sub`, `iat`, `exp`, `tester_id`, `attribution` — **works for pilot**; `employee_id` rename is mapping work. | **S**–**M** |
| 2.2.3 Entra/SAML/OIDC code | 🔮 | **Docs mention** activation; runtime codepaths **absent**. | **L** |
| 2.2.4 Refresh tokens | 🔮 | **No refresh** tokens; hourly session TTL only (`session_ttl_hours`). | **M** |

### §2.3 Corpus Scaling

| Check | Status | Gap description | Effort |
|-------|--------|-----------------|--------|
| 2.3.1 Chunking performance | ⚠️ | Ingest sequential per doc; large PDF throughput **not profiled**. | **M** |
| 2.3.2 Pinecone capacity | 🔮 | **Console/plan-dependent** — code uses single index + metadata filters. | **S**–**M** |
| 2.3.3 Embedding cost | ✅ | `text-embedding-3-small` in config — cost model acceptable at stated scale (ops tracking still needed). | **S** |
| 2.3.4 Incremental ingest | ✅ | Per-document **delete Pinecone IDs + Chunk rows + re-upsert** in `ingest_file`. | **S** |
| 2.3.5 Document versioning | ⚠️ | **`superseded_by_document_id`** exists; versioning UX/API light. | **M** |

### §2.4 Retrieval & Generation Scaling

| Check | Status | Gap description | Effort |
|-------|--------|-----------------|-------|
| 2.4.1 Latency under load | ⚠️ | **`idx.query`** in `_pinecone_scores` is **sync** inside async method — blocks event loop under load (`retrieval.py`). Embed uses async helpers. Anthropic **`AsyncAnthropic`** for generation/query rewrite ✅. | **M** |
| 2.4.2 Rate limiting | ❌ | **No** per-user/per-IP rate limit middleware found. | **M** |
| 2.4.3 Caching | ❌ | **No** Redis/TTL cache for embeddings or retrieval. | **M** |
| 2.4.4 Token budget | ⚠️ | `max_tokens=1200` generation / `150` rewrite — **no** aggregate quota or metering. | **M** |
| 2.4.5 Grounding threshold | ⚠️ | **Default `0.72`** in `config.py`; env override may differ (`GROUNDING_THRESHOLD` if set). Larger corpus ⇒ **needs recalibration**. | **S**–**M** |
| 2.4.6 Rewriter cost | ✅ | Claude rewrite per follow-up — acceptable order-of-magnitude; monitor in prod. | **S** |

### §2.5 Security

| Check | Status | Gap description | Effort |
|-------|--------|-----------------|--------|
| 2.5.1 Input length limit | ⚠️ | **`question`**: `min_length=3` only — no `max_length`** on `AskBody`. | **S** |
| 2.5.2 SQL injection | ✅ | SQLAlchemy ORM; `readyz` uses bound `text("SELECT 1")`. | — |
| 2.5.3 CORS production | ⚠️ | **`cors_origins`** configurable (comma-split); docs must lock to SharePoint origin. | **S** |
| 2.5.4 Admin console auth | ⚠️ | Basic auth + **`guard_admin`** — prod must rotate password / move behind SSO/VPN. | **M** |
| 2.5.5 API key rotation | ⚠️ | Settings cached at startup — **restart required** for key rotation. | **S**–**M** |
| 2.5.6 Prompt injection | ⚠️ | **Strong system prompt** + JSON-only grounding; **not** a formal jailbreak harness. | **M** ongoing |
| 2.5.7 Data at rest | 🔮 | Local Docker Postgres = **ops responsibility**; managed services add encryption-by-default. | **M** |

### §2.6 Observability & Operations

| Check | Status | Gap description | Effort |
|-------|--------|-----------------|--------|
| 2.6.1 Log sink | ⚠️ | **stdout JSON** strings — no CloudWatch/Datadog forwarder configured in repo. | **M** |
| 2.6.2 Alerting | ❌ | **Not implemented** (no thresholds / PagerDuty / etc.). | **M** |
| 2.6.3 Metrics dashboards | ⚠️ | Internal readout APIs exist; **no Prometheus/Grafana**. | **M** |
| 2.6.4 Error tracking | ❌ | **No** Sentry/Rollbar in dependencies. | **S**–**M** |
| 2.6.5 Audit trail | ⚠️ | DB-backed questions/responses — **tamper-evidence / retention policy** unspecified. | **M** |
| 2.6.6 Backup & recovery | ❌ | **No** documented RTO/RPO or Pinecone backup runbooks in repo. | **M** |

### §2.7 Multi-tenancy (platform vision)

| Check | Status | Gap description | Effort |
|-------|--------|-----------------|--------|
| 2.7.1–2.7.4 Tenant isolation | ❌🔮 | **No** `tenant_id`, RLS multi-tenant, or per-tenant Pinecone namespaces in models. Single-tenant pilot. | **L** |

### §2.8 SharePoint Integration Seams

| Check | Status | Gap description | Effort |
|-------|--------|-----------------|--------|
| 2.8.1 Embed modal | ⚠️ | Vite **SPA bundle** exists; SPFx/iframe hardening/CSP — **manual integration** not proven. | **M**–**L** |
| 2.8.2 `VITE_API_BASE_URL` | ✅ | Present across web-demo (**build-time config** seam). | **S** |
| 2.8.3 Auth handoff | 🔮 | **No** SSO/token exchange implemented — today's login modal is pilot-only. | **L** |
| 2.8.4 Doc source SharePoint | ❌🔮 | Ingest expects **filesystem paths** (`ingest_manifest` paths). | **M**–**L** |
| 2.8.5 Network topology | 🔮 | Outbound SaaS egress policy + hosting zone — **enterprise decision**. | **M** |

### Production Readiness Summary (Phase 2)

| Metric | Count (approx.) |
|--------|----------------|
| Items scored | ~45 |
| ✅ Ready now | ~8 |
| ⚠️ Needs work | ~26 |
| ❌ Missing / 🔮 Deferred | ~11 |

**Top 5 production gaps**

1. **Identity (Entra/SSO)** — **L** — blocks turnkey SharePoint staff rollout as described in TRD activation.
2. **Hosting + TLS + multi-worker HA** — **M**–**L** — no prod topology in-repo.
3. **Rate limiting + cost controls + input bounds** — **M** — financial & abuse posture for 1,500 staff.
4. **Observability stack** — **M** — log sink, alerting, exceptions (Sentry), metrics.
5. **Blocking Pinecone `query`** on event loop + **secrets hot-reload** — **M** — scale & ops friction.

---

## SharePoint Integration Readiness

| Party | Responsibility |
|-------|----------------|
| **Already in place** | `VITE_API_BASE_URL` seam; CORS config knob; SPA modal + JWT pilot auth; TRD wording on deferred activation (`AskBPL_TRD.md` / architecture docs mention Entra). |
| **BPL / Michael’s team** | Entra app registration / consent; SharePoint host origin(s); CSP/iframe policies; egress allowlists for Anthropic/OpenAI/Pinecone; production secrets & SSO expectations. |
| **Vizion (pre-handoff)** | SSO token exchange adapter; hardened admin auth; staging URL + TLS; **fix or document Legacy shell context gap** so any demo path matches TRD UX; ingest from SharePoint (Graph) if required. |

**Estimated activation effort:** **L** (many-to-mostly configuration seams exist at API boundary, **identity + hosting + ingestion source** remain substantial).

---

## COMBINED ASSESSMENT

### Overall verdict

| Dimension | Assessment |
|-----------|-------------|
| **Demo (June 15)** | **CONDITIONALLY READY** — backend contracts and logging/PII behaviors are well-implemented in code; **gaps:** missing persisted **14-test results file**, **no browser verification** in this run, **`AvatarShellLegacy` missing `conversation_context`**, **`/readyz` does not verify Pinecone**. |
| **Production** | **~35–45% ops-ready** (core app exists; HA, SSO, observability, rate limits, prod IaC largely open). |
| **SharePoint activation** | **Feasible but not turnkey** — **API base URL** is ready; **SSO & embedding & corpora source** are the heavy lifts.

### Recommended next steps

1. **Save `qa_acceptance_results_*.md`** in-repo with verbatim curl bodies + timestamps — owner: Vizion — before demo rehearsal.
2. **Manual UI/console checklist** §1.3–§1.4 on `localhost:5173` with recording — owner: Vizion + BPL — this week.
3. **Decision: default shell** — if `VITE_ENABLE_AVATAR_SHELL=true`, **wire `conversation_context`** in `AvatarShellLegacy` or disable legacy for demo — owner: Vizion.
4. **Strengthen `/readyz`** (optional deps: DB + Pinecone ping) — owner: Vizion — **S**.
5. **Production programme:** Entra SSO design review, HA deployment target, rate limits, log aggregation — owners: Vizion + BPL IT — **post-pilot**.

---

*Assessment performed by codebase inspection only; production estimates are directional.*
