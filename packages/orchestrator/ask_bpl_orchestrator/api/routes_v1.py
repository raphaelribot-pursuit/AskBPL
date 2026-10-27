"""Canonical TRD v1 path aliases (``/v1/ask``, ``/v1/feedback``)."""

from __future__ import annotations

import asyncio
import logging

import anthropic
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ask_bpl_orchestrator.api.deps import SessionClaims
from ask_bpl_orchestrator.api.response_session import attach_public_session_header
from ask_bpl_orchestrator.api.routes_feedback import FeedbackPayload, submit_feedback
from ask_bpl_orchestrator.api.routes_questions import AskBody
from ask_bpl_orchestrator.api.session_dep import DbSessionDep
from ask_bpl_orchestrator.services import ask_service

router = APIRouter(prefix="/v1", tags=["v1"])
logger = logging.getLogger(__name__)

ASK_PIPELINE_TIMEOUT_SECONDS = 120.0


@router.post("/ask")
async def ask_v1(body: AskBody, request: Request, claims: SessionClaims, db: DbSessionDep):
    context_dicts = (
        [{"role": t.role, "content": t.content.strip()} for t in body.conversation_context]
        if body.conversation_context
        else None
    )
    try:
        payload, status_code = await asyncio.wait_for(
            ask_service.handle_ask(
                db,
                jwt_session_id=claims["session_id"],
                jwt_attribution=claims["attribution"],
                question_text=body.question.strip(),
                conversation_context=context_dicts,
                user_role=body.user_role,
            ),
            timeout=ASK_PIPELINE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error("ask_pipeline_timeout session=%s", claims.get("session_id"))
        return JSONResponse(
            status_code=504,
            content={
                "type": "error_timeout",
                "detail": "pipeline_timeout",
                "message": "Upstream API timeout. Please retry.",
            },
        )
    except anthropic.APIError as exc:
        logger.error("anthropic_api_error: %s", exc)
        return JSONResponse(
            status_code=502,
            content={
                "type": "error_upstream",
                "detail": "generation_service_error",
                "message": "AI generation service error. Please retry.",
            },
        )
    except Exception as exc:
        logger.exception("ask_pipeline_error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "type": "error_internal",
                "detail": "ask_pipeline_error",
                "message": "Something went wrong processing your question.",
            },
        )

    rid = payload.get("request_id")
    headers = {"X-Request-ID": rid} if isinstance(rid, str) else None
    return attach_public_session_header(
        request,
        JSONResponse(content=payload, status_code=status_code, headers=headers or None),
    )


@router.post("/feedback")
async def feedback_v1(request: Request, claims: SessionClaims, body: FeedbackPayload, db: DbSessionDep):
    result = await submit_feedback(claims, body, db)
    return attach_public_session_header(request, JSONResponse(content=result))
