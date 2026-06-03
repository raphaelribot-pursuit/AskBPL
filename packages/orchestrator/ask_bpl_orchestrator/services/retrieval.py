"""OpenAI embeddings plus Pinecone top-K fused with Postgres chunk bodies."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.db.models import Chunk, Document
from ask_bpl_orchestrator.services.langchain_embeddings import embed_query
from ask_bpl_orchestrator.services.pinecone_client import get_pinecone_index


def _pinecone_query_matches(response: Any) -> List[Any]:
    """Pinecone v5+ returns QueryResponse structs; older samples used plain dicts."""
    if isinstance(response, dict):
        return list(response.get("matches") or [])
    matches = getattr(response, "matches", None)
    return list(matches or [])


def _pinecone_match_id(match: Any) -> Optional[str]:
    if isinstance(match, dict):
        raw = match.get("id")
    else:
        raw = getattr(match, "id", None)
    return str(raw) if raw else None


def _pinecone_match_score(match: Any) -> float:
    if isinstance(match, dict):
        raw = match.get("score")
    else:
        raw = getattr(match, "score", None)
    return float(raw or 0.0)


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    score: float
    document_id: uuid.UUID
    title: str
    policy_type: str
    version: str
    section_heading: Optional[str]
    text: str


class VectorRetriever:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def embed_question(self, question: str) -> List[float]:
        return await embed_query(question, settings=self.settings)

    def _pinecone_index(self):
        return get_pinecone_index()

    async def _pinecone_scores(self, question: str, top_k: int) -> Dict[uuid.UUID, float]:
        if not self.settings.pinecone_api_key:
            return {}
        vector = await self.embed_question(question)
        idx = self._pinecone_index()
        pine = await asyncio.to_thread(
            idx.query,
            vector=vector,
            top_k=top_k,
            include_metadata=False,
        )
        scores: Dict[uuid.UUID, float] = {}

        for m in _pinecone_query_matches(pine):
            cid_raw = _pinecone_match_id(m)
            if not cid_raw:
                continue
            try:
                cid = uuid.UUID(cid_raw)
            except ValueError:
                continue
            scores[cid] = _pinecone_match_score(m)
        return scores

    async def _hydrate_ordered(self, db: AsyncSession, ordered: Dict[uuid.UUID, float]) -> List[RetrievedChunk]:
        if not ordered:
            return []

        identities = list(ordered.keys())

        stmt = (
            select(Chunk, Document)
            .join(Document, Chunk.document_id == Document.document_id)
            .where(Chunk.chunk_id.in_(identities))
            .where(Document.superseded_by_document_id.is_(None))
        )
        rows = (await db.execute(stmt)).all()
        mapper = {chunk.chunk_id: (chunk, document) for chunk, document in rows}

        hydrated: List[RetrievedChunk] = []
        # preserve descending Pinecone similarity order based on insertion dict order unreliable
        ranked = sorted(ordered.items(), key=lambda kv: kv[1], reverse=True)

        for chunk_id, score in ranked:
            row = mapper.get(chunk_id)
            if not row:
                continue

            chunk_row, doc_row = row
            hydrated.append(
                RetrievedChunk(
                    chunk_id=chunk_row.chunk_id,
                    score=score,
                    document_id=chunk_row.document_id,
                    title=doc_row.title,
                    policy_type=doc_row.policy_type,
                    version=doc_row.version,
                    section_heading=chunk_row.section_heading,
                    text=chunk_row.text,
                )
            )
        return hydrated

    async def query(self, db: AsyncSession, question: str, top_k: int) -> List[RetrievedChunk]:
        scores = await self._pinecone_scores(question, top_k)
        return await self._hydrate_ordered(db, scores)


def max_score(chunks: List[RetrievedChunk]) -> float:
    if not chunks:
        return 0.0
    return max(c.score for c in chunks)
