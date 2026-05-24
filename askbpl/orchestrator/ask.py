"""End-to-end ask pipeline: retrieve → threshold → generate → verify (TRD-RET-3, TRD-GEN)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional

from dotenv import load_dotenv

from generation.citation_verifier import verify_citations
from generation.generator import generate_answer, load_generation_config
from generation.pii_gate import PII_REJECTION_MESSAGE, rejects_input
from ingestion.policy_metadata import PROJECT_ROOT
from orchestrator.routing import owners_for_policy
from retrieval.retriever import Retriever, infer_policy_type, max_score

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """One citation attached to an answer."""

    vector_id: str
    source_document: str
    section: Optional[str]
    policy_type: str


@dataclass
class AskResponse:
    """Structured orchestrator response."""

    response_type: str
    answer: Optional[str]
    refusal_explanation: Optional[str]
    inferred_policy_type: Optional[str]
    routing_owners: List[str] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)
    best_score: float = 0.0
    retrieved_count: int = 0
    pii_categories: List[str] = field(default_factory=list)


def _load_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT.parent / ".env")


def _retrieval_refusal(inferred: Optional[str], owners: List[str]) -> str:
    area = inferred.replace("_", " ") if inferred else "this topic"
    lines = [
        "I wasn't able to find an answer to that in BPL's policy documents.",
        "",
        f"This question may fall under {area}. For a definitive answer, please contact:",
    ]
    for owner in owners:
        lines.append(f"  • {owner}")
    lines.append("")
    lines.append("If you're unsure who to contact, please check with your supervisor.")
    return "\n".join(lines)


def ask_question(
    question: str,
    *,
    retriever: Retriever | None = None,
    threshold: float | None = None,
) -> AskResponse:
    """Run closed-corpus RAG for one question (TRD-RET-3, TRD-GEN-4)."""
    _load_env()

    blocked, pii_cats = rejects_input(question)
    if blocked:
        return AskResponse(
            response_type="pii_rejection",
            answer=None,
            refusal_explanation=PII_REJECTION_MESSAGE,
            routing_owners=[],
            pii_categories=pii_cats,
        )

    r = retriever or Retriever()
    cutoff = threshold if threshold is not None else r.grounding_threshold

    chunks = r.query(question)
    best = max_score(chunks)
    inferred = infer_policy_type(chunks)
    owners = owners_for_policy(inferred)

    if not chunks or best < cutoff:
        return AskResponse(
            response_type="refusal",
            answer=None,
            refusal_explanation=_retrieval_refusal(inferred, owners),
            inferred_policy_type=inferred,
            routing_owners=owners,
            best_score=best,
            retrieved_count=len(chunks),
        )

    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return AskResponse(
            response_type="refusal",
            answer=None,
            refusal_explanation="Generation is unavailable — ANTHROPIC_API_KEY is not configured.",
            inferred_policy_type=inferred,
            routing_owners=owners,
            best_score=best,
            retrieved_count=len(chunks),
        )

    gen_cfg = load_generation_config()
    gen = generate_answer(
        question=question,
        chunks=chunks,
        routing_owners=owners,
        config=gen_cfg,
    )

    if gen.refuses:
        explanation = gen.answer.strip() or _retrieval_refusal(inferred, owners)
        return AskResponse(
            response_type="refusal",
            answer=None,
            refusal_explanation=explanation,
            inferred_policy_type=inferred,
            routing_owners=owners,
            best_score=best,
            retrieved_count=len(chunks),
        )

    check = verify_citations(
        answer=gen.answer,
        refuses=gen.refuses,
        cited_vector_ids=gen.cited_vector_ids,
        retrieved=chunks,
    )

    if not check.ok:
        return AskResponse(
            response_type="refusal",
            answer=None,
            refusal_explanation="I could not safely verify citations from the retrieved policy excerpts.",
            inferred_policy_type=inferred,
            routing_owners=owners,
            best_score=best,
            retrieved_count=len(chunks),
        )

    chunk_map = {c.vector_id: c for c in chunks}
    citations: List[Citation] = []
    for vid in gen.cited_vector_ids:
        hit = chunk_map.get(vid)
        if not hit:
            continue
        citations.append(
            Citation(
                vector_id=vid,
                source_document=hit.source_document,
                section=hit.section,
                policy_type=hit.policy_type,
            )
        )

    return AskResponse(
        response_type="answer",
        answer=gen.answer,
        refusal_explanation=None,
        inferred_policy_type=inferred,
        routing_owners=owners,
        citations=citations,
        best_score=best,
        retrieved_count=len(chunks),
    )


def format_response(resp: AskResponse) -> str:
    """Human-readable CLI output."""
    lines: List[str] = []
    if resp.response_type == "answer" and resp.answer:
        lines.append(resp.answer)
    elif resp.response_type == "pii_rejection":
        lines.append(resp.refusal_explanation or PII_REJECTION_MESSAGE)
    else:
        lines.append(resp.refusal_explanation or "Unable to answer from policy corpus.")
    if resp.response_type == "answer" and resp.best_score:
        lines.append("")
        lines.append(f"[retrieval: best={resp.best_score:.3f}, chunks={resp.retrieved_count}]")
    elif resp.response_type != "pii_rejection":
        lines.append("")
        lines.append(f"[retrieval: best={resp.best_score:.3f}, chunks={resp.retrieved_count}]")
    return "\n".join(lines)
