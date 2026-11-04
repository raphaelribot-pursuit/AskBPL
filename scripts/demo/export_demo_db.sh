#!/usr/bin/env bash
# Ask BPL demo, step 1 (on the build team's Mac): export a copy of the database for the demo Mac (patch 0070).
#
# The copy holds the policies, their passages, the routing rules and settings: what the demo needs to answer, matching
# the vectors already in Pinecone. It leaves OUT every stored question, answer, citation, session and feedback row.
# It contains BPL internal policy text: carry it by AirDrop or USB, never commit it or email it.
#
# Usage: scripts/demo/export_demo_db.sh [output-file]     (default: ~/Downloads/askbpl_demo_db_YYYYMMDD.dump)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="$REPO/packages/orchestrator/.env"
OUT="${1:-$HOME/Downloads/askbpl_demo_db_$(date +%Y%m%d).dump}"

[ -f "$ENV_FILE" ] || { echo "No settings file at $ENV_FILE. Run this on the Mac that already runs Ask BPL."; exit 1; }
URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2- | sed 's/+asyncpg//')"
[ -n "$URL" ] || { echo "DATABASE_URL is not set in $ENV_FILE."; exit 1; }

. "$REPO/scripts/demo/_tools.sh"
PG_BIN="$(find_pg_bin)" || PG_BIN="$(dirname "$(command -v pg_dump)")"
PG_DUMP="$PG_BIN/pg_dump"

echo "Exporting the Ask BPL database (no questions, answers, sessions or feedback)..."
"$PG_DUMP" --format=custom --no-owner --no-privileges \
  --exclude-table-data=questions --exclude-table-data=responses --exclude-table-data=citations \
  --exclude-table-data=feedback --exclude-table-data=routing_decisions --exclude-table-data=sessions \
  --file "$OUT" "$URL"
chmod 600 "$OUT"

DOCS="$(psql "$URL" -Atc 'select count(*) from documents')"
CHUNKS="$(psql "$URL" -Atc 'select count(*) from chunks')"
echo
echo "Done: $OUT"
echo "  $(du -h "$OUT" | cut -f1), $DOCS documents, $CHUNKS passages; md5 $(md5 -q "$OUT")"
echo "  Copy it to the demo Mac (AirDrop or USB), then run scripts/demo/setup_demo_mac.sh there."
