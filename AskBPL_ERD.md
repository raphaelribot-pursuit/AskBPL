# Ask BPL — Entity Relationship Diagram (ERD)

| Field | Value |
|---|---|
| Document type | Entity Relationship Diagram (ERD) |
| Project | Ask BPL — AI Policy Assistant |
| Aligned to | BPL Ask BPL PRD v3 (April 29, 2026) and TRD v0.3 (May 8, 2026) |
| Version | 0.3 |
| Date | May 8, 2026 |
| BPL client lead | Selvon Smith — ssmith@bklynlibrary.org |
| Vizion engineering partner | Denward Lee Aulder |
| Primary audience | BPL IT (Selvon Smith — data flow validation); Vizion engineering (Denward Lee Aulder — schema implementation) |
| Status | Draft for client review |

> This document is part of the Ask BPL deliverable set. The PRD (v3) is canonical scope; the TRD specifies what the system does; this ERD specifies what it remembers.

---

## 1. Introduction

### 1.1 What this document is (and isn't)

This Entity Relationship Diagram (ERD) defines the data model that supports the Ask BPL pilot. It identifies the entities the orchestrator persists, the attributes they carry, and the relationships between them. It is the companion to the TRD: the TRD specifies what the system does; this ERD specifies what it remembers.

It is **not** a database administration document. It does not prescribe specific Postgres versions, indexing strategies beyond the obvious, or backup procedures. Those decisions sit with Vizion engineering and are out of v3 scope.

### 1.2 Audiences

- **Selvon Smith (BPL):** verify that the data Vizion will store about questions, sessions, and feedback aligns with PRD v3's privacy and anonymity guarantees. Section 4 (privacy walk-through) is the most important for this audience.
- **Denward Lee Aulder (Vizion engineering):** the schema spec. The data dictionary in §5 is the authoritative description; the schema diagram in §3 is the at-a-glance view.

### 1.3 Storage layout

The relational entities live in a single Postgres database managed by Vizion. Pinecone holds the embedding vectors keyed by `chunk_id`; vectors are not duplicated in Postgres. Secrets — API keys, JWT signing keys — live in a server-side secrets store and are not modeled here.

> **v3 alignment.** Per PRD v3, the demo environment does not touch BPL intranet, BPL identity, or any BPL-managed data store. Every entity in this ERD lives in Vizion-controlled infrastructure for the duration of the pilot. At activation, identity (`Tester`, `Session`) defers to BPL via SharePoint identity; the rest of the schema is unaffected.

---

## 2. Conceptual model

Three intertwined concerns shape the data model:

- **Identity:** who asked, in what session, with what attribution mode. `Tester`, `Session`.
- **Knowledge:** the curated corpus and its routing vocabulary. `Document`, `Chunk`, `PolicyType`, `RoutingRule`, `OwningTeam`.
- **Interaction:** the audit-of-record per request — question, response, citations or routing decisions, and feedback. `Question`, `Response`, `Citation`, `RoutingDecision`, `Feedback`.

These three concerns connect deliberately at narrow seams:

- `Session` links Identity to Interaction (and may carry no `tester_id` when anonymous).
- `Citation` and `RoutingDecision` link Interaction to Knowledge.
- There is **no** direct Tester-to-Document path; testers don't "own" documents, and documents don't "belong to" testers.

---

## 3. Schema diagram

Twelve entities organized into the three concerns above. Primary keys are marked **PK**; foreign keys are marked **FK**.

