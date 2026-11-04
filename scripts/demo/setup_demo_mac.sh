#!/usr/bin/env bash
# Ask BPL demo, step 2 (once, on the demo Mac): install what Ask BPL needs, load the database copy, ask for the keys,
# build the widget, check everything, and put Start / Stop icons on the Desktop (patch 0070). See docs/DEMO_MAC_SETUP.md.
#
# Usage: scripts/demo/setup_demo_mac.sh /path/to/askbpl_demo_db_YYYYMMDD.dump
# Needs: macOS 11 or later (Intel or Apple Silicon), internet, Postgres.app (PostgreSQL 16), Python 3.13 and Node 22
# from their official installers (Homebrew also works where installed), and the three keys. Never prints a key.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
ORCH="$REPO/packages/orchestrator"; WEB="$REPO/packages/web-demo"
DUMP="${1:-}"
say() { printf '\n== %s\n' "$*"; }
fail() { printf '\nSTOPPED: %s\n' "$*"; exit 1; }

[ "$(uname)" = "Darwin" ] || fail "This script is for macOS."
. "$REPO/scripts/demo/_tools.sh"
MACOS="$(macos_major)"
[ -n "$MACOS" ] && [ "$MACOS" -ge 11 ] || fail "This Mac runs macOS $(sw_vers -productVersion 2>/dev/null); Ask BPL needs macOS 11 or later."
[ -n "$DUMP" ] && [ -f "$DUMP" ] || fail "Give the database copy as the first argument, e.g. scripts/demo/setup_demo_mac.sh ~/Downloads/askbpl_demo_db_20261103.dump"
say "1/7 Checking for Postgres 16, Python and Node (nothing is installed or changed yet)"
missing=""
PG_BIN="$(find_pg_bin)" || missing="$missing
  - PostgreSQL 16: download Postgres.app (the version with PostgreSQL 16) from https://postgresapp.com , move it to
    Applications, open it and click Initialize."
PY="$(find_python)" || missing="$missing
  - Python 3.14 (or 3.13): the macOS installer from https://www.python.org/downloads/macos/ (Intel and Apple Silicon)."
node_ok || missing="$missing
  - Node.js 22 (LTS): the macOS installer from https://nodejs.org (choose the .pkg)."
[ -z "$missing" ] || fail "Install these first, then run this script again:$missing"
export PATH="$PG_BIN:$PATH"
echo "Postgres: $PG_BIN"; echo "Python:   $PY ($("$PY" -V 2>&1))"; echo "Node:     $(node -v)"; echo "This Mac: $(uname -m)"
start_postgres
for _ in $(seq 1 30); do pg_isready -q -h localhost -p 5432 && break; sleep 1; done
pg_isready -q -h localhost -p 5432 || fail "Postgres did not start on port 5432. Open Postgres.app and click Start (or Initialize the first time)."

say "2/7 Creating the askbpl database and loading the copy"
if psql -h localhost -d postgres -Atc "select 1 from pg_database where datname='askbpl'" | grep -q 1; then
  if [ "${ASKBPL_RESET:-}" = "1" ]; then dropdb -h localhost askbpl; else
    fail "A database named askbpl already exists on this Mac. To replace it with the copy, run: ASKBPL_RESET=1 $0 $DUMP"; fi
fi
DB_PW="$("$PY" -c 'import secrets; print(secrets.token_urlsafe(18))')"
if psql -h localhost -d postgres -Atc "select 1 from pg_roles where rolname='askbpl'" | grep -q 1; then
  psql -h localhost -d postgres -qc "ALTER ROLE askbpl WITH LOGIN PASSWORD '$DB_PW'"
else
  psql -h localhost -d postgres -qc "CREATE ROLE askbpl WITH LOGIN PASSWORD '$DB_PW'"
fi
createdb -h localhost -O askbpl askbpl
DB_URL="postgresql://askbpl:$DB_PW@localhost:5432/askbpl"
pg_restore --no-owner --no-privileges --exit-on-error -d "$DB_URL" "$DUMP"
echo "Loaded: $(psql "$DB_URL" -Atc 'select count(*) from documents') documents, $(psql "$DB_URL" -Atc 'select count(*) from chunks') passages."

say "3/7 Settings (keys are typed here once, kept only in packages/orchestrator/.env on this Mac, never shown)"
if [ -f "$ORCH/.env" ] && [ "${ASKBPL_RESET:-}" != "1" ]; then
  fail "$ORCH/.env already exists. Remove it or run with ASKBPL_RESET=1 to write a new one."
