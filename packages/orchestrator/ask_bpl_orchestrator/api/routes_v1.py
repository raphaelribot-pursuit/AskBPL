"""Canonical TRD v1 path aliases (``/v1/ask``, ``/v1/feedback``)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ask_bpl_orchestrator.api.deps import JwtAuthClaims
from ask_bpl_orchestrator.api.routes_feedback import FeedbackPayload, submit_feedback
from ask_bpl_orchestrator.api.routes_questions import AskBody
from ask_bpl_orchestrator.api.session_dep import DbSessionDep
from ask_bpl_orchestrator.services import ask_service

router = APIRouter(prefix="/v1", tags=["v1"])


@router.post("/ask")
async def ask_v1(body: AskBody, claims: JwtAuthClaims, db: DbSessionDep):
    context_dicts = (
        [{"role": t.role, "content": t.content.strip()} for t in body.conversation_context]
        if body.conversation_context
        else None
    )
    payload, status_code = await ask_service.handle_ask(
        db,
        jwt_session_id=claims["session_id"],
        jwt_attribution=claims["attribution"],
        question_text=body.question.strip(),
        conversation_context=context_dicts,
    )
    rid = payload.get("request_id")
    headers = {"X-Request-ID": rid} if isinstance(rid, str) else None
    return JSONResponse(content=payload, status_code=status_code, headers=headers or None)


@router.post("/feedback")
async def feedback_v1(claims: JwtAuthClaims, body: FeedbackPayload, db: DbSessionDep):
    return await submit_feedback(claims, body, db)
