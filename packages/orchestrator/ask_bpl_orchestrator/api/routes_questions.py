"""Question / answer orchestration endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ask_bpl_orchestrator.api.deps import JwtAuthClaims
from ask_bpl_orchestrator.api.session_dep import DbSessionDep
from ask_bpl_orchestrator.services import ask_service

router = APIRouter(prefix="/questions", tags=["questions"])


class AskBody(BaseModel):
    question: str = Field(..., min_length=3)


@router.post("/ask")
async def ask_question(body: AskBody, claims: JwtAuthClaims, db: DbSessionDep):
    payload, status_code = await ask_service.handle_ask(
        db,
        jwt_session_id=claims["session_id"],
        jwt_attribution=claims["attribution"],
        question_text=body.question.strip(),
    )
    rid = payload.get("request_id")
    headers = {"X-Request-ID": rid} if isinstance(rid, str) else None
    return JSONResponse(content=payload, status_code=status_code, headers=headers or None)
