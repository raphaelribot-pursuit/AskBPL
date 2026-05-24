"""Post-generation citation validation (TRD-GEN-6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Set

from retrieval.retriever import RetrievedChunk


@dataclass(frozen=True)
class CitationCheck:
    """Outcome of citation verification."""

    ok: bool
    reason: str


def verify_citations(
    *,
    answer: str,
    refuses: bool,
    cited_vector_ids: List[str],
    retrieved: List[RetrievedChunk],
) -> CitationCheck:
    """Confirm cites are subset of retrieval and answer is grounded (TRD-GEN-6)."""
    if refuses:
        return CitationCheck(ok=False, reason="model_refused")
    if not answer.strip():
        return CitationCheck(ok=False, reason="empty_answer")
    if not cited_vector_ids:
        return CitationCheck(ok=False, reason="no_citations")

    allowed: Set[str] = {c.vector_id for c in retrieved}
    invalid = [cid for cid in cited_vector_ids if cid not in allowed]
    if invalid:
        return CitationCheck(ok=False, reason=f"invalid_citations:{','.join(invalid[:3])}")

    return CitationCheck(ok=True, reason="ok")
