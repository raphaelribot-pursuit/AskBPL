# Local backend + DB helpers (CI uses the same Postgres image + Python 3.11).
.PHONY: postgres postgres-down postgres-wait orchestrator-venv orchestrator-migrate orchestrator-test

postgres:
	docker compose -f infra/docker-compose.yml up -d

postgres-down:
	docker compose -f infra/docker-compose.yml down

postgres-wait:
	./scripts/wait-postgres.sh

orchestrator-venv:
	./scripts/recreate-orchestrator-venv.sh

# Requires env (see repo .env.example): DATABASE_URL, JWT_SECRET_KEY, ADMIN_BASIC_PASSWORD, ANTHROPIC_API_KEY, etc.
orchestrator-migrate: postgres postgres-wait
	cd packages/orchestrator && .venv/bin/alembic upgrade head && .venv/bin/askbpl-seed

orchestrator-test: postgres postgres-wait
	cd packages/orchestrator && .venv/bin/alembic upgrade head && .venv/bin/askbpl-seed && .venv/bin/pytest -q
