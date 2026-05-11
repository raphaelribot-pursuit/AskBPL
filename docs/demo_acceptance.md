## Ask BPL pilot — scripted acceptance rehearsal (§13 shorthand)

Goal: repeatable walkthrough proving closed-corpus safeguards, ingestion visibility, routing, modal UX.

### Preconditions

1. `docker compose -f infra/docker-compose.yml up -d`
2. `cd packages/orchestrator`
3. `python3 -m venv .venv && source .venv/bin/activate`
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

Log each `X-Request-ID` header emitted by `/questions/ask` for audit replay.
