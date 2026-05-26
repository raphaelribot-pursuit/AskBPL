# Pinecone corpus ingestion — Ask BPL pilot

This document is the operational guide for getting **Selvon’s curated policy corpus** (PRD v3: ~100 pages) into the pilot stack: **Postgres** (chunks + documents) and **Pinecone** (vectors only). Retrieval always **hydrates chunk text from Postgres** using `chunk_id` IDs returned from Pinecone (`packages/orchestrator/ask_bpl_orchestrator/services/retrieval.py`).

---

## 1. What gets stored where

| Layer | Content | Notes |
|--------|---------|--------|
| **Postgres** | `Document`, `Chunk` rows | Full chunk text, titles, policy slugs, ingest status, supersession links (ERD). |
| **Pinecone** | One vector per chunk | Vector `id` = `chunk_id` (UUID string). Metadata is a small mirror for ops/debug; **answers and citations use Postgres**, not Pinecone metadata text. |

**Pinecone vector metadata** (each upsert) — from `ingest/service.py`:

- `chunk_id` (string)
- `document_id` (string)
- `policy_type` (string, same as `--policy` / `PolicyType.policy_type`)
- `title` (document title)
- `version` (version label from CLI)

PII must **never** be pasted into corpus files for ingestion; the **input gate** blocks questions at ask-time (TRD-GRD-1/2). Ingested documents are assumed to be **library-approved policy text**.

---

## 2. Pinecone index (create once per environment)

