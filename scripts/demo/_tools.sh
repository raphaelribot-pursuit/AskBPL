# Shared by the demo scripts (patch 0071): find Postgres 16, Python and Node without requiring Homebrew.
# Homebrew no longer supports Intel Macs (Tier 3 from September 2026), so each tool is looked for in its official
# installer's location first: Postgres.app, python.org, nodejs.org; Homebrew is used only if it is there.

find_pg_bin() {
  local d
  for d in "/Applications/Postgres.app/Contents/Versions/16/bin" "/Applications/Postgres.app/Contents/Versions/latest/bin"; do
    [ -x "$d/pg_isready" ] && { echo "$d"; return 0; }
  done
  if command -v brew >/dev/null 2>&1; then d="$(brew --prefix postgresql@16 2>/dev/null)/bin"; [ -x "$d/pg_isready" ] && { echo "$d"; return 0; }; fi
  return 1
}

start_postgres() {
  # Postgres.app starts its server when the app opens (Initialize it once); Homebrew's runs as a service.
  if [ -d "/Applications/Postgres.app" ]; then open -ga Postgres
  elif command -v brew >/dev/null 2>&1; then brew services start postgresql@16 >/dev/null 2>&1; fi
}

find_python() {
  # Python 3.14 first (the team Mac's version), then 3.13, then 3.12: every pinned package has a ready-made build for
  # these (checked 2026-11-03). Newer versions are NOT accepted: on the demo Mac, Python 3.15 failed (no httptools 0.8.0
  # build for it, patch 0073), so an unchecked version is reported as missing rather than tried.
  local p
  for p in /Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14 /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 \
           /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
           "$(command -v python3.14 2>/dev/null)" "$(command -v python3.13 2>/dev/null)" "$(command -v python3.12 2>/dev/null)" \
           "$(command -v python3 2>/dev/null)"; do
    [ -n "$p" ] && [ -x "$p" ] && "$p" -c 'import sys; sys.exit(0 if (3, 12) <= sys.version_info[:2] <= (3, 14) else 1)' 2>/dev/null && { echo "$p"; return 0; }
  done
  return 1
}

macos_major() { sw_vers -productVersion 2>/dev/null | cut -d. -f1; }

node_ok() {
  # Vite 8 needs Node ^20.19 or >= 22.12.
  command -v node >/dev/null 2>&1 || return 1
  node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit((a===20&&b>=19)||(a===22&&b>=12)||a>22?0:1)'
}
