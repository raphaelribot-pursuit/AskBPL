"""Corpus ingestion pipeline (documents -> chunks -> Postgres + Pinecone)."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from ask_bpl_orchestrator.services.langchain_embeddings import embed_query

from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.db.models import Chunk, Document, IngestStatus, PolicyType, SourceFormat
from ask_bpl_orchestrator.db.session import async_session_factory
from ask_bpl_orchestrator.ingest.chunking import split_text_with_sections
from ask_bpl_orchestrator.ingest.loaders import load_bytes
from ask_bpl_orchestrator.services.pinecone_client import get_pinecone_index

DOC_NS = uuid.UUID("6fa459ea-ee8a-3ca4-894e-db77e160355e")


def _document_uuid(rel_path: str) -> uuid.UUID:
    return uuid.uuid5(DOC_NS, rel_path.strip().lower())


def _chunk_uuid(document_id: uuid.UUID, ordinal: int, snippet: str) -> uuid.UUID:
    digest = hashlib.sha256(snippet.encode("utf-8")).hexdigest()
    return uuid.uuid5(DOC_NS, f"{document_id}-{ordinal}-{digest}")


def approx_word_tokens(snippet: str) -> int:
    return max(1, len(snippet.split()))


async def embed_snippet(snippet: str) -> List[float]:
    cfg = get_settings()
    return await embed_query(snippet, settings=cfg)


def pinecone_bulk_delete(identifiers: Sequence[str]) -> None:
    identifiers = list(identifiers)
    if not identifiers:
        return

    cfg = get_settings()
    if not cfg.pinecone_api_key:
        return

    index = get_pinecone_index()

    BATCH = 200
    for start in range(0, len(identifiers), BATCH):
        index.delete(ids=identifiers[start : start + BATCH])


def pinecone_bulk_upsert(rows: List[Tuple[str, List[float], dict]]) -> None:
    if not rows:
        return

    cfg = get_settings()
    if not cfg.pinecone_api_key:
        return

    index = get_pinecone_index()

    payloads = [{"id": rid, "values": vec, "metadata": meta} for rid, vec, meta in rows]
    index.upsert(vectors=payloads)


async def ingest_file(
    *,
    absolute_path: Path,
    corpus_root: Path,
    policy_slug: str,
    title: str,
    version_label: str,
    supersedes_document_id: Optional[uuid.UUID] = None,
) -> None:
    cfg = get_settings()

    suffix = absolute_path.suffix.lower()

    FORMAT_MAP = {
        ".pdf": SourceFormat.pdf,
        ".docx": SourceFormat.docx,
        ".md": SourceFormat.md,
        ".markdown": SourceFormat.md,
        ".txt": SourceFormat.md,
    }

    source_format = FORMAT_MAP.get(suffix)
    if not source_format:
        raise ValueError(f"Unsupported ingest suffix `{suffix}` for {absolute_path}")

    rel = str(absolute_path.resolve().relative_to(corpus_root.resolve())).strip()
    doc_uuid = _document_uuid(rel)

    try:
        full_text = load_bytes(absolute_path)
    except Exception:  # noqa: BLE001 ingestion must mark failure
        async with async_session_factory() as db_session:
            existing = (
                (
                    await db_session.execute(select(Document).where(Document.document_id == doc_uuid))
                )
                .scalars()
                .first()
            )

            if existing:
                existing.ingest_status = IngestStatus.failed
                existing.title = title
                existing.version = version_label
                existing.policy_type = policy_slug
                existing.source_format = source_format
                existing.source_path = rel
                await db_session.merge(existing)
            else:
                await db_session.merge(
                    Document(
                        document_id=doc_uuid,
                        title=title,
                        version=version_label,
                        policy_type=policy_slug,
                        source_format=source_format,
                        source_path=rel,
                        ingest_status=IngestStatus.failed,
                        page_count=0,
                    )
                )
            await db_session.commit()
        raise

    segmented = split_text_with_sections(
        full_text,
        model_name=cfg.openai_embedding_model,
        chunk_size=cfg.chunk_size_tokens,
        overlap=cfg.chunk_overlap_tokens,
    )

    staging: List[Tuple[str, str, int]] = []

    async with async_session_factory() as db_session:
        registered_policy = (
            (
                await db_session.execute(select(PolicyType).where(PolicyType.policy_type == policy_slug))
            )
            .scalars()
            .first()
        )

        if not registered_policy:
            raise RuntimeError(f"Policy `{policy_slug}` missing — run routing seed.")

        legacy_ids_rows = (
            (
                await db_session.execute(select(Chunk.chunk_id).where(Chunk.document_id == doc_uuid))
            )
            .scalars()
            .all()
        )
        legacy_ids = [str(value) for value in legacy_ids_rows]

        if legacy_ids:
            pinecone_bulk_delete(legacy_ids)
            await db_session.execute(delete(Chunk).where(Chunk.document_id == doc_uuid))

        document_row = Document(
            document_id=doc_uuid,
            title=title,
            version=version_label,
            policy_type=policy_slug,
            source_format=source_format,
            ingested_at=datetime.now(timezone.utc),
            ingest_status=IngestStatus.indexed,
            page_count=max(1, len(full_text) // 2000),
            source_path=rel,
        )

        await db_session.merge(document_row)

        for ordinal, segment in enumerate(segmented, start=1):
            snippet = segment.text
            chunk_uuid = _chunk_uuid(doc_uuid, ordinal, snippet)
            staging.append((str(chunk_uuid), snippet, ordinal))

            db_session.add(
                Chunk(
                    chunk_id=uuid.UUID(chunk_uuid),
                    document_id=doc_uuid,
                    section_heading=segment.section_heading,
                    ordinal=ordinal,
                    text=snippet,
                    token_count=approx_word_tokens(snippet),
                    content_hash=hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
                )
            )

        await db_session.commit()

    if not staging:
        return

    embeddings = await asyncio.gather(*(embed_snippet(snippet) for _, snippet, _ in staging))

    payloads: List[Tuple[str, List[float], dict]] = []
    meta_base = {
        "document_id": str(doc_uuid),
        "policy_type": policy_slug,
        "title": title,
        "version": version_label,
    }

    for (cid, body, _), vector in zip(staging, embeddings):
        meta_payload = dict(meta_base)
        meta_payload["chunk_id"] = cid
        payloads.append((cid, vector, meta_payload))

    await asyncio.to_thread(pinecone_bulk_upsert, payloads)

    if supersedes_document_id is not None:
        if supersedes_document_id == doc_uuid:
            raise ValueError("`supersedes` cannot point at the document being ingested")
        async with async_session_factory() as sup_sess:
            prior = await sup_sess.get(Document, supersedes_document_id)
            if prior is None:
                raise ValueError(f"No document found for supersedes={supersedes_document_id}")
            prev_chunks = (
                (
                    await sup_sess.execute(
                        select(Chunk.chunk_id).where(Chunk.document_id == supersedes_document_id)
                    )
                )
                .scalars()
                .all()
            )
            prev_ids = [str(cid) for cid in prev_chunks]
            if prev_ids:
                await asyncio.to_thread(pinecone_bulk_delete, prev_ids)
            prior.superseded_by_document_id = doc_uuid
            await sup_sess.commit()
