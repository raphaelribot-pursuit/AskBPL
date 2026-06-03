"""Pinecone SDK response shape — QueryResponse uses struct matches, not dict .get()."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pinecone.errors.exceptions import ApiError

from ask_bpl_orchestrator.services.retrieval import (
    VectorRetriever,
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


@pytest.mark.asyncio
async def test_pinecone_scores_returns_empty_when_pinecone_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = MagicMock()
    settings.pinecone_api_key = "test-key"
    monkeypatch.setattr(
        "ask_bpl_orchestrator.services.retrieval.get_settings",
        lambda: settings,
    )

    async def fake_embed(self, _question: str) -> list[float]:
        return [0.0] * 8

    idx = MagicMock()
    idx.query.side_effect = ApiError("read unit limit", status_code=429)

    monkeypatch.setattr(VectorRetriever, "embed_question", fake_embed)
    monkeypatch.setattr(
        "ask_bpl_orchestrator.services.retrieval.get_pinecone_index",
        lambda: idx,
    )

    async def run_sync(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", run_sync)

    retriever = VectorRetriever()
    scores = await retriever._pinecone_scores("gift acceptance?", 5)

    assert scores == {}
