"""Attach public demo session headers to JSON responses."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


def attach_public_session_header(request: Request, response: JSONResponse) -> JSONResponse:
    new_session_id = getattr(request.state, "new_session_id", None)
    if isinstance(new_session_id, str) and new_session_id:
        response.headers["X-Session-ID"] = new_session_id
    return response
