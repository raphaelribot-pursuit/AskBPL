"""Session helpers — inactivity-based expiry (TRD-AUTH-4)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.db.models import Session


async def touch_session(db: AsyncSession, session_id: uuid.UUID) -> None:
    """Slide ``expires_at`` forward from now (8h inactivity window)."""
    row = await db.get(Session, session_id)
    if row is None:
        return
    settings = get_settings()
    now = datetime.now(timezone.utc)
    row.expires_at = now + timedelta(hours=settings.session_ttl_hours)
    await db.commit()
