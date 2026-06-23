"""FastAPI dependency wiring."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.hash import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ask_bpl_orchestrator.api.session_dep import session_dependency
from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.db.models import Session, Tester
from ask_bpl_orchestrator.services.jwt_tokens import decode_session_token
from ask_bpl_orchestrator.services.public_session import (
    create_attributed_demo_session,
    load_session_claims,
)
from ask_bpl_orchestrator.services.session_service import touch_session

Bearer = HTTPBearer(auto_error=False)


async def _claims_from_bearer(
    credentials: HTTPAuthorizationCredentials,
    db: AsyncSession,
) -> Dict[str, Any]:
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


async def jwt_auth(
    credentials: HTTPAuthorizationCredentials = Depends(Bearer),
    db: AsyncSession = Depends(session_dependency),
) -> Dict[str, Any]:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return await _claims_from_bearer(credentials, db)


async def resolve_session(
    request: Request,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(Bearer)],
    x_session_id: Annotated[Optional[str], Header(alias="X-Session-ID")] = None,
    db: AsyncSession = Depends(session_dependency),
) -> Dict[str, Any]:
    """Bearer JWT (legacy testers) or public demo session via ``X-Session-ID``."""
    if credentials:
        return await _claims_from_bearer(credentials, db)

    if x_session_id:
        try:
            session_uuid = uuid.UUID(x_session_id.strip())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Session-ID",
            ) from exc
        claims = await load_session_claims(db, session_uuid)
        if claims:
            await touch_session(db, session_uuid)
            return claims

    session_row = await create_attributed_demo_session(db)
    request.state.new_session_id = str(session_row.session_id)
    return {
        "session_id": session_row.session_id,
        "tester_id": session_row.tester_id,
        "attribution": session_row.attribution_mode.value,
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
SessionClaims = Annotated[dict, Depends(resolve_session)]

