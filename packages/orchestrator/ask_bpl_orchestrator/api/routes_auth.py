"""Authentication routes."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from ask_bpl_orchestrator.api.session_dep import DbSessionDep
from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.db.models import AttributionMode, Session
from ask_bpl_orchestrator.services.jwt_tokens import build_claims, create_session_token

from .deps import authenticate_tester

router = APIRouter(prefix="/auth", tags=["auth"])


class SignInRequest(BaseModel):
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    access_code: str = Field(min_length=4)
    attribution_mode: AttributionMode
    user_agent: str | None = None


class SignInResponse(BaseModel):
    token: str
    session_id: str
    expires_at: datetime


@router.post("/sign-in", response_model=SignInResponse)
@router.post("/login", response_model=SignInResponse, include_in_schema=True)
async def sign_in(payload: SignInRequest, response: Response, db: DbSessionDep):
    settings = get_settings()
    tester = await authenticate_tester(db, payload.email, payload.access_code)
    if tester is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    session_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=settings.session_ttl_hours)

    attribution = payload.attribution_mode
    session_row = Session(
        session_id=session_id,
        tester_id=(
            tester.tester_id if attribution == AttributionMode.attributed else None
        ),
        attribution_mode=attribution,
        started_at=now,
        expires_at=expires_at,
        user_agent=payload.user_agent[:255] if payload.user_agent else None,
    )

    claims = build_claims(
        session_id=session_id,
        tester_id=(
            tester.tester_id if attribution == AttributionMode.attributed else None
        ),
        attribution=attribution.value,
    )

    db.add(session_row)
    await db.commit()

    jwt_token = create_session_token(settings, claims)
    response.headers["X-Session-ID"] = str(session_id)

    return SignInResponse(
        token=jwt_token,
        session_id=str(session_id),
        expires_at=expires_at,
    )
