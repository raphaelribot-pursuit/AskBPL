"""Corpus ingestion pipeline (documents -> chunks -> Postgres + Pinecone)."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import delete, select

from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.services.langchain_embeddings import embed_query
from ask_bpl_orchestrator.db.models import (
    Chunk,
    Citation,
    Document,
    ExtractionStatus,
    IngestStatus,
    PolicyType,
    SourceFormat,
)
from ask_bpl_orchestrator.db.session import async_session_factory
from ask_bpl_orchestrator.ingest.chunking import split_text_with_sections
from ask_bpl_orchestrator.ingest.extraction_review import ValidatedExtraction
from ask_bpl_orchestrator.ingest.inventory import InventoryRow, apply_row
from ask_bpl_orchestrator.ingest.loaders import load_bytes
from ask_bpl_orchestrator.ingest.provenance import (
    MAX_HEADING_CHARS,
    find_headings,
    heading_at,
    page_from_heading,
    page_range,
)
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


def _is_missing_namespace(exc: Exception) -> bool:
    """Pinecone answers 404 "Namespace not found" when deleting from an index that has
    never received an upsert (the default namespace is created by the first upsert)."""
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    text = str(exc).lower()
    return "namespace not found" in text or (status == 404 and "namespace" in text)


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
        try:
            index.delete(ids=identifiers[start : start + BATCH])
        except Exception as exc:  # noqa: BLE001
            if _is_missing_namespace(exc):
                # Nothing was ever upserted, so there is nothing to delete. This happens on a
                # brand-new index when an earlier ingest wrote Postgres rows but failed before upsert.
                return
            raise


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
    inventory_row: Optional[InventoryRow] = None,
    validated_extraction: Optional[ValidatedExtraction] = None,
    extraction_review_required: bool = False,
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
        # A verified review record replaces automatic extraction: the indexed text is the text a person signed off.
        full_text = validated_extraction.text if validated_extraction is not None else load_bytes(absolute_path)
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

    chunk_size = cfg.chunk_size_tokens
    chunk_overlap = cfg.chunk_overlap_tokens
    if policy_slug == "conflict_of_interest":
        # Pilot COI PDF extracts as one flat body (~few thousand chars) with no
        # markdown headings, so default 800-token windows stay a single chunk.
        # Narrower windows diversify retrieval across the policy until a structured source replaces the PDF path.
        chunk_size = min(chunk_size, 280)
        chunk_overlap = min(chunk_overlap, 50)

    # Confident headings (0013). Under the sentence strategy (0014) they are also where chunks are cut, so a
    # chunk's heading label covers all of it. A validated scan carries its own "## Page N" markers instead.
    confident_headings = [] if validated_extraction is not None else find_headings(full_text.strip())

    segmented = split_text_with_sections(
        full_text,
        model_name=cfg.openai_embedding_model,
        chunk_size=chunk_size,
        overlap=chunk_overlap,
        strategy=cfg.chunk_strategy,
        boundaries=[h.offset for h in confident_headings],
    )

    staging: List[Tuple[str, str, int]] = []

    # Page spans exist only for PDFs read here. Labels describe each chunk; they never alter its text.
    page_spans = getattr(full_text, "pages", None)

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
            await db_session.execute(delete(Citation).where(Citation.chunk_id.in_(legacy_ids_rows)))
            await db_session.execute(delete(Chunk).where(Chunk.document_id == doc_uuid))

        # Re-ingest must NOT reset eligibility: update the existing row in place.
        document_row = await db_session.get(Document, doc_uuid)
        if document_row is None:
            document_row = Document(document_id=doc_uuid)  # default-deny: authority_pending, not test-index
            db_session.add(document_row)
        document_row.title = title
        document_row.version = version_label
        document_row.policy_type = policy_slug
        document_row.source_format = source_format
        document_row.ingested_at = datetime.now(timezone.utc)
        document_row.ingest_status = IngestStatus.indexed
        document_row.page_count = max(1, len(full_text) // 2000)
        document_row.source_path = rel
        # Set on EVERY ingest so a stale 'validated' can never stay attached to newly extracted text.
        if validated_extraction is not None:
            document_row.extraction_status = ExtractionStatus.validated
            document_row.extraction_validated_by = validated_extraction.reviewer
            document_row.extraction_validated_at = validated_extraction.reviewed_on
            document_row.extraction_record_sha256 = validated_extraction.record_sha256
            document_row.page_count = validated_extraction.page_count
        else:
            document_row.extraction_status = (
                ExtractionStatus.review_required if extraction_review_required else ExtractionStatus.standard
            )
            document_row.extraction_validated_by = None
            document_row.extraction_validated_at = None
            document_row.extraction_record_sha256 = None
        if inventory_row is not None:
            apply_row(document_row, inventory_row)
        await db_session.flush()

        for ordinal, segment in enumerate(segmented, start=1):
            snippet = segment.text
            chunk_uuid = _chunk_uuid(doc_uuid, ordinal, snippet)
            staging.append((str(chunk_uuid), snippet, ordinal))

            heading = segment.section_heading
            start_char = getattr(segment, "start_char", None)
            end_char = getattr(segment, "end_char", None)
            page_start = page_end = None
            marker_page = page_from_heading(heading)
            if marker_page is not None:
                # "Page 3" from a validated scan is a page, not a section name.
                page_start = page_end = marker_page
                heading = None
            else:
                if page_spans and start_char is not None and end_char is not None:
                    page_start, page_end = page_range(page_spans, start_char, end_char)
                if heading is None and start_char is not None:
                    heading = heading_at(confident_headings, start_char)  # None unless the strict rule fired
            if heading:
                heading = heading[:MAX_HEADING_CHARS]

            db_session.add(
                Chunk(
                    chunk_id=chunk_uuid,
                    document_id=doc_uuid,
                    section_heading=heading,
                    page_start=page_start,
                    page_end=page_end,
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
