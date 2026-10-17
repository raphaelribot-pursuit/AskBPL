"""Pilot document text for side-by-side citation viewer."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

from ask_bpl_orchestrator.api.deps import SessionClaims
from ask_bpl_orchestrator.api.response_session import attach_public_session_header
from ask_bpl_orchestrator.api.session_dep import DbSessionDep
from ask_bpl_orchestrator.db.models import Chunk, Document
from ask_bpl_orchestrator.services.eligibility import TEST_INDEX_LABEL, is_retrievable, is_test_index_source

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/{document_id}/text")
async def get_document_text(
    document_id: str,
    request: Request,
    claims: SessionClaims,  # noqa: ARG001 — session gate for public demo
    db: DbSessionDep,
) -> JSONResponse:
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid document_id") from exc

    doc = await db.get(Document, doc_uuid)
    if doc is None or not is_retrievable(doc):
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
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "start_offset": start,
                "end_offset": end,
            }
        )
        full_text_parts.append(text)
        current_offset = end + 2

    payload = {
        "document_id": str(doc.document_id),
        "title": doc.title,
        "policy_type": doc.policy_type,
        "test_index": is_test_index_source(doc),
        "index_label": TEST_INDEX_LABEL if is_test_index_source(doc) else None,
        "full_text": "\n\n".join(full_text_parts),
        "chunks": chunk_data,
    }
    return attach_public_session_header(request, JSONResponse(content=payload))
