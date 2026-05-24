"""Pinecone retrieval with pinned embeddings (TRD-RET-1, TRD-RET-2)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import yaml

from ingestion.embedder import Embedder, load_embeddings_config
from ingestion.pinecone_client import PineconeClient, load_pinecone_config
from ingestion.policy_metadata import PROJECT_ROOT

logger = logging.getLogger(__name__)

RETRIEVAL_PATH = PROJECT_ROOT / "config" / "retrieval.yaml"


@dataclass(frozen=True)
class RetrievedChunk:
    """One chunk returned from vector search (TRD-RET-5)."""

    vector_id: str
    score: float
    source_document: str
    source_filename: str
    section: Optional[str]
    policy_type: str
    document_version: str
    chunk_index: int
    text: str


def load_retrieval_config(path: Path = RETRIEVAL_PATH) -> dict:
    """Load retrieval parameters including grounding threshold (TRD-RET-3)."""
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def max_score(chunks: List[RetrievedChunk]) -> float:
    """Return highest similarity score in a result set."""
    if not chunks:
        return 0.0
    return max(c.score for c in chunks)


def infer_policy_type(chunks: List[RetrievedChunk]) -> Optional[str]:
    """Infer policy from the highest-scoring chunk's metadata."""
    if not chunks:
        return None
    best = max(chunks, key=lambda c: c.score)
    return best.policy_type or None


class Retriever:
    """Embed questions and query Pinecone with metadata (TRD-RET-1, TRD-RET-2)."""

    def __init__(
        self,
        retrieval_config: dict | None = None,
        embedder: Embedder | None = None,
        pinecone: PineconeClient | None = None,
    ) -> None:
        self.config = retrieval_config or load_retrieval_config()
        self.top_k: int = int(self.config["top_k"])
        self.grounding_threshold: float = float(self.config["grounding_threshold"])
        self._embedder = embedder or Embedder(load_embeddings_config())
        self._pine = pinecone or PineconeClient(load_pinecone_config())

    def query(self, question: str, *, top_k: int | None = None) -> List[RetrievedChunk]:
        """Retrieve top-K chunks for a question (TRD-RET-2)."""
        k = top_k if top_k is not None else self.top_k
        vector = self._embedder.embed_query(question)
        response = self._pine.index.query(vector=vector, top_k=k, include_metadata=True)
        chunks: List[RetrievedChunk] = []
        for match in response.get("matches") or []:
            meta = match.get("metadata") or {}
            vector_id = str(match.get("id") or "")
            if not vector_id:
                continue
            section_raw = meta.get("section")
            section = str(section_raw) if section_raw else None
            if section == "":
                section = None
            chunks.append(
                RetrievedChunk(
                    vector_id=vector_id,
                    score=float(match.get("score") or 0.0),
                    source_document=str(meta.get("source_document") or ""),
                    source_filename=str(meta.get("source_filename") or ""),
                    section=section,
                    policy_type=str(meta.get("policy_type") or ""),
                    document_version=str(meta.get("document_version") or ""),
                    chunk_index=int(meta.get("chunk_index") or 0),
                    text=str(meta.get("chunk_text") or ""),
                )
            )
        chunks.sort(key=lambda c: c.score, reverse=True)
        logger.debug("Retrieved %s chunks; best score=%.3f", len(chunks), max_score(chunks))
        return chunks

    def meets_threshold(self, chunks: List[RetrievedChunk], threshold: float | None = None) -> bool:
        """True when best chunk score clears grounding threshold (TRD-RET-3)."""
        cutoff = threshold if threshold is not None else self.grounding_threshold
        return bool(chunks) and max_score(chunks) >= cutoff
