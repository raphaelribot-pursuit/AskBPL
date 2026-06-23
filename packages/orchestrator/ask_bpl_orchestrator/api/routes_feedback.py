"""Feedback submissions."""

from __future__ import annotations

from datetime import datetime, timezone

import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from ask_bpl_orchestrator.api.deps import SessionClaims
from ask_bpl_orchestrator.api.response_session import attach_public_session_header
from ask_bpl_orchestrator.api.session_dep import DbSessionDep
from ask_bpl_orchestrator.db.models import Feedback as FeedbackORM
from ask_bpl_orchestrator.db.models import FeedbackRating, Question

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackPayload(BaseModel):
    request_id: uuid.UUID
    rating: FeedbackRating
    comment: str | None = Field(default=None, max_length=1000)
    anonymous_override: bool = False


async def submit_feedback(claims: dict, body: FeedbackPayload, db: DbSessionDep) -> dict:
    q = (
        (
            await db.execute(select(Question).where(Question.request_id == body.request_id))
        )
        .scalars()
        .first()
    )
    if q is None:
        raise HTTPException(status_code=404, detail="request not found")
    if q.session_id != claims["session_id"]:
        raise HTTPException(status_code=403, detail="question does not belong to this session")

    existing = (
        (
            await db.execute(select(FeedbackORM).where(FeedbackORM.request_id == body.request_id))
        )
        .scalars()
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="feedback exists")

    row = FeedbackORM(
        request_id=body.request_id,
        rating=body.rating,
        comment=(body.comment or None),
        anonymous=body.anonymous_override,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()

    return {"status": "ok"}


@router.post("/")
async def submit_feedback_route(
    request: Request,
    claims: SessionClaims,
    body: FeedbackPayload,
    db: DbSessionDep,
):
    result = await submit_feedback(claims, body, db)
    return attach_public_session_header(request, JSONResponse(content=result))
