"""Ask BPL FastAPI application entry."""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ask_bpl_orchestrator.api.routes_admin import router as admin_router
from ask_bpl_orchestrator.api.routes_auth import router as auth_router
from ask_bpl_orchestrator.api.routes_documents import router as documents_router
from ask_bpl_orchestrator.api.routes_feedback import router as feedback_router
from ask_bpl_orchestrator.api.routes_internal import router as internal_router
from ask_bpl_orchestrator.api.routes_questions import router as question_router
from ask_bpl_orchestrator.api.routes_v1 import router as v1_router
from ask_bpl_orchestrator.api.session_dep import DbSessionDep
from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.middleware.request_id import RequestIdMiddleware

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    settings.require_secrets()

    application = FastAPI(title="Ask BPL Orchestrator", version="0.1.0")

    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @application.exception_handler(Exception)
    async def unhandled_exception(_request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, HTTPException):
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )
        # Plain-text 500s omit CORS headers; browsers surface that as "Network error".
        logger.exception("unhandled_exception: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "type": "error_internal",
                "detail": "internal_error",
                "message": "The server hit an unexpected error. Try again in a moment.",
            },
        )

    application.include_router(auth_router)
    application.include_router(question_router)
    application.include_router(documents_router)
    application.include_router(feedback_router)
    application.include_router(admin_router)
    application.include_router(internal_router)

    # TRD v1 path aliases (canonical contract)
    application.include_router(v1_router)
    application.include_router(auth_router, prefix="/v1")
    application.include_router(question_router, prefix="/v1")
    application.include_router(documents_router, prefix="/v1")
    application.include_router(feedback_router, prefix="/v1")
    application.include_router(internal_router, prefix="/v1")
    application.include_router(admin_router, prefix="/v1")

    @application.get("/healthz")
    async def health():  # noqa: WPS430 nested function intentional
        return {"status": "ok"}

    @application.get("/readyz")
    async def readyz(db: DbSessionDep):
        """Liveness remains `/healthz`; this probes the database."""
        try:
            await db.execute(text("SELECT 1"))
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="database_unavailable",
            ) from exc
        return {"status": "ok", "database": True}

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("ask_bpl_orchestrator.main:app", host=settings.host, port=settings.port, reload=False)
