"""JWT helpers for tester sessions."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt

from ask_bpl_orchestrator.config import Settings, get_settings


def create_session_token(settings: Settings, claims: Dict[str, Any]) -> str:
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_session_token(settings: Settings, token: str, *, verify_exp: bool = False) -> Dict[str, Any]:
    try:
        options = {"verify_exp": verify_exp}
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options=options,
        )
    except JWTError as e:
        raise ValueError("INVALID_TOKEN") from e


def build_claims(*, session_id: uuid.UUID, tester_id: Optional[uuid.UUID], attribution: str) -> Dict[str, Any]:
    settings = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours)
    now = datetime.now(timezone.utc)
    sub = str(session_id)
    payload: Dict[str, Any] = {
        "sub": sub,
        "attribution": attribution,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    if tester_id:
        payload["tester_id"] = str(tester_id)
    return payload
