# Ask BPL — AI Policy Assistant (pilot)

Internal AI assistant for Brooklyn Public Library policy Q&A. Scope and requirements: [AskBPL_PRD_v3.md](AskBPL_PRD_v3.md), [AskBPL_TRD.md](AskBPL_TRD.md), [AskBPL_ERD.md](AskBPL_ERD.md).

## Quick start (local)

1. Copy [`.env.example`](.env.example) to `.env` and set API keys (OpenAI, Pinecone, Anthropic) plus `admin_basic_password` for the `/admin/*` routes.
2. Start Postgres: `docker compose -f infra/docker-compose.yml up -d`
3. `cd packages/orchestrator && python3 -m venv .venv && source .venv/bin/activate`
4. `pip install -e '.[dev]'`
5. `alembic upgrade head`
6. `askbpl-seed` *(loads `config/routing_seed.yaml` + demo tester)*
7. API: `uvicorn ask_bpl_orchestrator.main:app --reload --host 0.0.0.0 --port 8000`
8. Web demo: copy [`packages/web-demo/.env.example`](packages/web-demo/.env.example) → `.env.local`, then `npm install && npm run dev`
9. Optional smoke corpus: `askbpl-ingest --path ./sample_corpus/readme/fundraising_overview.md --corpus-root ./sample_corpus --policy fundraising_policy`

## Packages

- `packages/orchestrator` — FastAPI orchestrator (`askbpl-ingest`, `askbpl-seed`, `askbpl-latency-smoke`)
- `packages/web-demo` — Vite + React pilot modal (`App.tsx`)

## Traceability

- [`docs/requirements-matrix.md`](docs/requirements-matrix.md) — condensed TRD → code routing
- [`docs/AskBPL_ERD.dbml`](docs/AskBPL_ERD.dbml) — DB diagram export
- [`docs/demo_acceptance.md`](docs/demo_acceptance.md) — scripted §13 rehearsal
