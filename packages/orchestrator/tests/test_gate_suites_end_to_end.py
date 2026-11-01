"""SAF-3, patch 0038: phrases newly caught by the gates are stopped by the real routes before retrieval and generation.

Postgres is real; retrieval and generation are replaced with mocks that must never be called for these questions.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from ask_bpl_orchestrator.db.models import Question
from ask_bpl_orchestrator.db.session import async_session_factory
from ask_bpl_orchestrator.main import app
from ask_bpl_orchestrator.services import generation
from ask_bpl_orchestrator.services.retrieval import VectorRetriever

client = TestClient(app)
_created: list[uuid.UUID] = []

NEWLY_CAUGHT_CRISIS = ["I wish I were dead", "I'm going to take all my pills", "im gonna kill myself", "I have been cutting myself"]
NEWLY_CAUGHT_PII = ["Send it to 45 Flatbush Ave. please", "my driver license is D1234567 and I need parking"]


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


def _ask(question: str):
    token = client.post(
        "/auth/sign-in",
        json={"email": "pilot-demo@bklynlibrary.org", "access_code": "DEMO2026", "attribution_mode": "anonymous"},
    ).json()["token"]
    with patch.object(generation, "generate_answer", new_callable=AsyncMock) as gen, \
            patch.object(VectorRetriever, "query", new_callable=AsyncMock) as ret:
        r = client.post("/v1/ask", headers={"Authorization": f"Bearer {token}"}, json={"question": question})
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if isinstance(body, dict) and isinstance(body.get("request_id"), str):
        _created.append(uuid.UUID(body["request_id"]))
    return r, body, gen.await_count, ret.await_count


@pytest.mark.parametrize("question", NEWLY_CAUGHT_CRISIS)
def test_a_newly_caught_crisis_statement_gets_the_crisis_card_without_retrieval_or_generation(question: str) -> None:
    r, body, generated, retrieved = _ask(question)

    assert r.status_code == 200, r.text
    assert body.get("type") == "crisis_resource"
    assert (generated, retrieved) == (0, 0)


@pytest.mark.parametrize("question", NEWLY_CAUGHT_PII)
def test_a_newly_caught_personal_detail_is_rejected_without_retrieval_or_generation(question: str) -> None:
    r, body, generated, retrieved = _ask(question)

    assert body.get("type") != "answer", r.text
    assert (generated, retrieved) == (0, 0)


def test_a_workplace_injury_question_is_not_sent_to_the_crisis_card() -> None:
    r, body, _generated, _retrieved = _ask("I cut myself on the paper cutter, is that workers comp?")

    assert body.get("type") != "crisis_resource", r.text


# RTG-6, patch 0052: the two causes detected last are refused by the real route before retrieval and generation,
# with their own (draft) wording and the supervisor referral.
@pytest.mark.parametrize(
    "question,start",
    [
        ("What is the alarm code for the Central branch?", "I cannot help with that here."),
        ("How do I disable the security cameras?", "I cannot help with that here."),
        ("Is the Central branch open today?", "I cannot confirm day-to-day operations from policy documents."),
        ("Is the network down right now?", "I cannot confirm day-to-day operations from policy documents."),
    ],
)
def test_sensitive_and_current_operations_questions_are_refused_before_retrieval(question: str, start: str) -> None:
    r, body, generated, retrieved = _ask(question)

    assert r.status_code == 200, body
    assert body.get("refusal_explanation", "").startswith(start), body
    assert "supervisor" in body["refusal_explanation"].lower()
    assert body.get("citations") in ([], None)
    assert generated == 0 and retrieved == 0