```
┌──────────── IDENTITY ────────────┐    ┌────────── INTERACTION ──────────┐
│                                  │    │                                 │
│  ┌──────────┐    ┌─────────────┐ │    │  ┌──────────┐    ┌────────────┐ │
│  │ Tester   │◄───│ Session     │ │    │  │ Question │◄───│ Response   │ │
│  │ PK id    │    │ PK id       │ │    │  │ PK req_id│    │ PK resp_id │ │
│  └──────────┘    │ FK tester_id│ │    │  │ FK ses_id│    │ FK req_id  │ │
│                  └──────┬──────┘ │    │  │ FK tst_id│    └─────┬──────┘ │
│                         │        │    │  └──────────┘          │        │
└─────────────────────────┼────────┘    │        ▲               ▼        │
                          │             │        │     ┌────────────┐     │
                          └─────────────┼────────┘     │ Citation   │     │
                                        │              │ FK chunk_id├─────┼──┐
                                        │              └────────────┘     │  │
                                        │              ┌────────────────┐ │  │
                                        │              │ RoutingDecision│ │  │
                                        │              │ FK team_id     ├─┼──┼──┐
                                        │              └────────────────┘ │  │  │
                                        │              ┌────────────┐     │  │  │
                                        │              │ Feedback   │     │  │  │
                                        │              │ FK req_id  │     │  │  │
                                        │              └────────────┘     │  │  │
                                        └─────────────────────────────────┘  │  │
                                                                             │  │
┌─────────────────────────── KNOWLEDGE ──────────────────────────────────────┘  │
│                                                                               │
│  ┌──────────┐    ┌──────────┐    ┌────────────┐                               │
│  │ Document │◄───│ Chunk    │◄───┘            │                               │
│  │ PK id    │    │ PK id    │                 │                               │
│  │ FK p_type│    │ FK doc_id│                 │                               │
│  └────┬─────┘    └──────────┘                 │                               │
│       │                                                                       │
│       ▼                                                                       │
│  ┌────────────┐    ┌──────────────┐    ┌─────────────┐                        │
│  │ PolicyType │◄───│ RoutingRule  │───►│ OwningTeam  │◄───────────────────────┘
│  │ PK p_type  │    │ FK p_type    │    │ PK team_id  │
│  └────────────┘    │ FK team_id   │    └─────────────┘
│                    └──────────────┘
└──────────────────────────────────────────────────────────────────────────────
```

