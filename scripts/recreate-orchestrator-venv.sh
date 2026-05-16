#!/usr/bin/env bash
# Recreate packages/orchestrator/.venv with Python 3.11+ (matches CI).
# Usage: from repo root — ./scripts/recreate-orchestrator-venv.sh
# Or:    PYTHON=python3.10 ./scripts/recreate-orchestrator-venv.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCH="$ROOT/packages/orchestrator"
cd "$ORCH"

pick_python() {
  if [[ -n "${PYTHON:-}" ]] && command -v "$PYTHON" >/dev/null 2>&1; then
    if "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      echo "$PYTHON"
      return
    fi
  fi
  for c in python3.12 python3.11 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        echo "$c"
        return
      fi
    fi
  done
  echo ""
}

PY="$(pick_python)"
if [[ -z "$PY" ]]; then
  echo "No Python 3.10+ on PATH. Install 3.11 (recommended, matches CI), e.g.: brew install python@3.11" >&2
  exit 1
fi

echo "Using: $($PY --version) ($PY)"
rm -rf .venv
"$PY" -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/pip install -e '.[dev]'
echo "OK — $(./.venv/bin/python --version)"
