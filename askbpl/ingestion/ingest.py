"""Corpus ingestion entry point (TRD-IGN-1 through TRD-IGN-5)."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from ingestion.chunker import TextChunk, chunk_document, load_chunking_config
from ingestion.embedder import Embedder, load_embeddings_config
from ingestion.parsers import parse_document
from ingestion.pinecone_client import PineconeClient, VectorRecord, load_pinecone_config, make_vector_id
from ingestion.policy_metadata import PROJECT_ROOT, PolicyRecord, load_valid_policy_types, match_policy

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

CORPUS_DIR = PROJECT_ROOT / "corpus"
STATE_DIR = PROJECT_ROOT / "state"
STATE_PATH = STATE_DIR / "ingestion_state.json"


@dataclass
class DocumentStatus:
    """Per-document ingestion outcome (TRD-IGN-5)."""

    filename: str
    policy_type: Optional[str]
    status: str
    chunks: int
    pages: int
    ingested_at: Optional[str]
    error: Optional[str]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_vectors(
    chunks: List[TextChunk],
    embeddings: list,
    policy: PolicyRecord,
    filename: str,
) -> List[VectorRecord]:
    records: List[VectorRecord] = []
    for chunk, emb in zip(chunks, embeddings):
        metadata: Dict[str, Any] = {
            "source_document": policy.source_document,
            "source_filename": filename,
            "section": chunk.section if chunk.section is not None else "",
            "policy_type": policy.policy_type,
            "document_version": policy.document_version,
            "chunk_index": chunk.chunk_index,
            "chunk_text": chunk.text,
        }
        records.append(
            VectorRecord(
                vector_id=make_vector_id(policy.source_document, chunk.text),
                values=emb.embedding,
                metadata=metadata,
            )
        )
    return records


def ingest_corpus() -> dict:
    """Run full corpus ingestion pipeline (TRD-IGN-1 through TRD-IGN-5)."""
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT.parent / ".env")
    valid_types = load_valid_policy_types()
    chunk_cfg = load_chunking_config()
    embed_cfg = load_embeddings_config()
    pine_cfg = load_pinecone_config()

    corpus_files = sorted(
        p for p in CORPUS_DIR.iterdir() if p.is_file() and not p.name.startswith(".")
    )

    if not corpus_files:
        state = {
            "last_run": _utc_now(),
            "embedding_model": embed_cfg["model"],
            "index_name": pine_cfg["index_name"],
            "documents": [],
        }
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        print("No files found in corpus/. Add the six BPL policy PDFs and re-run.")
        print("─" * 69)
        print("Total: 0 documents, 0 chunks, 0 pages — 0 failed")
        return state

    embedder = Embedder(embed_cfg)
    pine = PineconeClient(pine_cfg)

    documents: List[DocumentStatus] = []
    total_chunks = 0
    total_pages = 0
    failed = 0

    for path in corpus_files:
        policy = match_policy(path.name, valid_types)
        if policy is None:
            documents.append(
                DocumentStatus(
                    filename=path.name,
                    policy_type=None,
                    status="Failed",
                    chunks=0,
                    pages=0,
                    ingested_at=_utc_now(),
                    error="unknown_policy_type",
                )
            )
            failed += 1
            continue

        try:
            parsed = parse_document(path)
            if not parsed.text.strip():
                raise ValueError(
                    f"parse_error: empty text ({parsed.empty_pages} empty pages of {parsed.page_count})"
                )

            chunks = chunk_document(parsed.text, chunk_cfg)
            if not chunks:
                raise ValueError("parse_error: no chunks produced")

            embeddings = embedder.embed_texts([c.text for c in chunks])
            vectors = _build_vectors(chunks, embeddings, policy, path.name)
            pine.upsert_records(vectors)

            documents.append(
                DocumentStatus(
                    filename=path.name,
                    policy_type=policy.policy_type,
                    status="Indexed",
                    chunks=len(chunks),
                    pages=parsed.page_count,
                    ingested_at=_utc_now(),
                    error=None,
                )
            )
            total_chunks += len(chunks)
            total_pages += parsed.page_count

        except NotImplementedError as exc:
            documents.append(
                DocumentStatus(
                    filename=path.name,
                    policy_type=policy.policy_type,
                    status="Failed",
                    chunks=0,
                    pages=0,
                    ingested_at=_utc_now(),
                    error=str(exc),
                )
            )
            failed += 1
        except Exception as exc:
            reason = str(exc)
            if not reason.startswith("parse_error"):
                reason = f"ingest_error: {reason}"
            documents.append(
                DocumentStatus(
                    filename=path.name,
                    policy_type=policy.policy_type,
                    status="Failed",
                    chunks=0,
                    pages=0,
                    ingested_at=_utc_now(),
                    error=reason,
                )
            )
            failed += 1

    state = {
        "last_run": _utc_now(),
        "embedding_model": embed_cfg["model"],
        "index_name": pine_cfg["index_name"],
        "documents": [asdict(doc) for doc in documents],
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    _print_summary(documents, total_chunks, total_pages, failed)
    return state


def _print_summary(documents: List[DocumentStatus], total_chunks: int, total_pages: int, failed: int) -> None:
    """Print one-line-per-document ingestion summary."""
    name_width = 42
    for doc in documents:
        if doc.status == "Indexed" and doc.policy_type:
            policy = match_policy(doc.filename, load_valid_policy_types())
            label = policy.source_document if policy else doc.filename
            print(
                f"[Indexed]  {label:<{name_width}} {doc.chunks:>3} chunks  {doc.pages:>2} pages"
            )
        elif doc.status == "Failed":
            print(f"[Failed]   {doc.filename:<{name_width}} {doc.error or 'unknown error'}")
        else:
            print(f"[{doc.status}]   {doc.filename}")

    indexed_count = sum(1 for d in documents if d.status == "Indexed")
    print("─" * 69)
    print(
        f"Total: {indexed_count} documents, {total_chunks} chunks, {total_pages} pages — {failed} failed"
    )


def main() -> None:
    """CLI entry: python -m ingestion.ingest."""
    try:
        ingest_corpus()
    except Exception as exc:
        logger.exception("Ingestion failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
