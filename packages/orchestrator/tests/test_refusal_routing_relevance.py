"""Patch 0068 (found in Max's live run-through, 2026-11-02): an unrelated question must not be referred to a specific
policy's team. "What is the best pizza in Brooklyn?" was refused correctly but routed to the Materials Review Committee,
because the referral came from the nearest passage however weak. Real routes and Postgres; retrieval is a stand-in."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.db.models import Question
from ask_bpl_orchestrator.db.session import async_session_factory
from ask_bpl_orchestrator.main import app
from ask_bpl_orchestrator.services import generation, routing_service
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk, VectorRetriever

client = TestClient(app)
_created: list[uuid.UUID] = []


@pytest.fixture(autouse=True)
def _cleanup():
    yield

    async def clean() -> None:
        if _created:
            async with async_session_factory() as s:
                await s.execute(delete(Question).where(Question.request_id.in_(list(_created))))
                await s.commit()

    asyncio.run(clean())
    _created.clear()


def _chunk(score: float) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=uuid.uuid4(), score=score, document_id=uuid.uuid4(), title="Materials Selection Policy",
                          policy_type="materials_selection", version="v", section_heading=None, text="Selection criteria.")


def _ask(chunks: list[RetrievedChunk]):
    token = client.post("/auth/sign-in", json={"email": "pilot-demo@bklynlibrary.org", "access_code": "DEMO2026",
                                               "attribution_mode": "anonymous"}).json()["token"]
    with patch.object(VectorRetriever, "query", new_callable=AsyncMock, return_value=chunks), \
            patch.object(generation, "generate_answer", new_callable=AsyncMock,
                         return_value=("", True, [], '{"answer": "", "refuse": true, "cited_chunk_ids": []}')), \
            patch.object(routing_service, "teams_for_policy", wraps=routing_service.teams_for_policy) as teams_for:
        body = client.post("/v1/ask", headers={"Authorization": f"Bearer {token}"}, json={"question": "What is the best pizza in Brooklyn?"}).json()
    _created.append(uuid.UUID(body["request_id"]))
    return body, teams_for


def test_a_question_matching_nothing_relevant_gets_the_general_referral_not_a_policy_team() -> None:
    floor = get_settings().grounding_threshold
    body, teams_for = _ask([_chunk(floor - 0.02), _chunk(floor - 0.05)])  # the pizza case: nearest passages below the floor

    assert body["type"].startswith("refusal")
    assert body.get("inferred_policy_type") is None
    teams_for.assert_not_called()
    assert "Materials Review Committee" not in [r["team"] for r in body["routing"]]


def test_a_relevant_but_insufficient_match_still_routes_to_that_policys_team() -> None:
    floor = get_settings().grounding_threshold
    body, teams_for = _ask([_chunk(floor + 0.01)])  # one passage at the floor, below strong: refused, but on topic

    assert body["type"].startswith("refusal")
    assert body.get("inferred_policy_type") == "materials_selection"
    teams_for.assert_called()
