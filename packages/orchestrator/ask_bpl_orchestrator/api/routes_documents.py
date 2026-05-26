"""Pilot document text for side-by-side citation viewer."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ask_bpl_orchestrator.api.deps import JwtAuthClaims
from ask_bpl_orchestrator.api.session_dep import DbSessionDep
from ask_bpl_orchestrator.db.models import Chunk, Document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/{document_id}/text")
async def get_document_text(
    document_id: str,
    claims: JwtAuthClaims,  # noqa: ARG001 — auth gate
    db: DbSessionDep,
) -> dict:
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid document_id") from exc

    doc = await db.get(Document, doc_uuid)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    result = await db.execute(
        select(Chunk).where(Chunk.document_id == doc_uuid).order_by(Chunk.ordinal)
    )
    chunks = result.scalars().all()

    full_text_parts: list[str] = []
    chunk_data: list[dict] = []
    current_offset = 0

    for chunk in chunks:
        text = chunk.text or ""
        start = current_offset
        end = current_offset + len(text)
        chunk_data.append(
            {
                "chunk_id": str(chunk.chunk_id),
                "ordinal": chunk.ordinal,
                "text": text,
                "section_heading": chunk.section_heading,
                "start_offset": start,
                "end_offset": end,
            }
        )
        full_text_parts.append(text)
        current_offset = end + 2

    return {
        "document_id": str(doc.document_id),
        "title": doc.title,
        "policy_type": doc.policy_type,
        "full_text": "\n\n".join(full_text_parts),
        "chunks": chunk_data,
    }
