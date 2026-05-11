"""Build-team aggregate endpoints (basic auth)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import func, nulls_last, select

from ask_bpl_orchestrator.api.session_dep import DbSessionDep
from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.db.models import (
    Document,
    FeedbackRating,
    Question,
    Response,
    ResponseType,
    RoutingDecision,
)
from ask_bpl_orchestrator.db.models import Feedback as FeedbackORM

router = APIRouter(prefix="/admin", tags=["admin"])
basic_auth = HTTPBasic(auto_error=False)


async def guard_admin(creds: Annotated[HTTPBasicCredentials | None, Depends(basic_auth)]):
    settings = get_settings()
    username = creds.username if creds else ""
    password = creds.password if creds else ""
    if not username.strip() or not password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Auth required")
    if (
        credentials_missing(settings)
        or not secrets.compare_digest(username, settings.admin_basic_user)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Auth required")

    expected = settings.admin_basic_password.encode("utf-8")
    incoming = password.encode("utf-8")
    if not secrets.compare_digest(incoming, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Auth required")


def credentials_missing(settings):  # guard empty password deployments
    return settings.admin_basic_password.strip() == ""


@router.get("/summary", dependencies=[Depends(guard_admin)])
async def aggregate_summary(db: DbSessionDep) -> dict:
    now = datetime.now(timezone.utc)
    week_floor = now - timedelta(days=7)

    questions_last_week = int(
        (
            await db.execute(
                select(func.count()).where(Question.submitted_at >= week_floor)
            )
        ).scalar_one()
        or 0
    )

    total_questions = int(
        (
            await db.execute(select(func.count()).select_from(Question))
        ).scalar_one()
        or 0
    )
    blocked_pii = int(
        (
            await db.execute(select(func.count()).where(Question.pii_rejected.is_(True)))
        ).scalar_one()
        or 0
    )
    refusal_count = int(
        (
            await db.execute(
                select(func.count()).where(Response.response_type != ResponseType.answer)
            )
        ).scalar_one()
        or 0
    )

    fb_helpful = int(
        (
            await db.execute(
                select(func.count()).where(FeedbackORM.rating == FeedbackRating.helpful)
            )
        ).scalar_one()
        or 0
    )

    fb_sad = int(
        (
            await db.execute(
                select(func.count()).where(FeedbackORM.rating == FeedbackRating.not_helpful)
            )
        ).scalar_one()
        or 0
    )

    routing_top = (
        (
            await db.execute(
                select(RoutingDecision.team_id, func.count())
                .group_by(RoutingDecision.team_id)
                .order_by(func.count().desc())
                .limit(5)
            )
        ).all()
    )

    ingest_groups = (
        (
            await db.execute(
                select(Document.ingest_status, func.count())
                .group_by(Document.ingest_status)
                .order_by(func.count())
            )
        ).all()
    )

    return {
        "questions_total": total_questions,
        "questions_submitted_last_7d": questions_last_week,
        "questions_pii_blocked": blocked_pii,
        "responses_non_answer_approx": refusal_count,
        "feedback_helpful": fb_helpful,
        "feedback_not_helpful": fb_sad,
        "routing_team_counts_sample": [
            {"team_id": str(t_id), "count": cnt} for t_id, cnt in routing_top
        ],
        "documents_by_status": [
            {"ingest_status": st.value if hasattr(st, "value") else str(st), "count": cnt}
            for st, cnt in ingest_groups
        ],
    }


@router.get("/documents", dependencies=[Depends(guard_admin)])
async def list_documents(db: DbSessionDep, limit: int = 120) -> dict:
    cap = max(1, min(limit, 500))
    stmt = select(Document).order_by(
        nulls_last(Document.ingested_at.desc()),
        Document.title,
    ).limit(cap)
    rows = (await db.execute(stmt)).scalars().all()

    return {
        "documents": [
            {
                "document_id": str(d.document_id),
                "title": d.title,
                "version": d.version,
                "policy_type": d.policy_type,
                "source_path": d.source_path,
                "source_format": d.source_format.value,
                "ingest_status": d.ingest_status.value,
                "ingested_at": d.ingested_at.isoformat() if d.ingested_at else None,
                "superseded_by_document_id": str(d.superseded_by_document_id)
                if d.superseded_by_document_id
                else None,
            }
            for d in rows
        ],
    }