fi
# The pdfium PDF reader's Intel Mac build needs macOS 13. It is only used when policies are loaded, never by the demo,
# so on macOS 11 and 12 it is left out and the default reader is configured instead.
PDF_READER="pdfium"; [ "$(uname -m)" = "x86_64" ] && [ "$MACOS" -lt 13 ] && PDF_READER="pypdf"
read -rsp "OpenAI API key: " OPENAI_KEY; echo
read -rsp "Anthropic API key: " ANTHROPIC_KEY; echo
read -rsp "Pinecone API key: " PINECONE_KEY; echo
read -rp  "Pinecone index name [askbpl-pilot]: " PINECONE_INDEX; PINECONE_INDEX="${PINECONE_INDEX:-askbpl-pilot}"
[ -n "$OPENAI_KEY" ] && [ -n "$ANTHROPIC_KEY" ] && [ -n "$PINECONE_KEY" ] || fail "All three keys are needed."
ACCESS_CODE="$("$PY" -c 'import secrets; print(secrets.token_urlsafe(9))')"
OPENAI_KEY="$OPENAI_KEY" ANTHROPIC_KEY="$ANTHROPIC_KEY" PINECONE_KEY="$PINECONE_KEY" PINECONE_INDEX="$PINECONE_INDEX" \
DB_URL="postgresql+asyncpg://askbpl:$DB_PW@localhost:5432/askbpl" ACCESS_CODE="$ACCESS_CODE" PDF_READER="$PDF_READER" \
"$PY" - "$REPO/.env.example" "$ORCH/.env" <<'PY'
import os, re, secrets, sys
src, dst = sys.argv[1], sys.argv[2]
values = {
    "DATABASE_URL": os.environ["DB_URL"],
    "JWT_SECRET_KEY": secrets.token_urlsafe(48),
    "PILOT_DEMO_ACCESS_CODE": os.environ["ACCESS_CODE"],
    "ADMIN_BASIC_PASSWORD": secrets.token_urlsafe(18),
    "OPENAI_API_KEY": os.environ["OPENAI_KEY"],
    "ANTHROPIC_API_KEY": os.environ["ANTHROPIC_KEY"],
    "PINECONE_API_KEY": os.environ["PINECONE_KEY"],
    "PINECONE_INDEX_NAME": os.environ["PINECONE_INDEX"],
    "ALLOW_TEST_INDEX": "true",
    "PDF_READER": os.environ["PDF_READER"],
}
out, seen = [], set()
for line in open(src, encoding="utf-8").read().splitlines():
    m = re.match(r"^([A-Z_]+)=", line)
    if m and m.group(1) in values:
        out.append(f"{m.group(1)}={values[m.group(1)]}"); seen.add(m.group(1))
    else:
        out.append(line)
out += [f"{k}={v}" for k, v in values.items() if k not in seen]
fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
PY
unset OPENAI_KEY ANTHROPIC_KEY PINECONE_KEY
echo "Wrote $ORCH/.env (readable only by you)."

say "4/7 Python environment and database check"
cd "$ORCH"
[ -d .venv ] || "$PY" -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip
# The exact versions tested on the team Mac (requirements.lock.txt). One exception on Intel Macs: cryptography stopped
# publishing Intel Mac builds after 48.0.1, so that pin is lowered (it only backs the login token library).
LOCK="$ORCH/requirements.lock.txt"
if [ "$(uname -m)" = "x86_64" ]; then
  LOCK="$(mktemp)"; sed -E 's/^cryptography==.*/cryptography==48.0.1/' "$ORCH/requirements.lock.txt" > "$LOCK"
  # macOS 11-12 on Intel: no pypdfium2 build (needs 13); not used by the demo (PDF_READER=pypdf above).
  if [ "$MACOS" -lt 13 ]; then sed -i '' -E '/^pypdfium2==/d' "$LOCK"; fi
fi
pip install -q --only-binary=:all: -r "$LOCK" || fail "A Python package could not be installed from a ready-made build (see above)."
pip install -q --no-deps -e .
[ "$PDF_READER" = "pypdf" ] && echo "Note: macOS $MACOS on Intel: the optional pdfium PDF reader was left out (not used by the demo)."
alembic upgrade head
askbpl-seed >/dev/null   # this Mac's own demo sign-in code; routing rules as on the team Mac

say "5/7 Building the widget"
cd "$WEB"
printf 'VITE_API_BASE_URL=http://localhost:8000\n' > .env.local
npm ci --no-audit --no-fund
npm run build

say "6/7 Checking everything (read-only)"
cd "$ORCH"
askbpl-doctor || true
askbpl-corpus-report --strict --summary-only || fail "The corpus report found something to reconcile (see above)."
askbpl-vector-report --strict || fail "The vectors in Pinecone do not match this database (see above). Check the Pinecone key and index name."
read -rp "Test the three keys now? Costs a fraction of a cent. [Y/n] " LIVE
if [ "${LIVE:-Y}" != "n" ] && [ "${LIVE:-Y}" != "N" ]; then askbpl-doctor --live || fail "A key did not work (see above)."; fi

say "7/7 Start and Stop icons on the Desktop"
chmod +x "$REPO/scripts/demo/"*.sh
for name in "Start Ask BPL Demo" "Stop Ask BPL Demo"; do
  target="$REPO/scripts/demo/$( [ "$name" = "Start Ask BPL Demo" ] && echo start_demo.sh || echo stop_demo.sh )"
  printf '#!/usr/bin/env bash\nexec "%s"\n' "$target" > "$HOME/Desktop/$name.command"
  chmod +x "$HOME/Desktop/$name.command"
done
echo
echo "All set. Double-click 'Start Ask BPL Demo' on the Desktop. The widget opens at http://localhost:4173."
