"""Ask BPL FastAPI application entry."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ask_bpl_orchestrator.api.routes_admin import router as admin_router
from ask_bpl_orchestrator.api.routes_auth import router as auth_router
from ask_bpl_orchestrator.api.routes_feedback import router as feedback_router
from ask_bpl_orchestrator.api.routes_questions import router as question_router
from ask_bpl_orchestrator.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(title="Ask BPL Orchestrator", version="0.1.0")

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(auth_router)
    application.include_router(question_router)
    application.include_router(feedback_router)
    application.include_router(admin_router)

    @application.get("/healthz")
    async def health():  # noqa: WPS430 nested function intentional
        return {"status": "ok"}

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("ask_bpl_orchestrator.main:app", host=settings.host, port=settings.port, reload=False)
