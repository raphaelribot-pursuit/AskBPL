"""Request correlation id for logs and support (demo_acceptance § audit replay)."""

from __future__ import annotations

import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

log = logging.getLogger("ask_bpl.http")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get("x-request-id") or request.headers.get("X-Request-ID")
        rid = (incoming or "").strip() or str(uuid.uuid4())
        request.state.request_id = rid

        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        log.info("request_id=%s %s %s", rid, request.method, request.url.path)
        return response