1. In [Pinecone console](https://app.pinecone.io/), create an index whose **name** matches `.env` → `PINECONE_INDEX_NAME` (default `askbpl-pilot`).

2. **Embedding model → dimensions**

   - Default orchestrator setting: `OPENAI_EMBEDDING_MODEL=text-embedding-3-small` (`packages/orchestrator/ask_bpl_orchestrator/config.py`).
   - OpenAI’s **`text-embedding-3-small`** returns **1536** dimensions with default API parameters (what this codebase uses).
   - Create the Pinecone index with **dimension = 1536** and metric **`cosine`** (standard for normalized embedding similarity).

3. **Serverless / host**

   - If Pinecone shows a **host URL** for the index (serverless), set `PINECONE_HOST` in `.env` to that value (see `.env.example`). The client uses it in `get_pinecone_index()` (`services/pinecone_client.py`).

4. **API key**

   - Set `PINECONE_API_KEY` in `.env`. Without it, ingest **still writes Postgres** but **skips** `upsert` / `delete` (no-op paths in `pinecone_bulk_*`), and `/questions/ask` retrieval returns **no vector matches** — useful only for DB-only experiments.

---

## 3. Environment checklist (orchestrator)

From repo root `.env` (see `.env.example`):

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Async Postgres URL (`postgresql+asyncpg://…`). |
| `OPENAI_API_KEY` | Required for **embeddings** at ingest and at ask-time. |
| `OPENAI_EMBEDDING_MODEL` | Must match the dimension you used when creating the Pinecone index. |
| `PINECONE_API_KEY` | Required for real vector upsert/query. |
| `PINECONE_INDEX_NAME` | Index name in Pinecone. |
| `PINECONE_HOST` | Optional; required for typical serverless index URLs. |
| `CHUNK_SIZE_TOKENS` / `CHUNK_OVERLAP_TOKENS` | Defaults 800 / 100; tune only with care (re-ingest all documents after change). |

---

## 4. Before first ingest

1. **Postgres up** — e.g. `docker compose -f infra/docker-compose.yml up -d` (see root `README.md`).

2. **Migrations** — `cd packages/orchestrator && alembic upgrade head`.

3. **Seed policy types + routing + demo tester** — `askbpl-seed`  
   This loads `packages/orchestrator/config/routing_seed.yaml`. Every `--policy` value you pass to ingest **must** be a `slug` listed there (`gift_acceptance`, `fundraising_policy`, `data_retention`, `generic_policy`, …).

---

## 5. Supported file formats

The ingest CLI accepts **`.pdf`**, **`.docx`**, **`.md`**, **`.markdown`**, **`.txt`** under the path you pass (`ingest/cli.py` → `loaders.py` → `ocr_fallback.py` for PDFs).

**Scanned PDFs (no text layer):** per-page pypdf extraction uses **OCR** when a page has fewer than `OCR_MIN_CHARS_PER_PAGE` characters (default 100). Install the Python extra **`pip install -e '.[ocr]'`** plus system **Tesseract** and **Poppler** (e.g. `brew install tesseract poppler`; Linux: `tesseract-ocr`, `poppler-utils`). Set **`OCR_ENABLED=false`** to force pypdf-only. Without the extra or binaries, thin pages are left empty (same as before OCR).

Recommended for pilot drafts:

- **Markdown** (`.md`) for fast iterations and clear headings (future: section extraction; today `section_heading` is stored as `NULL` unless extended).

---

## 6. Ingest CLI reference

Entry point: `askbpl-ingest` (`pyproject.toml`).

```bash
cd packages/orchestrator
# activate venv, pip install -e '.[dev]' as in root README
```

### 6.1 Single file (smoke test)

```bash
askbpl-ingest \
  --path ./sample_corpus/readme/fundraising_overview.md \
  --corpus-root ./sample_corpus \
  --policy fundraising_policy \
  --title "Fundraising overview (sample)" \
  --version pilot-draft
```

Rules:

- `--path` may be a **file** or a **directory** (recursive).
- `--corpus-root` must be a **parent** of `--path` (used for stable `source_path` / deterministic `document_id`).

### 6.2 Whole folder

```bash
askbpl-ingest \
  --path ./sample_corpus/readme \
  --corpus-root ./sample_corpus \
  --policy generic_policy \
  --version pilot-draft
```

Use **`--policy`** that matches the **dominant** routing domain for those files, or run ingest **per folder** with different slugs if you split corpus by policy area.

### 6.3 Replace a document (PRD §8.5)

After ingesting a new version of a document:

1. Note the **old** `document_id` (UUID) from `GET /admin/documents` (Basic auth).

2. Ingest the new file with:

```bash
askbpl-ingest \
  --path ./path/to/New_Gift_Policy.md \
  --corpus-root ./sample_corpus \
  --policy gift_acceptance \
  --supersedes <OLD_DOCUMENT_UUID>
```

Effects: old document marked superseded, **old chunk vectors deleted** from Pinecone, old chunks hidden from retrieval (`superseded_by_document_id`).

---

## 7. Verify ingestion

1. **Admin JSON** — `GET {API}/admin/documents` with `ADMIN_BASIC_USER` / `ADMIN_BASIC_PASSWORD`: expect `ingest_status`, page/chunk counts, policy slugs aligned with wireframe “Corpus” screen (Screen 4).

2. **Pinecone console** — index vector count should rise after bulk upsert (batch size 200 in code).

3. **Ask path** — sign in via demo tester, ask a question that should hit an ingested chunk; citations should list `document_title` / `section_heading` from Postgres (`AskPilotShell` citation chips).

4. **No Pinecone** — if API key omitted, documents/chunks still appear in Postgres but **retrieval scores empty** → expect refusals or low grounding unless you rely on non-vector paths (not applicable in current pilot code).

---

## 8. Operational notes for the build team (Wireframe Screen 4)

| Wireframe concept | Implementation today |
|-------------------|----------------------|
| “Re-ingest all” | Run `askbpl-ingest` over corpus dirs with correct `--policy` per batch; no single admin button yet. |
| “Edit routing” | Edit `config/routing_seed.yaml` and re-run **`askbpl-seed`** (or future admin API). |
| Document table / status pills | `GET /admin/documents` + `ingest_status` on `Document` (`indexed`, `failed`, etc.). |

---

## 9. Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| `Policy X missing — run routing seed` | `askbpl-seed` not run, or typo in `--policy`. |
| `Corpus root must be parent of target path` | `--corpus-root` not an ancestor of `--path`. |
| Pinecone dimension mismatch | Index dimension ≠ embedding model output (fix index or model). |
| Ingest marks `failed`, 0 vectors | Loader threw (corrupt PDF, bad path); see Postgres `Document.ingest_status` and logs. |
| Ask returns no citations | No / low retrieval: missing Pinecone key, wrong index/host, or threshold `GROUNDING_THRESHOLD` too high vs scores. |

---

## 10. Traceability

- **TRD**: IGN-*, RET-*, GEN-3/4 (grounding + citations), RTG-* (routing slugs must exist before ingest).
- **Code**: `ask_bpl_orchestrator/ingest/service.py`, `ingest/cli.py`, `ingest/chunking.py`, `services/retrieval.py`, `services/pinecone_client.py`.
- **Requirements matrix**: `docs/requirements-matrix.md`.

When the real **100-page Selvon corpus** is finalized, repeat §6 per file or batched directories, then re-run demo acceptance (`docs/demo_acceptance.md`).
