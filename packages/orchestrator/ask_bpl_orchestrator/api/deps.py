"""FastAPI dependency wiring."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.hash import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ask_bpl_orchestrator.api.session_dep import session_dependency
from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.db.models import Session, Tester
from ask_bpl_orchestrator.services.jwt_tokens import decode_session_token
from ask_bpl_orchestrator.services.session_service import touch_session

Bearer = HTTPBearer(auto_error=False)


async def jwt_auth(
    credentials: HTTPAuthorizationCredentials = Depends(Bearer),
    db: AsyncSession = Depends(session_dependency),
) -> Dict[str, Any]:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    settings = get_settings()
    try:
        payload = decode_session_token(settings, credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    session_id_raw = payload.get("sub")
    if not session_id_raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    try:
        session_uuid = uuid.UUID(str(session_id_raw))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed session"
        ) from exc

    sess = await db.get(Session, session_uuid)
    if not sess:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Session not found")
    expires = sess.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    await touch_session(db, session_uuid)

    tester_raw = payload.get("tester_id")
    tester_uuid: Optional[uuid.UUID] = None
    if tester_raw:
        try:
            tester_uuid = uuid.UUID(str(tester_raw))
        except ValueError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Bad tester id") from exc

    attribution = str(payload.get("attribution") or "")
    return {
        "session_id": session_uuid,
        "tester_id": tester_uuid,
        "attribution": attribution,
    }


async def authenticate_tester(db: AsyncSession, email: str, access_code: str) -> Optional[Tester]:
    res = await db.execute(select(Tester).where(Tester.email == email.strip().lower()))
    tester = res.scalars().first()
    if tester is None or not tester.active:
        return None
    if bcrypt.verify(access_code, tester.access_code_hash):
        return tester
    return None


JwtAuthClaims = Annotated[dict, Depends(jwt_auth)]
