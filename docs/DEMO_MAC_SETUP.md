# Running Ask BPL on a demo Mac

For demo day on a Mac that has never run Ask BPL (patch 0070). About 20 minutes the first time; after that, one
double-click. The demo needs **internet** (the search index and the AI services are online), **macOS 11 or later**, and
**admin rights** on the Mac to install three programs. It works on **Intel and Apple Silicon** Macs. Homebrew is not
needed (it no longer supports Intel Macs since September 2026); the official installers are used instead.

## What you need

- The project folder on the demo Mac (`git clone` of the repository).
- A **database copy** made on the build team's Mac (step 1). It holds the policies and settings, and **no stored
  questions, answers, sessions or feedback**. It contains BPL internal policy text: move it by AirDrop or USB only.
- The three keys (OpenAI, Anthropic, Pinecone) from the build team. You type them once on the demo Mac; they are never
  shown, never put in the copy, and stay in `packages/orchestrator/.env` on that Mac only.

## Step 1: on the build team's Mac (makes the copy)

```
scripts/demo/export_demo_db.sh
```

It writes `~/Downloads/askbpl_demo_db_YYYYMMDD.dump` and prints its size, document count and md5. Make a new copy
whenever the policies change.

## Step 2: on the demo Mac (once)

1. Install these three, from their official sites (each is a normal Mac installer):
   - **Postgres.app** with PostgreSQL 16: https://postgresapp.com . Move it to Applications, open it, click
     **Initialize**. (In its settings, tick "Automatically start server" if offered.)
   - **Python 3.13**: https://www.python.org/downloads/macos/ (the macOS 64-bit universal installer).
   - **Node.js 22 LTS**: https://nodejs.org (the macOS .pkg).
2. In the project folder:

```
scripts/demo/setup_demo_mac.sh ~/Downloads/askbpl_demo_db_YYYYMMDD.dump
```

It first checks for Postgres 16, Python and Node and lists anything missing with its download link, changing nothing
until all three are there. Then it loads the copy into a new `askbpl` database; asks for the three keys; writes the
settings with fresh local secrets; installs and builds everything; runs the health check, the corpus report and the
vector check (and, if you say yes, a key test costing a fraction of a cent); and puts **Start Ask BPL Demo** and **Stop
Ask BPL Demo** on the Desktop. It stops with a plain message at the first problem. To start over on the same Mac:
`ASKBPL_RESET=1 scripts/demo/setup_demo_mac.sh <copy>` (it replaces that Mac's `askbpl` database and settings).

## Demo day

- Double-click **Start Ask BPL Demo**. It starts the database and the API, runs the health check, serves the widget and
  opens http://localhost:4173. If anything is wrong it says what and does not start.
- Double-click **Stop Ask BPL Demo** afterwards.
- Logs: `~/Library/Logs/AskBPL/` (`api.log`, `web.log`, `doctor.txt`).
- Before the audience arrives, ask one question (for example "How many days of annual leave can I carry over?") to warm
  up the connection.

## If something goes wrong

| Message | What to do |
|---|---|
| "Install these first..." | Install the programs it lists (links above), then run the setup again. |
| "Postgres did not start on port 5432" | Open Postgres.app and click Start (Initialize the first time). |
| "Port 8000 is already in use" | Ask BPL (or something else) is already running: double-click Stop, then Start again. |
| "The health check found something to fix" | Read the [FIX] lines in the window; each says what to do. |
| "The vectors in Pinecone do not match this database" | The Pinecone key or index name is wrong, or the copy is older than the index: make a new copy (step 1). |
| No answers, "temporarily unavailable" | Check the internet connection; then `askbpl-doctor --live` in `packages/orchestrator`. |

## Intel Macs: one package version differs

Every Python package is installed at the exact version tested on the team Mac (`requirements.lock.txt`), from ready-made
builds only. One exception: `cryptography` stopped publishing Intel Mac builds after 48.0.1, so on Intel the setup uses
48.0.1 instead of the locked version (it only backs the login-token library). The full test suite (1783 tests) passes
with that version.
