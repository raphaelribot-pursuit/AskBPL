#!/usr/bin/env bash
# Ask BPL demo: stop the API and the widget (patch 0070). The database keeps running; it costs nothing idle.
RUN="$HOME/Library/Logs/AskBPL/run"
for svc in web api; do
  if [ -f "$RUN/$svc.pid" ]; then kill "$(cat "$RUN/$svc.pid")" 2>/dev/null; rm -f "$RUN/$svc.pid"; fi
done
for port in "${ASKBPL_API_PORT:-8000}" "${ASKBPL_WEB_PORT:-4173}"; do
  pids="$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null)"; [ -n "$pids" ] && kill $pids 2>/dev/null
done
echo "Ask BPL stopped."
