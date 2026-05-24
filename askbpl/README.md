# Ask BPL — Steps 01–02: Ingestion, Retrieval, Generation

**Ask BPL** is a closed-corpus Retrieval-Augmented Generation (RAG) policy assistant for Brooklyn Public Library (BPL), built by **Vizion** with engineering partner **Denward Lee Aulder**. Client lead: **Selvon Smith** (BPL). The June 15 demo targets staff who need authoritative answers from internal policy documents only — never from general internet knowledge or model pretraining.

This directory contains the **Step 01–02** Python pipeline: ingest policy PDFs into Pinecone, verify retrieval, tune the grounding threshold, and generate grounded answers with Claude.

## Setup

1. **Python 3.11+** recommended.

   ```bash
   cd askbpl
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copy environment template and add API keys (or rely on repo-root `.env`):

   ```bash
   cp .env.example .env
   # OPENAI_API_KEY, PINECONE_API_KEY, ANTHROPIC_API_KEY
   ```

3. Place the six BPL policy PDFs in `corpus/`.

## Run order

**Step 01 — ingest + retrieval check**

```bash
python -m ingestion.ingest
python -m verification.verify_retrieval
```

**Step 02 — threshold tuning + generation**

```bash
python -m verification.tune_threshold
python -m verification.verify_generation
python -m orchestrator.cli "Who is eligible for annual leave?"
```

## Step 02 definition of done

1. `tune_threshold` recommends a threshold with ≥ 20/24 in-scope retrieval passes.
2. `verify_generation` returns ≥ 18/24 grounded answers with valid citations.
3. `orchestrator.cli` returns an answer (not refusal) for in-scope pilot questions.
4. Out-of-corpus questions refuse at the retrieval gate (no Claude call below threshold).

## Config reference

| Path | Purpose |
|------|---------|
| `config/retrieval.yaml` | `top_k`, `grounding_threshold`, tuner candidates (TRD-RET-3) |
| `config/generation.yaml` | Pinned Claude model (TRD-GEN-1) |
| `config/embeddings.yaml` | OpenAI embedding model (TRD-RET-1) |
| `config/routing.yaml` | `policy_type` → owning team(s) |
| `state/ingestion_state.json` | Per-document ingest status |
| `state/threshold_tuning.json` | Latest threshold calibration report |

## Architecture (Step 02)

```
Question → embed → Pinecone top-K → threshold gate → Claude → citation verifier → answer/refusal + routing
```

No LangChain, no HTTP API, no PII gate in this step — those ship with the full orchestrator package.

## Step 01 recap

Step 01 acceptance: **≥ 20/24** on `verify_retrieval`. Re-ingest is idempotent (content-hash vector IDs).
