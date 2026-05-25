"""Question / answer orchestration endpoints."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ask_bpl_orchestrator.api.deps import JwtAuthClaims
from ask_bpl_orchestrator.api.session_dep import DbSessionDep
from ask_bpl_orchestrator.services import ask_service

router = APIRouter(prefix="/questions", tags=["questions"])


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)


class AskBody(BaseModel):
    question: str = Field(..., min_length=3)
    conversation_context: Optional[list[ConversationTurn]] = Field(
        default=None,
        max_length=4,
        description=(
            "Optional recent conversation turns for follow-up context. "
            "Last 2 Q&A pairs max. Frontend-managed, not stored."
        ),
    )


@router.post("/ask")
async def ask_question(body: AskBody, claims: JwtAuthClaims, db: DbSessionDep):
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
