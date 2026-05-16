## Ask BPL pilot — scripted acceptance rehearsal (§13 shorthand)

Goal: repeatable walkthrough proving closed-corpus safeguards, ingestion visibility, routing, modal UX.

### Preconditions

1. `docker compose -f infra/docker-compose.yml up -d`
2. `cd packages/orchestrator`
3. **Python 3.10+** (CI uses **3.11** — match that locally to avoid typing/FastAPI collection errors on 3.9):

   `python3.11 -m venv .venv && source .venv/bin/activate`  

   (Use `python3.10` if 3.11 is unavailable.)

4. `pip install -e '.[dev]'`
5. `alembic upgrade head`
6. `askbpl-seed`

### Automated smoke

```
askbpl-latency-smoke --iterations 3
```

Healthy output prints medians for `/healthz`, `/auth/sign-in`, and `/questions/ask`. Use `--skip-ask` for environments without seeded corpus.

### Corpus + modal

```
askbpl-ingest --path ./sample_corpus --corpus-root . --policy generic_policy --version demo-1
cd ../web-demo && npm install && npm run dev
```

Pilot credentials (seeded): **pilot-demo@bklynlibrary.org / DEMO2026**.

### Acceptance checklist pointers

| Item | Observation |
| --- | --- |
| PII refusal | Prompt with email/phone; expect `400` (`error_pii`) and persisted question row flagged. |
| Refusal routing | Prompt unrelated to seeded corpus → refusal card + RoutingDecision surfaced in UI/API. |
| Citations | When answer returns, clickable chips obey `DOCUMENTS_PUBLIC_BASE_URL` / `VITE_DOCUMENTS_PUBLIC_BASE`. |
| Build-team dashboards | Navigate to modal “Build-team readout”; enter `admin_basic_*` creds → JSON mirrors TRD aggregates. |

**Request IDs:** Every response includes `X-Request-ID` (or echoes a client-sent `X-Request-ID`). Collect it from **any** orchestrator response (including `/healthz`) for support or log correlation — not only `/questions/ask`.

**Readiness:** `GET /readyz` runs `SELECT 1` against Postgres — use behind the load balancer for “dependencies up” (keep `GET /healthz` for simple process checks).

**Admin tests / CI:** Set `ADMIN_BASIC_PASSWORD` in `.env` locally; CI injects a non-empty secret so `/admin/summary` basic-auth tests pass.

Log each `X-Request-ID` from `/questions/ask` (and other calls) for audit replay.
