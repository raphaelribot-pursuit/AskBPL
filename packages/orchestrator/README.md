# Ask BPL orchestrator

FastAPI service: auth, `/ask`, `/feedback`, admin aggregation, ingest CLI.

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
