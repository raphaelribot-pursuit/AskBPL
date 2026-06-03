"""Pinecone SDK response shape — QueryResponse uses struct matches, not dict .get()."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from ask_bpl_orchestrator.services.retrieval import (
    _pinecone_match_id,
    _pinecone_match_score,
    _pinecone_query_matches,
)


def test_pinecone_query_matches_from_dict_response() -> None:
    cid = str(uuid.uuid4())
    response = {"matches": [{"id": cid, "score": 0.88}]}

    matches = _pinecone_query_matches(response)

    assert len(matches) == 1
    assert _pinecone_match_id(matches[0]) == cid
    assert _pinecone_match_score(matches[0]) == 0.88


def test_pinecone_query_matches_from_sdk_style_response() -> None:
    cid = uuid.uuid4()
    match = SimpleNamespace(id=str(cid), score=0.91)
    response = SimpleNamespace(matches=[match])

    matches = _pinecone_query_matches(response)

    assert len(matches) == 1
    assert _pinecone_match_id(matches[0]) == str(cid)
    assert _pinecone_match_score(matches[0]) == 0.91


def test_pinecone_match_fields_reject_missing_id() -> None:
    match = SimpleNamespace(score=0.5)

    assert _pinecone_match_id(match) is None
    assert _pinecone_match_score(match) == 0.5
