"""Patch 0064 end to end: a typed name never reaches the search, the answer step or the stored question.

Real routes and Postgres; the retriever and the answer step are stand-ins that record what they were given.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from ask_bpl_orchestrator.db.models import Question
from ask_bpl_orchestrator.db.session import async_session_factory
from ask_bpl_orchestrator.main import app
from ask_bpl_orchestrator.services import generation
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk, VectorRetriever

client = TestClient(app)
_created: list[uuid.UUID] = []

CHUNK = RetrievedChunk(chunk_id=uuid.uuid4(), score=0.95, document_id=uuid.uuid4(), title="Annual Leave Policy",
                       policy_type="annual_leave", version="v", section_heading=None, text="Supervisors approve annual leave.")


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


def _token(mode: str) -> str:
    r = client.post("/auth/sign-in", json={"email": "pilot-demo@bklynlibrary.org", "access_code": "DEMO2026", "attribution_mode": mode})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _ask(question: str, mode: str = "anonymous", context=None):
    body = {"question": question}
    if context:
        body["conversation_context"] = context
    with patch.object(VectorRetriever, "query", new_callable=AsyncMock, return_value=[CHUNK]) as ret, \
            patch.object(generation, "generate_answer", new_callable=AsyncMock,
                         return_value=("", True, [], '{"answer": "", "refuse": true, "cited_chunk_ids": []}')) as gen:
        r = client.post("/v1/ask", headers={"Authorization": f"Bearer {_token(mode)}"}, json=body)
    payload = r.json()
    if isinstance(payload.get("request_id"), str):
        _created.append(uuid.UUID(payload["request_id"]))
    return r, payload, ret, gen


def test_the_name_never_reaches_the_search_or_the_answer_step() -> None:
    r, payload, ret, gen = _ask("Can Maria approve my annual leave?")

    assert r.status_code == 200
    searched = ret.await_args.args[1]
    asked = gen.await_args.kwargs["question"]
    assert "Maria" not in searched and "Maria" not in asked
    assert "a colleague approve my annual leave" in asked
    assert payload["names_removed"] == 1


def test_a_question_without_a_name_is_sent_exactly_as_typed() -> None:
    r, payload, ret, gen = _ask("Who approves annual leave?")
    assert gen.await_args.kwargs["question"] == "Who approves annual leave?"
    assert payload["names_removed"] == 0


def test_an_attributed_question_is_stored_without_the_name() -> None:
    r, payload, _, _ = _ask("Can my coworker Tasha approve my annual leave?", mode="attributed")

    async def stored() -> str | None:
        async with async_session_factory() as s:
            q = (await s.execute(select(Question).where(Question.request_id == uuid.UUID(payload["request_id"])))).scalar_one()
            return q.question_text

    text = asyncio.run(stored())
    assert text == "Can my coworker approve my annual leave?"


def test_earlier_turns_sent_with_a_follow_up_lose_their_names_too() -> None:
    context = [{"role": "user", "content": "Can Priya approve leave?"}, {"role": "assistant", "content": "Supervisors approve leave."}]
    with patch("ask_bpl_orchestrator.services.ask_service.rewrite_follow_up", new_callable=AsyncMock, return_value="Who approves leave?") as rw:
        r, payload, ret, gen = _ask("And what about her?", context=context)
    sent = gen.await_args.kwargs["conversation_context"]
    assert all("Priya" not in t["content"] for t in sent)
    if rw.await_count:
        assert all("Priya" not in t["content"] for t in rw.await_args.kwargs["context"])


def test_the_guard_still_sees_the_question_as_typed() -> None:
    r, payload, ret, gen = _ask("Was Maria fired for that?")
    assert gen.await_count == 0 and ret.await_count == 0  # refused before retrieval, as before
    assert payload["type"].startswith("refusal")
