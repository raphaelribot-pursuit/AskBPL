"""Question / answer orchestration endpoints."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ask_bpl_orchestrator.api.deps import SessionClaims
from ask_bpl_orchestrator.api.response_session import attach_public_session_header
from ask_bpl_orchestrator.api.session_dep import DbSessionDep
from ask_bpl_orchestrator.services import ask_service

router = APIRouter(prefix="/questions", tags=["questions"])


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)


class AskBody(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    conversation_context: Optional[list[ConversationTurn]] = Field(
        default=None,
        max_length=4,
        description=(
            "Optional recent conversation turns for follow-up context. "
            "Last 2 Q&A pairs max. Frontend-managed, not stored."
        ),
    )
    user_role: Optional[str] = Field(
        default=None,
        max_length=64,
        description=(
            "Optional self-selected role lens (general, staff, manager). Not a security boundary (ROLE-4). "
            "Missing or unrecognised values are treated as General (ROLE-11), never an error."
        ),
    )


@router.post("/ask")
async def ask_question(body: AskBody, request: Request, claims: SessionClaims, db: DbSessionDep):
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
        user_role=body.user_role,
    )
    rid = payload.get("request_id")
    headers = {"X-Request-ID": rid} if isinstance(rid, str) else None
    return attach_public_session_header(
        request,
        JSONResponse(content=payload, status_code=status_code, headers=headers or None),
    )
