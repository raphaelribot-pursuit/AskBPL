"""Server-side citation gate (PRD GRD-5, NFR-2, AC-2).

This is the production check used by ``ask_service``. Tests import this function; they
must not carry their own copy (PRD BASE-4).

Scope: this confirms that every cited chunk was actually retrieved for the question and
that the model did not refuse or return an empty answer. It does NOT yet confirm that each
claim is supported by the cited passage; that is GRD-11 / R-13 and is separate work.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Iterable


def verify_citations(
    *,
    cited: Iterable[uuid.UUID] | None,
    retrieval_ids: Collection[uuid.UUID],
    refusal_flag: bool,
    answer: str,
) -> bool:
    cited_list = list(cited or [])
    return (
        bool(cited_list)
        and all(i in retrieval_ids for i in cited_list)
        and not refusal_flag
        and answer.strip() != ""
    )
