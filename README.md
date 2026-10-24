# Ask BPL — AI Policy Assistant (pilot)

Internal AI assistant for Brooklyn Public Library policy Q&A. Scope and requirements: [AskBPL_PRD_v3.md](AskBPL_PRD_v3.md), [AskBPL_TRD.md](AskBPL_TRD.md), [AskBPL_ERD.md](AskBPL_ERD.md).

## Documentation

| Doc | Purpose |
|-----|---------|
| [**Pinecone corpus ingestion**](docs/PINECONE_CORPUS_INGEST.md) | Index setup (1536 / cosine), env vars, `askbpl-ingest` CLI, supersede flow, verification, troubleshooting — **pilot corpus → Postgres + Pinecone**. |
| [**Wireframe ↔ code parity**](docs/pilot/WIREFRAME_PARITY.md) | Maps clickable wireframe v3 screens 1–4 to `AskPilotShell` / `App` and notes UI gaps. |
| [**Tester setup guide**](docs/TESTER_SETUP.md) | Plain-language setup for the test version, with `askbpl-doctor`, a read-only preflight check (patch 0019). |
| [Requirements matrix](docs/requirements-matrix.md) | TRD IDs → modules. |
| [Demo acceptance](docs/demo_acceptance.md) | Scripted rehearsal. |

## Quick start (local)

1. Copy [`.env.example`](.env.example) to `packages/orchestrator/.env` (the app reads `.env` from the folder it runs in, so a copy left at the repo root is not found). Set the API keys (OpenAI, Pinecone, Anthropic), `JWT_SECRET_KEY` (the app will not start without it) and `admin_basic_password` for the `/admin/*` routes.
2. Start Postgres: `docker compose -f infra/docker-compose.yml up -d`
3. `cd packages/orchestrator && python3 -m venv .venv && source .venv/bin/activate`
4. `pip install -e '.[dev]'`
5. `alembic upgrade head`
6. `askbpl-seed` *(loads `config/routing_seed.yaml` + demo tester)*
7. API: `uvicorn ask_bpl_orchestrator.main:app --reload --host 0.0.0.0 --port 8000`
8. Web demo: copy [`packages/web-demo/.env.example`](packages/web-demo/.env.example) → `.env.local`, then `npm install && npm run dev`
9. Optional smoke corpus: `askbpl-ingest --path ./sample_corpus/readme/fundraising_overview.md --corpus-root ./sample_corpus --policy fundraising_policy` — full runbook in [**docs/PINECONE_CORPUS_INGEST.md**](docs/PINECONE_CORPUS_INGEST.md).

**New version supersedes old (PRD §8.5):** ingest the replacement file, then pass `--supersedes <old_document_uuid>` (from `/admin/documents`). That marks the old row, removes its vectors from Pinecone, and hides its chunks from retrieval.

## Packages

- `packages/orchestrator` — FastAPI orchestrator (`askbpl-ingest`, `askbpl-seed`, `askbpl-latency-smoke`)
- `packages/web-demo` — Vite + React pilot modal (`App.tsx`)

## Traceability

- [`docs/PINECONE_CORPUS_INGEST.md`](docs/PINECONE_CORPUS_INGEST.md) — corpus → Postgres + Pinecone
- [`docs/pilot/WIREFRAME_PARITY.md`](docs/pilot/WIREFRAME_PARITY.md) — wireframe v3 ↔ code
- [`docs/requirements-matrix.md`](docs/requirements-matrix.md) — condensed TRD → code routing
- [`docs/AskBPL_ERD.dbml`](docs/AskBPL_ERD.dbml) — DB diagram export
- [`docs/demo_acceptance.md`](docs/demo_acceptance.md) — scripted §13 rehearsal
