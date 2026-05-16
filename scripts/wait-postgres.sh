#!/usr/bin/env bash
# Wait until infra/docker-compose Postgres is accepting connections (max ~60s).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
for i in $(seq 1 60); do
  if docker compose -f infra/docker-compose.yml exec -T postgres pg_isready -U askbpl -d askbpl >/dev/null 2>&1; then
    echo "Postgres is ready."
    exit 0
  fi
  sleep 1
done
echo "Timeout waiting for Postgres (docker compose -f infra/docker-compose.yml up -d ?)" >&2
exit 1
