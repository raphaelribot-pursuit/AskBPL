"""End-to-end `/ask` orchestration (TRD flow; ERD persistence)."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.db.models import (
    AttributionMode,
    Chunk,
    Citation,
    Document,
    OwningTeam,
    Question,
    Response,
    ResponseType,
    RoutingDecision,
    Session,
)
from ask_bpl_orchestrator.services import generation, routing_service
from ask_bpl_orchestrator.services.intent_guard import flagged_intents
from ask_bpl_orchestrator.services.pii_gate import rejects_input
from ask_bpl_orchestrator.services.retrieval import VectorRetriever, max_score
from ask_bpl_orchestrator.services.text_hash import question_sha256


async def _persist_routing(db: AsyncSession, response_id: uuid.UUID, teams: List[OwningTeam]) -> None:
    for i, team in enumerate(teams, start=1):
        db.add(RoutingDecision(response_id=response_id, team_id=team.team_id, ordinal=i))


async def _finish_refusal(
    db: AsyncSession,
    *,
    start: float,
    q_row: Question,
    request_id: uuid.UUID,
    rtype: ResponseType,
    refusal_explanation: str,
    inferred_policy: Optional[str],
    teams: List[OwningTeam],
) -> Tuple[Dict[str, Any], int]:
    resp = Response(
        request_id=request_id,
        response_type=rtype,
        answer_text=None,
        refusal_explanation=refusal_explanation,
        inferred_policy_type=inferred_policy,
    )
    db.add(resp)
    await db.flush()
    await _persist_routing(db, resp.response_id, teams)
    q_row.latency_ms = int((time.perf_counter() - start) * 1000)
    await db.commit()
    return _payload(request_id, resp, teams, []), 200


def _payload(
    request_id: uuid.UUID, resp: Response, teams: List[OwningTeam], citations: List[Dict[str, Any]]
) -> Dict[str, Any]:
    return {
        "request_id": str(request_id),
        "type": resp.response_type.value,
        "answer": resp.answer_text,
        "refusal_explanation": resp.refusal_explanation,
        "inferred_policy_type": resp.inferred_policy_type,
        "routing": [
            {"team": t.name, "contact_hint": t.contact_hint, "team_id": str(t.team_id)} for t in teams
        ],
        "citations": citations,
    }


async def _teams(db: AsyncSession, inferred_policy: Optional[str]) -> List[OwningTeam]:
    teams: List[OwningTeam] = []
    if inferred_policy:
        teams.extend(await routing_service.teams_for_policy(db, inferred_policy))
    if teams:
        return teams
    gen = await routing_service.general_supervisor_team(db)
    return [gen] if gen else []


async def handle_ask(
    db: AsyncSession,
    *,
    jwt_session_id: uuid.UUID,
    jwt_attribution: str,
    question_text: str,
) -> Tuple[Dict[str, Any], int]:
    settings = get_settings()
    started = time.perf_counter()
    request_id = uuid.uuid4()

    sess = await db.get(Session, jwt_session_id)
    if not sess:
        return {"error": "SESSION_NOT_FOUND"}, 401
    expires = sess.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        return {"error": "SESSION_EXPIRED"}, 401

    attributed_session = jwt_attribution == AttributionMode.attributed.value
    tester_storage = sess.tester_id if attributed_session else None

    q_hash = question_sha256(question_text)
    blocked, cats = rejects_input(question_text)
    if blocked:
        latency = int((time.perf_counter() - started) * 1000)
        q = Question(
            request_id=request_id,
            session_id=sess.session_id,
            tester_id=tester_storage,
            question_text=None,
            question_hash=q_hash,
            pii_rejected=True,
            latency_ms=latency,
        )
        db.add(q)
        await db.flush()
        db.add(Response(request_id=request_id, response_type=ResponseType.error_pii))
        await db.commit()
        return {"request_id": str(request_id), "type": "error_pii", "pii_categories": cats}, 400

    question_row = Question(
        request_id=request_id,
        session_id=sess.session_id,
        tester_id=tester_storage,
        question_text=question_text if attributed_session else None,
        question_hash=q_hash,
        pii_rejected=False,
    )
    db.add(question_row)
    await db.flush()

    if flagged_intents(question_text):
        teams = await _teams(db, None)
        return await _finish_refusal(
            db,
            start=started,
            q_row=question_row,
            request_id=request_id,
            rtype=ResponseType.refusal_oo_corpus,
            refusal_explanation="This request falls outside closed policy lookup. Speak with your supervisor or:",
            inferred_policy=None,
            teams=teams,
        )

    retriever = VectorRetriever()
    retrieved = await retriever.query(db, question_text, settings.pinecone_top_k)
    best = max_score(retrieved)
    inferred_policy = await routing_service.infer_policy_from_chunks(
        db, [c.policy_type for c in retrieved if c.policy_type]
    )
    route_targets = await _teams(db, inferred_policy)

    if best < settings.grounding_threshold or not retrieved:
        return await _finish_refusal(
            db,
            start=started,
            q_row=question_row,
            request_id=request_id,
            rtype=ResponseType.refusal_oo_corpus,
            refusal_explanation="I couldn't locate relevant policy excerpts.",
            inferred_policy=inferred_policy,
            teams=route_targets,
        )

    if not settings.anthropic_api_key:
        return await _finish_refusal(
            db,
            start=started,
            q_row=question_row,
            request_id=request_id,
            rtype=ResponseType.refusal_oo_corpus,
            refusal_explanation="Generation endpoint is unavailable in this build.",
            inferred_policy=inferred_policy,
            teams=route_targets,
        )

    ans, refusal_flag, cited, _raw = await generation.generate_answer(
        question=question_text,
        chunks=retrieved,
    )
    retrieval_ids = {c.chunk_id for c in retrieved}
    ok = (
        bool(cited)
        and all(i in retrieval_ids for i in cited)
        and not refusal_flag
        and ans.strip() != ""
    )
    if not ok:
        rtype = (
            ResponseType.refusal_citation_invalid if cited else ResponseType.refusal_oo_corpus
        )
        return await _finish_refusal(
            db,
            start=started,
            q_row=question_row,
            request_id=request_id,
            rtype=rtype,
            refusal_explanation="I could not safely verify citations from retrieval.",
            inferred_policy=inferred_policy,
            teams=route_targets,
        )

    ans_row = Response(
        request_id=request_id,
        response_type=ResponseType.answer,
        answer_text=ans,
        refusal_explanation=None,
        inferred_policy_type=inferred_policy,
    )
    db.add(ans_row)
    await db.flush()

    cites: List[Dict[str, Any]] = []
    for ord_i, cid in enumerate(cited, start=1):
        db.add(Citation(response_id=ans_row.response_id, chunk_id=cid, ordinal=ord_i))
        chunk = await db.get(Chunk, cid)
        if not chunk:
            continue
        doc = await db.get(Document, chunk.document_id)
        cites.append(
            {
                "chunk_id": str(cid),
                "document_id": str(chunk.document_id),
                "document_title": doc.title if doc else "",
                "section_heading": chunk.section_heading,
            }
        )

    question_row.latency_ms = int((time.perf_counter() - started) * 1000)
    await db.commit()

    return _payload(request_id, ans_row, [], cites), 200
