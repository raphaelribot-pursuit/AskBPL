# Ask BPL orchestrator

FastAPI service: auth, `/ask`, `/feedback`, admin aggregation, ingest CLI.

**Python:** `requires-python >= 3.10`. CI uses **3.11** — match locally (see `.python-version` for pyenv).

### Local venv (pip)

From repo root:

```bash
./scripts/recreate-orchestrator-venv.sh
# or: PYTHON=python3.11 ./scripts/recreate-orchestrator-venv.sh
```

Then start Postgres and apply schema + seed (env vars from repo `.env.example`):

```bash
docker compose -f infra/docker-compose.yml up -d
./scripts/wait-postgres.sh
cd packages/orchestrator
export DATABASE_URL=postgresql+asyncpg://askbpl:askbpl_dev_password@localhost:5434/askbpl
export JWT_SECRET_KEY=dev-change-me-at-least-32-characters-long
export ADMIN_BASIC_PASSWORD=dev-admin-secret
export ANTHROPIC_API_KEY=sk-ant-placeholder
.venv/bin/alembic upgrade head
.venv/bin/askbpl-seed
.venv/bin/pytest -q
```

Shorthand from repo root (same env exports required): `make orchestrator-test`.

### uv (alternative)

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn ask_bpl_orchestrator.main:app --reload
```

## Corpus → Pinecone + Postgres

See repo root **[docs/PINECONE_CORPUS_INGEST.md](../../docs/PINECONE_CORPUS_INGEST.md)** (index dimensions, `.env`, `askbpl-seed` before ingest, `askbpl-ingest` examples, supersede flow, verification).

Quick smoke after seed:

```bash
askbpl-ingest \
  --path ./sample_corpus/readme/fundraising_overview.md \
  --corpus-root ./sample_corpus \
  --policy fundraising_policy
```
