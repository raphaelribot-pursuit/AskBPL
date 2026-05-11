# Ask BPL orchestrator

FastAPI service: auth, `/ask`, `/feedback`, admin aggregation, ingest CLI.

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn ask_bpl_orchestrator.main:app --reload
```
