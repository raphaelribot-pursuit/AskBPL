"""Public demo sessions — no sign-in required; attributed to the pilot demo tester."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.db.models import AttributionMode, Session, Tester


def claims_from_session(sess: Session) -> Dict[str, Any]:
    attribution = (
        sess.attribution_mode.value
        if isinstance(sess.attribution_mode, AttributionMode)
        else str(sess.attribution_mode)
    )
    return {
        "session_id": sess.session_id,
        "tester_id": sess.tester_id,
        "attribution": attribution,
    }


async def load_session_claims(db: AsyncSession, session_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    sess = await db.get(Session, session_id)
    if not sess:
        return None
    expires = sess.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        return None
    return claims_from_session(sess)


async def create_attributed_demo_session(db: AsyncSession) -> Session:
    settings = get_settings()
    email = settings.public_demo_tester_email.strip().lower()
    res = await db.execute(select(Tester).where(Tester.email == email))
    tester = res.scalars().first()
    if tester is None or not tester.active:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Public demo is unavailable (demo tester not configured).",
        )

    session_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=settings.session_ttl_hours)
    session_row = Session(
        session_id=session_id,
        tester_id=tester.tester_id,
        attribution_mode=AttributionMode.attributed,
        started_at=now,
        expires_at=expires_at,
    )
    db.add(session_row)
    await db.commit()
    await db.refresh(session_row)
    return session_row
