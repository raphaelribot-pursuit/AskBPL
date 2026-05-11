"""Feedback submissions."""

from __future__ import annotations

from datetime import datetime, timezone

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from ask_bpl_orchestrator.api.session_dep import DbSessionDep
from ask_bpl_orchestrator.db.models import Feedback as FeedbackORM
from ask_bpl_orchestrator.db.models import FeedbackRating, Question

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackPayload(BaseModel):
    request_id: uuid.UUID
    rating: FeedbackRating
    comment: str | None = Field(default=None, max_length=1000)
    anonymous_override: bool = False


@router.post("/")
async def submit_feedback(body: FeedbackPayload, db: DbSessionDep):
    q = (
        (
            await db.execute(select(Question).where(Question.request_id == body.request_id))
        )
        .scalars()
        .first()
    )
    if q is None:
        raise HTTPException(status_code=404, detail="request not found")

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
