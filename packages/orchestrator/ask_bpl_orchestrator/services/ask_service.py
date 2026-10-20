"""End-to-end `/ask` orchestration (TRD flow; ERD persistence)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
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
from ask_bpl_orchestrator.services.routing_service import public_contact_hint
from ask_bpl_orchestrator.services.citation_verifier import verify_citations
from ask_bpl_orchestrator.services.crisis_gate import detect_crisis, format_crisis_response
from ask_bpl_orchestrator.services.intent_guard import intent_causes
from ask_bpl_orchestrator.services.pii_gate import rejects_input
from ask_bpl_orchestrator.services.refusal import (
    TECHNICAL_HTTP_STATUS,
    RefusalCause,
    classify_generation_failure,
    classify_retrieval_gate_failure,
    is_technical,
    stage_for,
    user_message,
)
from ask_bpl_orchestrator.services.glossary import acronyms_missing_from, get_glossary
from ask_bpl_orchestrator.services.query_rewriter import rewrite_follow_up
from ask_bpl_orchestrator.services.eligibility import TEST_INDEX_LABEL, is_retrievable, is_test_index_source
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk, VectorRetriever, max_score
from ask_bpl_orchestrator.services.text_hash import question_sha256

logger = logging.getLogger(__name__)

# Placeholder hash so we never store PII-bearing text but satisfy NOT NULL question_hash.
PII_REDACTED_QUESTION_HASH = question_sha256("__pii_gate_redacted_v1__")
# Placeholder hash for crisis-gate interception (same privacy principle).
CRISIS_REDACTED_QUESTION_HASH = question_sha256("__crisis_gate_redacted_v1__")


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
    refusal_stage: Optional[str] = None,
    technical_failure: Optional[str] = None,
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
    # RTG-6: internal only. These never reach the API response or the screen.
    if refusal_stage is not None:
        payload["refusal_stage"] = refusal_stage
    if technical_failure is not None:
        payload["technical_failure"] = technical_failure
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


@dataclass
class _AskContext:
    """What every outcome of one /ask call needs in order to log and persist itself."""

    started: float
    question_row: Question
    request_id: uuid.UUID
    session_marker: str


async def _refuse(
    db: AsyncSession,
    ctx: _AskContext,
    *,
    cause: RefusalCause,
    stage: str,
    inferred_policy: Optional[str],
    teams: List[OwningTeam],
    retrieval_hit: bool,
    n_chunks: int,
    top_score: Optional[float],
    grounding_passed: bool,
    rtype: ResponseType = ResponseType.refusal_oo_corpus,
) -> Tuple[Dict[str, Any], int]:
    """A completed refusal (HTTP 200, RTG-1). The cause is logged; staff see only the plain message."""
    out = await _finish_refusal(
        db,
        start=ctx.started,
        q_row=ctx.question_row,
        request_id=ctx.request_id,
        rtype=rtype,
        refusal_explanation=user_message(cause),
        inferred_policy=inferred_policy,
        teams=teams,
    )
    _emit_structured_ask_log(
        _build_completion_log(
            request_id=ctx.request_id,
            session_marker=ctx.session_marker,
            started=ctx.started,
            retrieval_hit=retrieval_hit,
            chunks_returned=n_chunks,
            top_score=top_score,
            grounding_passed=grounding_passed,
            refusal=True,
            refusal_reason=cause.value,
            inferred_policy_type=inferred_policy,
            routing_teams=_routing_team_names(teams),
            citation_verified=False,
            refusal_stage=stage,
        )
    )
    return out


async def _fail_technical(
    db: AsyncSession,
    ctx: _AskContext,
    *,
    cause: RefusalCause,
    stage: str,
    retrieval_hit: bool,
    n_chunks: int,
    top_score: Optional[float],
    grounding_passed: bool,
) -> Tuple[Dict[str, Any], int]:
    """A system failure, not a policy conclusion: 5xx, never a refusal, so it cannot pass as a safe refusal.

    The staff-facing message says what happened to the request. The cause label stays in the log.
    """
    assert is_technical(cause)
    ctx.question_row.latency_ms = int((time.perf_counter() - ctx.started) * 1000)
    await db.commit()
    _emit_structured_ask_log(
        _build_completion_log(
            request_id=ctx.request_id,
            session_marker=ctx.session_marker,
            started=ctx.started,
            retrieval_hit=retrieval_hit,
            chunks_returned=n_chunks,
            top_score=top_score,
            grounding_passed=grounding_passed,
            refusal=False,
            refusal_reason=None,
            inferred_policy_type=None,
            routing_teams=None,
            citation_verified=False,
            refusal_stage=stage,
            technical_failure=cause.value,
        )
    )
    return (
        {
            "type": "error_unavailable",
            "detail": "service_unavailable",
            "message": user_message(cause),
            "request_id": str(ctx.request_id),
        },
        TECHNICAL_HTTP_STATUS[cause],
    )


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
            {"team": t.name, "contact_hint": public_contact_hint(t.contact_hint), "team_id": str(t.team_id)}
            for t in teams
        ],
        "citations": citations,
    }


async def _cited_documents_answerable(db: AsyncSession, cited: List[uuid.UUID], settings) -> bool:
    for cid in cited:
        chunk = await db.get(Chunk, cid)
        doc = await db.get(Document, chunk.document_id) if chunk else None
        if not is_retrievable(doc, settings):
            return False
    return True


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

    # PII gate: scan ONLY the current question, not conversation history.
    # Prior messages were already vetted when they arrived. Re-scanning them
    # causes false positives if a prior PII-blocked message leaked into context.
    blocked, cats = rejects_input(question_text)
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

    # Crisis gate — parallel to PII gate, runs BEFORE retrieval.
    # On match: bypass RAG pipeline entirely, return crisis resource response.
    # NEVER log message content (same privacy principle as PII gate).
    # Same principle: only scan current question, not conversation history.
    if detect_crisis(question_text):
        crisis_row = Question(
            request_id=request_id,
            session_id=sess.session_id,
            tester_id=tester_storage,
            question_text=None,  # NEVER store potentially sensitive content
            question_hash=CRISIS_REDACTED_QUESTION_HASH,
            pii_rejected=False,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        db.add(crisis_row)
        await db.commit()
        _emit_structured_ask_log(
            {
                "event": "ask_completed",
                "request_id": str(request_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "session": session_marker,
                "crisis_resource_served": True,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        )
        crisis_payload = format_crisis_response()
        crisis_payload["request_id"] = str(request_id)
        return crisis_payload, 200

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

    ctx = _AskContext(
        started=started, question_row=question_row, request_id=request_id, session_marker=session_marker
    )

    guard_causes = intent_causes(question_text)
    if guard_causes:
        return await _refuse(
            db,
            ctx,
            cause=guard_causes[0],
            stage="intent_guard",
            inferred_policy=None,
            teams=await _teams(db, None),
            retrieval_hit=False,
            n_chunks=0,
            top_score=None,
            grounding_passed=False,
        )

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
                # Log lengths only. Question text must not reach logs (SAF-5, NFR-4, AC-15).
                "original_chars": len(question_text),
                "rewritten_chars": len(retrieval_query),
                "rewritten_changed": retrieval_query != question_text,
                "request_id": str(request_id),
            }
        )

    # Approved glossary terms add their expansion to the SEARCH query only (patch 0016, GLO-6). The model below still
    # receives question_text as the staff member wrote it, and nothing here can become evidence or a citation.
    glossary = get_glossary()
    expanded = glossary.expand_query(retrieval_query)
    retrieval_query = expanded.text

    retriever = VectorRetriever()
    retrieved: List[RetrievedChunk] = await retriever.query(db, retrieval_query, settings.pinecone_top_k)
    if retriever.search_failed:
        # The search itself broke. That is not the same as "no policy covers this".
        return await _fail_technical(
            db,
            ctx,
            cause=RefusalCause.retrieval_unavailable,
            stage="retrieval",
            retrieval_hit=False,
            n_chunks=0,
            top_score=None,
            grounding_passed=False,
        )
    unlisted = glossary.unlisted_acronyms(question_text)
    if expanded.matches or unlisted:
        # Counts only: question text and the acronyms themselves must not reach logs (SAF-5, NFR-4, AC-15).
        _emit_structured_ask_log(
            {
                "event": "glossary",
                "matched_terms": len(expanded.matches),
                "unlisted_acronyms": len(unlisted),
                "unlisted_not_in_evidence": len(acronyms_missing_from(unlisted, [c.text for c in retrieved])),
                "request_id": str(request_id),
            }
        )
    best = max_score(retrieved)
    inferred_policy = await routing_service.infer_policy_from_chunks(
        db, [c.policy_type for c in retrieved if c.policy_type]
    )
    route_targets = await _teams(db, inferred_policy)

    n_chunks = len(retrieved)
    # Margin rule: >=2 chunks above floor OR one chunk above strong threshold
    floor = settings.grounding_threshold
    strong = settings.grounding_strong_threshold
    n_above_floor = sum(1 for c in retrieved if c.score >= floor)
    grounding_passed = bool(retrieved) and (n_above_floor >= 2 or best >= strong)

    if not grounding_passed:
        return await _refuse(
            db,
            ctx,
            cause=classify_retrieval_gate_failure(
                best_score=best, floor=floor, excluded_best_score=retriever.excluded_best_score
            ),
            stage="retrieval_gate",
            inferred_policy=inferred_policy,
            teams=route_targets,
            retrieval_hit=n_chunks > 0,
            n_chunks=n_chunks,
            top_score=best,
            grounding_passed=grounding_passed,
        )

    if not settings.anthropic_api_key:
        return await _fail_technical(
            db,
            ctx,
            cause=RefusalCause.generation_unavailable,
            stage="generation",
            retrieval_hit=True,
            n_chunks=n_chunks,
            top_score=best,
            grounding_passed=grounding_passed,
        )

    # Owning teams the model may name: approved routing rules for the policy areas actually retrieved.
    routing = await routing_service.routing_choices(db, [c.policy_type for c in retrieved])
    ans, refusal_flag, cited, raw_output = await generation.generate_answer(
        question=question_text,
        chunks=retrieved,
        conversation_context=conversation_context,
        routing=routing,
    )
    retrieval_ids = {c.chunk_id for c in retrieved}
    ok = verify_citations(
        cited=cited,
        retrieval_ids=retrieval_ids,
        refusal_flag=refusal_flag,
        answer=ans,
    )
    if ok and not await _cited_documents_answerable(db, cited, settings):
        # Defence in depth (GATE-03): retrieval already filters on eligibility, but a
        # citation to a non-answerable document must never be emitted.
        logger.error("citation_rejected_ineligible_document request=%s", request_id)
        ok = False
    if not ok:
        cause = classify_generation_failure(
            output_usable=generation.model_output_usable(raw_output),
            refuse_flag=refusal_flag,
            answer=ans,
        )
        if is_technical(cause):
            return await _fail_technical(
                db,
                ctx,
                cause=cause,
                stage="generation",
                retrieval_hit=True,
                n_chunks=n_chunks,
                top_score=best,
                grounding_passed=grounding_passed,
            )
        # Only a real citation failure uses the citation-invalid response type.
        rtype = (
            ResponseType.refusal_citation_invalid
            if cause == RefusalCause.citation_unverified and cited
            else ResponseType.refusal_oo_corpus
        )
        return await _refuse(
            db,
            ctx,
            cause=cause,
            stage=stage_for(cause) or "generation",
            inferred_policy=inferred_policy,
            teams=route_targets,
            retrieval_hit=True,
            n_chunks=n_chunks,
            top_score=best,
            grounding_passed=grounding_passed,
            rtype=rtype,
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
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "test_index": is_test_index_source(doc),
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
            routing_teams=_routing_team_names(route_targets),
            citation_verified=True,
        )
    )

    payload = _payload(request_id, ans_row, [], cites)
    if any(c.get("test_index") for c in cites):
        payload["index_label"] = TEST_INDEX_LABEL
    return payload, 200
