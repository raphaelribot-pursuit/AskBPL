"""End-to-end `/ask` orchestration (TRD flow; ERD persistence)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

import anthropic

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
from ask_bpl_orchestrator.services.query_rewriter import rewrite_follow_up
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk, VectorRetriever, max_score
from ask_bpl_orchestrator.services.text_hash import question_sha256

logger = logging.getLogger(__name__)

# Placeholder hash so we never store PII-bearing text but satisfy NOT NULL question_hash.
PII_REDACTED_QUESTION_HASH = question_sha256("__pii_gate_redacted_v1__")


def _routing_team_names(teams: List[OwningTeam]) -> Optional[List[str]]:
    if not teams:
        return None
    return [t.name for t in teams]


def _emit_structured_ask_log(entry: Dict[str, Any]) -> None:
    """Single-line JSON log (TRD-LOG-2, TRD-RTG-6)."""
    logger.info(json.dumps(entry, default=str))


def _build_completion_log(
    *,
    request_id: uuid.UUID,
    session_marker: str,
    started: float,
    retrieval_hit: bool,
    chunks_returned: int,
    top_score: Optional[float],
    grounding_passed: bool,
    refusal: bool,
    refusal_reason: Optional[str],
    inferred_policy_type: Optional[str],
    routing_teams: Optional[List[str]],
    citation_verified: bool,
    pii_categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    latency_ms = (time.perf_counter() - started) * 1000
    payload: Dict[str, Any] = {
        "event": "ask_completed",
        "request_id": str(request_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session": session_marker,
        "retrieval_hit": retrieval_hit,
        "chunks_returned": chunks_returned,
        "top_score": top_score,
        "grounding_passed": grounding_passed,
        "refusal": refusal,
        "refusal_reason": refusal_reason,
        "inferred_policy_type": inferred_policy_type,
        "routing_teams": routing_teams,
        "citation_verified": citation_verified,
        "latency_ms": round(latency_ms, 3),
    }
    if pii_categories is not None:
        payload["pii_categories"] = pii_categories
        # TODO: map pii_categories to formal SIEM / OTel fields when pipeline is ready
    return payload


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
    conversation_context: Optional[List[Dict[str, str]]] = None,
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

    session_marker = str(sess.session_id) if attributed_session else "anonymous"

    q_hash = question_sha256(question_text)
    texts_to_scan = [question_text]
    if conversation_context:
        texts_to_scan.extend(turn["content"] for turn in conversation_context)
    combined_text = " ".join(texts_to_scan)
    blocked, cats = rejects_input(combined_text)
    if blocked:
        pii_row = Question(
            request_id=request_id,
            session_id=sess.session_id,
            tester_id=tester_storage,
            question_text=None,
            question_hash=PII_REDACTED_QUESTION_HASH,
            pii_rejected=True,
            pii_categories=cats,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        db.add(pii_row)
        await db.commit()
        _emit_structured_ask_log(
            _build_completion_log(
                request_id=request_id,
                session_marker=session_marker,
                started=started,
                retrieval_hit=False,
                chunks_returned=0,
                top_score=None,
                grounding_passed=False,
                refusal=True,
                refusal_reason="PII_DETECTED",
                inferred_policy_type=None,
                routing_teams=None,
                citation_verified=False,
                pii_categories=list(cats),
            )
        )
        return (
            {
                "type": "error_pii",
                "detail": "PII_DETECTED",
                "pii_categories": cats,
                "message": "Personal information was detected. Rephrase your question without names, contact details, or identifiers.",
            },
            400,
        )

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
        out = await _finish_refusal(
            db,
            start=started,
            q_row=question_row,
            request_id=request_id,
            rtype=ResponseType.refusal_oo_corpus,
            refusal_explanation="This request falls outside closed policy lookup. Speak with your supervisor or:",
            inferred_policy=None,
            teams=teams,
        )
        _emit_structured_ask_log(
            _build_completion_log(
                request_id=request_id,
                session_marker=session_marker,
                started=started,
                retrieval_hit=False,
                chunks_returned=0,
                top_score=None,
                grounding_passed=False,
                refusal=True,
                refusal_reason="NO_GROUNDING",
                inferred_policy_type=None,
                routing_teams=_routing_team_names(teams),
                citation_verified=False,
            )
        )
        return out

    retrieval_query = question_text
    if conversation_context and settings.anthropic_api_key:
        anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        retrieval_query = await rewrite_follow_up(
            question=question_text,
            context=conversation_context,
            client=anthropic_client,
            model=settings.anthropic_model,
        )
        _emit_structured_ask_log(
            {
                "event": "query_rewrite",
                "original": question_text,
                "rewritten": retrieval_query,
                "request_id": str(request_id),
            }
        )

    retriever = VectorRetriever()
    retrieved: List[RetrievedChunk] = await retriever.query(db, retrieval_query, settings.pinecone_top_k)
    best = max_score(retrieved)
    inferred_policy = await routing_service.infer_policy_from_chunks(
        db, [c.policy_type for c in retrieved if c.policy_type]
    )
    route_targets = await _teams(db, inferred_policy)
    team_names_for_log = _routing_team_names(route_targets)

    n_chunks = len(retrieved)
    grounding_passed = bool(retrieved) and best >= settings.grounding_threshold

    if best < settings.grounding_threshold or not retrieved:
        out = await _finish_refusal(
            db,
            start=started,
            q_row=question_row,
            request_id=request_id,
            rtype=ResponseType.refusal_oo_corpus,
            refusal_explanation="I couldn't locate relevant policy excerpts.",
            inferred_policy=inferred_policy,
            teams=route_targets,
        )
        _emit_structured_ask_log(
            _build_completion_log(
                request_id=request_id,
                session_marker=session_marker,
                started=started,
                retrieval_hit=n_chunks > 0,
                chunks_returned=n_chunks,
                top_score=best,
                grounding_passed=grounding_passed,
                refusal=True,
                refusal_reason="NO_GROUNDING",
                inferred_policy_type=inferred_policy,
                routing_teams=team_names_for_log,
                citation_verified=False,
            )
        )
        return out

    if not settings.anthropic_api_key:
        out = await _finish_refusal(
            db,
            start=started,
            q_row=question_row,
            request_id=request_id,
            rtype=ResponseType.refusal_oo_corpus,
            refusal_explanation="Generation endpoint is unavailable in this build.",
            inferred_policy=inferred_policy,
            teams=route_targets,
        )
        _emit_structured_ask_log(
            _build_completion_log(
                request_id=request_id,
                session_marker=session_marker,
                started=started,
                retrieval_hit=True,
                chunks_returned=n_chunks,
                top_score=best,
                grounding_passed=grounding_passed,
                refusal=True,
                refusal_reason="NO_GROUNDING",
                inferred_policy_type=inferred_policy,
                routing_teams=team_names_for_log,
                citation_verified=False,
            )
        )
        return out

    ans, refusal_flag, cited, _raw = await generation.generate_answer(
        question=question_text,
        chunks=retrieved,
        conversation_context=conversation_context,
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
        reason = "CITATION_VERIFICATION_FAILED" if cited else "NO_GROUNDING"
        refusal_expl = "I could not safely verify citations from retrieval."
        out = await _finish_refusal(
            db,
            start=started,
            q_row=question_row,
            request_id=request_id,
            rtype=rtype,
            refusal_explanation=refusal_expl,
            inferred_policy=inferred_policy,
            teams=route_targets,
        )
        _emit_structured_ask_log(
            _build_completion_log(
                request_id=request_id,
                session_marker=session_marker,
                started=started,
                retrieval_hit=True,
                chunks_returned=n_chunks,
                top_score=best,
                grounding_passed=grounding_passed,
                refusal=True,
                refusal_reason=reason,
                inferred_policy_type=inferred_policy,
                routing_teams=team_names_for_log,
                citation_verified=False,
            )
        )
        return out

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

    _emit_structured_ask_log(
        _build_completion_log(
            request_id=request_id,
            session_marker=session_marker,
            started=started,
            retrieval_hit=True,
            chunks_returned=n_chunks,
            top_score=best,
            grounding_passed=grounding_passed,
            refusal=False,
            refusal_reason=None,
            inferred_policy_type=inferred_policy,
            routing_teams=team_names_for_log,
            citation_verified=True,
        )
    )

    return _payload(request_id, ans_row, [], cites), 200
