# Ask BPL — TRD / PRD requirement matrix

| ID | Requirement (summary) | Primary code / artifact | Notes |
| --- | --- | --- | --- |
| AUTH-3 | Bearer JWT enforced on `/questions/*` | `ask_bpl_orchestrator/api/deps.py` (`jwt_auth`) | Returns 401 on missing/expired payload. |
| AUTH-4 | 8-hour session TTL | `routes_auth.py`, `models.Session.expires_at` | Fixed window from issuance; TTL via `session_ttl_hours`. |
| GEN-6 | Closed corpus + verifier | `generation.py`, `ask_service.handle_ask` citation checks | Drops answer when cites leave retrieval envelope. |
| RET-2 | Pinecone top-K retrieval | `config.Settings.pinecone_top_k`, `retrieval.VectorRetriever.query` | Default K=6. |
| IGN-5 | Upload / ingest dashboards | `/admin/documents`, `/admin/summary` | Served under basic-auth. |
| LOG-4 | Operational summaries | `/admin/summary`, web “Build-team readout” panel | Feedback + routing counts surfaced. |
| UI-7 | Feedback controls | Modal assistant footer + `/feedback/` | Mirrors TRD discrete buttons. |
| GRD-2 | Regex PII categories | `services/pii_gate.py`, `tests/test_pii_gate.py` | Raises 400 before embeddings. |
| AUTH-FEEDBACK | JWT on `POST /feedback/` | `routes_feedback.py`, web `AskPilotShell` | Session must own `request_id`. |
| RET-SUPERSEDED | Exclude superseded documents from hydration | `retrieval.py`, ingest `--supersedes` | PRD §8.5. |
| IGN-1 | Strict ingest loaders | `ingest/loaders.py` | Fails loudly for unknown corpus formats. |
| IGN-4 | Idempotent ingestion | `ingest/service.py` | Stable IDs + deletes orphan vectors before upsert. |

For June demo acceptance §13 reviewers can walk `docs/demo_acceptance.md` after running seed + ingestion.