> Render this schema interactively at [dbdiagram.io](https://dbdiagram.io) using the companion DBML file (`AskBPL_ERD.dbml`).

### 3.1 Cardinality summary

| Relationship | Cardinality | Notes |
|---|---|---|
| Tester → Session | 1 — N | A tester may have many sessions over the pilot. |
| Session → Question | 1 — N | Each session may contain many questions. |
| Question → Response | 1 — 1 | Every question yields exactly one response (an answer, a refusal, or a PII rejection error). |
| Response → Citation | 1 — N (≥1 when answered) | Answered responses must have at least one citation (TRD-GEN-3). Refusals and PII rejections have zero. |
| Response → RoutingDecision | 1 — N (≥1 when refused-with-routing) | Multiple owners are supported (TRD-RTG-3). |
| Question → Feedback | 1 — 0..1 | Feedback is optional, at most one per question per tester. |
| Document → Chunk | 1 — N | A document is chunked at ingest; chunks reference their parent document. |
| Document → PolicyType | N — 1 | Each document carries exactly one policy type (TRD-IGN-3). |
| PolicyType ↔ OwningTeam | N — N via RoutingRule | Multiple owners per policy area; an owning team may be referenced by multiple policy areas. |
| Chunk → Citation | 1 — N | A single chunk may ground multiple citations across responses. |
| OwningTeam → RoutingDecision | 1 — N | A team may be named in many refusals over time. |

---

## 4. Privacy walk-through (read this section, Selvon)

This section traces how PRD v3's privacy guarantees show up in the schema. It is the most important section for BPL to validate.

### 4.1 Anonymity is enforced by null FKs, not by promise

When a tester selects anonymous attribution at sign-in, the `Session` row's `tester_id` is set to `NULL`. Every `Question` created in that session also has `tester_id = NULL`. There is no row anywhere in the schema that links those questions back to the tester's identity. **Anonymity is structural, not procedural.**

### 4.2 PII is never stored

If the PII gate rejects an input, the `Question` row records `pii_rejected = true` and a metadata-only payload — **no** `question_text`. The actual user-typed text is dropped server-side after rejection. PII is therefore never written to disk.

### 4.3 Question text retention

For attributed sessions, `question_text` is stored to support Selvon's weekly readout (e.g., "these were the top out-of-corpus questions this week"). For anonymous sessions, we store a **hash** of the question text instead of the text itself, sufficient to count duplicates and track refusal rates without retaining content.

> **Beyond v3 scope — Vizion-internal engineering note.** Storing a hash for anonymous-session question text is a Vizion-internal choice. PRD v3 requires anonymity be respected end-to-end but does not specify hashing. Hashing provides duplicate-detection for the readout while keeping the row content non-reversible. This decision is documented here so Selvon sees it; he does not need to approve it.

### 4.4 Logs versus rows

The `Question` and `Response` rows are the audit-of-record: structured, queryable, retained for the pilot. Application logs (in the orchestrator's stderr) carry the same `request_id` but do not duplicate question content. At pilot end, both are archived; at activation, retention defaults defer to BPL's policy.

---

## 5. Data dictionary

Authoritative description of every entity and attribute. Implementation should match these definitions; deviations should round-trip through this document.

### 5.1 Tester

A staff member participating in the pilot. Created by Vizion at credential issuance; minimal record because the demo environment does not touch BPL identity.

| Marker | Field | Type | Description |
|---|---|---|---|
| **PK** | `tester_id` | `uuid` | Internal identifier. Stable for the duration of the pilot. |
|  | `email` | `varchar(255)` | BPL email used to issue credentials. Never written to question or feedback rows for anonymous sessions. |
|  | `group` | `enum(SME, non_expert)` | Tester group per PRD v3. |
|  | `department` | `varchar(100)` | Recorded only at issuance for cohort balance; not used for routing. |
|  | `issued_at` | `timestamptz` | When credentials were issued. |
|  | `active` | `boolean` | Whether the tester can sign in to the demo environment. |

### 5.2 Session

A single tester sign-in. Each session carries the attribution choice that governs whether questions in that session record the tester ID.

| Marker | Field | Type | Description |
|---|---|---|---|
| **PK** | `session_id` | `uuid` | Token subject. JWT carries this. |
| **FK** | `tester_id` | `uuid → Tester` | Null when `attribution_mode = anonymous`. |
|  | `attribution_mode` | `enum(attributed, anonymous)` | Chosen at sign-in. Binding for the session. |
|  | `started_at` | `timestamptz` | Session creation time. |
|  | `expires_at` | `timestamptz` | `started_at + 8h` per TRD-AUTH-4. |
|  | `user_agent` | `varchar(255)` | Diagnostic only; useful for latency triage. |

### 5.3 Document

A policy document in the curated 100-page corpus. Curated by Selvon; ingested by Vizion. Each document carries exactly one policy type.

| Marker | Field | Type | Description |
|---|---|---|---|
| **PK** | `document_id` | `uuid` | Stable across re-ingest of the same source file. |
|  | `title` | `varchar(255)` | Display name shown in citations. |
|  | `version` | `varchar(50)` | Document-level version (e.g., v3.2). |
| **FK** | `policy_type` | `varchar(80) → PolicyType` | Exactly one. Drives routing on refusal. |
|  | `source_format` | `enum(pdf, docx, md)` | Original file format. |
|  | `ingested_at` | `timestamptz` | Time of last successful ingest. |
|  | `ingest_status` | `enum(indexed, pending, failed)` | Surfaced in the build-team console. |
|  | `page_count` | `int` | Operational truth; sums to 100 across the corpus. |

### 5.4 Chunk

An indexed chunk of a `Document`, with its embedding vector stored in Pinecone (referenced by `chunk_id`; not duplicated relationally).

| Marker | Field | Type | Description |
|---|---|---|---|
| **PK** | `chunk_id` | `uuid` | Used as Pinecone vector ID and as the citation verifier's lookup key. |
| **FK** | `document_id` | `uuid → Document` | Parent document. |
|  | `section_heading` | `varchar(255)` | Used in citation surface (e.g., "Section 3 — Donor Vetting"). |
|  | `ordinal` | `int` | Position within document (for stable re-ingest). |
|  | `text` | `text` | Chunk text. Held alongside Pinecone vector for grounding-check and citation surface. |
|  | `token_count` | `int` | For chunk-strategy diagnostics during build. |

### 5.5 PolicyType

The vocabulary of policy areas. Drives routing. Editable by the build team during the pilot; approved by Selvon before the demo.

| Marker | Field | Type | Description |
|---|---|---|---|
| **PK** | `policy_type` | `varchar(80)` | Slug used everywhere (e.g., `gift_acceptance`, `fundraising_policy`). |
|  | `display_name` | `varchar(255)` | Human-readable label. |
|  | `description` | `text` | What questions fall under this policy area. |

### 5.6 RoutingRule

Maps a policy type to one or more owning teams. Many-to-many through this table satisfies TRD-RTG-3.

| Marker | Field | Type | Description |
|---|---|---|---|
| **PK** | `rule_id` | `uuid` | Synthetic key. |
| **FK** | `policy_type` | `varchar(80) → PolicyType` | Policy area being routed. |
| **FK** | `team_id` | `uuid → OwningTeam` | Team responsible for this policy area. |
|  | `priority` | `int` | Display order when multiple owners exist (e.g., IT before Legal for `data_retention`). |
|  | `approved_at` | `timestamptz` | When Selvon approved this rule. |

> Unique composite index on `(policy_type, team_id)` — one rule per policy/team pairing.

### 5.7 OwningTeam

A BPL team that can be named as the destination on a refusal. Maintained in config alongside the routing rules.

| Marker | Field | Type | Description |
|---|---|---|---|
| **PK** | `team_id` | `uuid` | Synthetic key. |
|  | `name` | `varchar(100)` | Display name (e.g., Development, Legal, IT). |
|  | `contact_hint` | `varchar(255)` | Lightweight reference (general distribution list, intranet page) shown to the user. No individual emails per PRD v3. |

### 5.8 Question

A question submitted by a tester. The orchestrator's audit-of-record per request.

| Marker | Field | Type | Description |
|---|---|---|---|
| **PK** | `request_id` | `uuid` | Echoed in response headers; used to correlate `Feedback`. |
| **FK** | `session_id` | `uuid → Session` | Always set. |
| **FK** | `tester_id` | `uuid → Tester` | Null when session is anonymous (TRD-PRIV-2). |
|  | `question_text` | `text` (nullable) | Stored only for attributed sessions. Anonymous sessions store a hash for de-duplication, not the text. |
|  | `question_hash` | `varchar(64)` | SHA-256 of normalized text. Used across both attribution modes for dedupe. |
|  | `pii_rejected` | `boolean` | True if the PII gate rejected the input. When true, `question_text` is NULL. |
|  | `submitted_at` | `timestamptz` | Server-side receipt time. |
|  | `latency_ms` | `int` | End-to-end response latency. |

### 5.9 Response

The system's reply to a question — either an answer, an out-of-corpus refusal, an invalid-citation refusal, or a PII rejection error.

| Marker | Field | Type | Description |
|---|---|---|---|
| **PK** | `response_id` | `uuid` | Synthetic key. |
| **FK** | `request_id` | `uuid → Question` | One-to-one with the parent question. |
|  | `response_type` | `enum(answer, refusal_oo_corpus, refusal_citation_invalid, error_pii)` | Drives downstream rows. |
|  | `answer_text` | `text` (nullable) | Populated for `response_type = answer`; NULL otherwise. |
|  | `refusal_explanation` | `text` (nullable) | Plain-language refusal text shown to the user. |
|  | `inferred_policy_type` | `varchar(80)` (nullable) | Policy area inferred from top-K retrieval; drives the routing card. |
|  | `created_at` | `timestamptz` | Server-side write time. |

### 5.10 Citation

A reference from an answer back to the chunk that grounded it. At least one row exists per answered `Response` (TRD-GEN-3).

| Marker | Field | Type | Description |
|---|---|---|---|
| **PK** | `citation_id` | `uuid` | Synthetic key. |
| **FK** | `response_id` | `uuid → Response` | Parent response. |
| **FK** | `chunk_id` | `uuid → Chunk` | The chunk that grounded this citation. |
|  | `ordinal` | `int` | Display order in the answer. |

### 5.11 RoutingDecision

The routing record attached to a refusal. Multiple rows per response when multiple teams own the policy area (TRD-RTG-3).

| Marker | Field | Type | Description |
|---|---|---|---|
| **PK** | `decision_id` | `uuid` | Synthetic key. |
| **FK** | `response_id` | `uuid → Response` | Parent refusal response. |
| **FK** | `team_id` | `uuid → OwningTeam` | Team named in the routing card. |
|  | `ordinal` | `int` | Display order when multiple teams. |

### 5.12 Feedback

Tester rating on a specific response. May be anonymous regardless of session attribution (TRD-PRIV-3).

| Marker | Field | Type | Description |
|---|---|---|---|
| **PK** | `feedback_id` | `uuid` | Synthetic key. |
| **FK** | `request_id` | `uuid → Question` | The question whose response is being rated. |
|  | `rating` | `enum(helpful, not_helpful)` | Per TRD-UI-7. |
|  | `comment` | `text` | Optional, max 1000 chars. |
|  | `anonymous` | `boolean` | If true, no `tester_id` is associated regardless of session attribution. |
|  | `submitted_at` | `timestamptz` | Server-side receipt time. |

---

## 6. Worked examples

Three end-to-end traces showing how rows are created across the schema for representative pilot interactions.

### 6.1 Attributed answer with one citation

An SME tester signs in with attribution and asks a question that retrieves cleanly.

- `Session` row: `session_id=s1, tester_id=t1, attribution_mode=attributed`.
- `Question` row: `request_id=q1, session_id=s1, tester_id=t1, question_text="What's our donor vetting threshold?", pii_rejected=false`.
- `Response` row: `response_id=r1, request_id=q1, response_type=answer, answer_text="…", inferred_policy_type=gift_acceptance`.
- `Citation` row: `citation_id=c1, response_id=r1, chunk_id=ck17` (from "Gift Acceptance Policy v3.2 §3").

No `RoutingDecision` rows. Feedback is optional and may be added later.

### 6.2 Anonymous out-of-corpus refusal routed to two teams

A non-expert tester signs in anonymously. They ask about data retention, which is owned by IT and Legal. No chunks meet the grounding threshold.

- `Session` row: `session_id=s2, tester_id=NULL, attribution_mode=anonymous`.
- `Question` row: `request_id=q2, session_id=s2, tester_id=NULL, question_text=NULL` (hash stored separately for dedupe), `pii_rejected=false`.
- `Response` row: `response_id=r2, request_id=q2, response_type=refusal_oo_corpus, refusal_explanation="…", inferred_policy_type=data_retention`.
- `RoutingDecision` rows: `rd1 (response_id=r2, team=IT, ordinal=1)` and `rd2 (response_id=r2, team=Legal, ordinal=2)`.

No `Citation` rows. The tester is shown both owning teams in the routing card.

### 6.3 PII rejection at input

A tester accidentally pastes a name and SSN.

- `Question` row: `request_id=q3, session_id=s3, tester_id=…` (per session), `question_text=NULL, pii_rejected=true, latency_ms=180`.
- `Response` row: `response_id=r3, request_id=q3, response_type=error_pii`.

No `Citation`, no `RoutingDecision`. The PII never reaches Pinecone, OpenAI, or Claude.

---

## 7. Traceability — PRD v3 to ERD

| PRD v3 requirement | Schema realization |
|---|---|
| Anonymity respected end-to-end | `Session.attribution_mode` + nullable `Question.tester_id` + hashed-only anonymous question text |
| Closed corpus, grounded answers | `Citation` FK to `Chunk`; `Response.answer_text` only valid when at least one `Citation` row exists |
| Citation on every answer | `Citation` table is non-empty for `response_type=answer` |
| Routing by policy type to owning team(s) | `PolicyType ↔ OwningTeam` many-to-many through `RoutingRule`; `RoutingDecision` per refusal |
| Multiple owners per policy area | `RoutingRule.priority` + multiple `RoutingDecision` rows per `Response` |
| PII rejected at input, not stored | `Question.pii_rejected` + null `question_text` on rejection; no downstream rows created |
| Selvon-curated 100-page corpus | `Document.ingest_status`, `Document.page_count`, `sum(page_count) = 100` across active corpus |
| 10 testers (SME + non-expert) | `Tester.group` enum, `Tester.active` flag |
| June 15 demo readout content | Aggregate queries over `Question`, `Response`, `RoutingDecision`, `Feedback` by `request_id` and timestamp |

---

## 8. Open questions for Selvon

Items in the schema where Vizion has made a defensible default that Selvon should still see and confirm:

1. **Question text retention for anonymous sessions** — Vizion stores a SHA-256 hash to enable dedupe in the weekly readout. Acceptable, or store nothing at all?
2. **`OwningTeam.contact_hint`** — Vizion defaults to a general team-level reference rather than individual emails, to avoid storing staff PII in the routing config. Acceptable?
3. **`Tester.department`** — recorded at credential issuance for cohort balance only, not used in routing. Acceptable, or should it be omitted entirely?
4. **Retention at pilot end** — Vizion will archive the full schema after June 15 for handoff. Confirm what BPL needs versus what should be deleted.
