#!/usr/bin/env bash
# Ask BPL demo: start everything and open the widget (patch 0070). Double-click "Start Ask BPL Demo" on the Desktop.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
ORCH="$REPO/packages/orchestrator"; WEB="$REPO/packages/web-demo"
LOGS="$HOME/Library/Logs/AskBPL"; RUN="$LOGS/run"; mkdir -p "$RUN"
API_PORT="${ASKBPL_API_PORT:-8000}"; WEB_PORT="${ASKBPL_WEB_PORT:-4173}"  # overridable for testing
stop_here() { printf '\nNOT STARTED: %s\nPress Return to close this window.' "$*"; read -r _; exit 1; }

echo "Starting Ask BPL..."
PG_BIN="$(brew --prefix postgresql@16 2>/dev/null)/bin"; export PATH="$PG_BIN:$PATH"
brew services start postgresql@16 >/dev/null 2>&1
for _ in $(seq 1 30); do pg_isready -q -h localhost -p 5432 && break; sleep 1; done
pg_isready -q -h localhost -p 5432 || stop_here "The database did not start."

for port in $API_PORT $WEB_PORT; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    stop_here "Port $port is already in use. Is Ask BPL already running? Double-click 'Stop Ask BPL Demo' first."
  fi
done

cd "$ORCH" && . .venv/bin/activate || stop_here "The Python environment is missing. Run scripts/demo/setup_demo_mac.sh first."
askbpl-doctor > "$LOGS/doctor.txt" 2>&1
if grep -q "\[FIX\]" "$LOGS/doctor.txt"; then cat "$LOGS/doctor.txt"; stop_here "The health check found something to fix (above)."; fi

nohup uvicorn ask_bpl_orchestrator.main:app --host 127.0.0.1 --port $API_PORT > "$LOGS/api.log" 2>&1 &
echo $! > "$RUN/api.pid"
for _ in $(seq 1 40); do curl -fsS "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1 && break; sleep 0.5; done
curl -fsS "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1 || stop_here "The API did not start. See $LOGS/api.log"

cd "$WEB" || stop_here "The widget folder is missing."
[ -d dist ] || stop_here "The widget has not been built. Run scripts/demo/setup_demo_mac.sh first."
nohup npx vite preview --host 127.0.0.1 --port $WEB_PORT --strictPort > "$LOGS/web.log" 2>&1 &
echo $! > "$RUN/web.pid"
for _ in $(seq 1 40); do curl -fsS "http://127.0.0.1:$WEB_PORT/" >/dev/null 2>&1 && break; sleep 0.5; done
curl -fsS "http://127.0.0.1:$WEB_PORT/" >/dev/null 2>&1 || stop_here "The widget did not start. See $LOGS/web.log"

[ "${ASKBPL_NO_BROWSER:-}" = "1" ] || open "http://localhost:$WEB_PORT/"
echo "Ask BPL is running at http://localhost:$WEB_PORT/  (logs: $LOGS)"
echo "You can close this window. To stop, double-click 'Stop Ask BPL Demo'."
