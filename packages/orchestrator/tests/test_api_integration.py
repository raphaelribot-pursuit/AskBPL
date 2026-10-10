"""HTTP integration tests — require Postgres, migrations, and `askbpl-seed` (matches CI)."""

from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from ask_bpl_orchestrator.db.models import Chunk, Document, IngestStatus, Question, SourceFormat
from ask_bpl_orchestrator.db.session import async_session_factory
from ask_bpl_orchestrator.main import app
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk, VectorRetriever

client = TestClient(app)


@pytest.fixture(autouse=True)
def _no_live_vector_lookup():
    """Keep these tests hermetic: no OpenAI embedding call and no Pinecone query.

    conftest.py sets placeholder API keys, so without this stub the app would try a
    real embedding request (and fail offline or with the placeholder key). An empty
    score map means "no vectors", which is the "no corpus" case the tests describe.
    Tests that need retrieved chunks patch ``VectorRetriever.query`` themselves, which
    takes precedence over this stub.
    """
    with patch.object(VectorRetriever, "_pinecone_scores", new_callable=AsyncMock, return_value={}):
        yield

_SIGN_IN_JSON = {
    "email": "pilot-demo@bklynlibrary.org",
    "access_code": "DEMO2026",
    "attribution_mode": "anonymous",
}


def _pilot_token() -> str:
    r = client.post("/auth/sign-in", json=_SIGN_IN_JSON)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_sign_in_success() -> None:
    r = client.post("/auth/sign-in", json=_SIGN_IN_JSON)
    assert r.status_code == 200
    body = r.json()
    assert body.get("token")
    assert body.get("session_id")
    assert r.headers.get("X-Session-ID")


def test_sign_in_invalid_credentials_401() -> None:
    r = client.post(
        "/auth/sign-in",
        json={
            "email": "pilot-demo@bklynlibrary.org",
            "access_code": "wrong-password",
            "attribution_mode": "anonymous",
        },
    )
    assert r.status_code == 401


def test_readyz_database_ok() -> None:
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json().get("database") is True


def test_admin_summary_requires_auth() -> None:
    r = client.get("/admin/summary")
    assert r.status_code == 401


def test_admin_summary_basic_auth_ok() -> None:
    user = os.environ.get("ADMIN_BASIC_USER", "vizion_build")
    password = os.environ["ADMIN_BASIC_PASSWORD"]
    r = client.get("/admin/summary", auth=(user, password))
    assert r.status_code == 200, r.text
    data = r.json()
    assert "questions_total" in data


def test_v1_ask_without_auth_creates_session_header() -> None:
    r = client.post(
        "/v1/ask",
        json={"question": "What is the data retention policy?"},
    )
    assert r.status_code == 200, r.text
    assert r.headers.get("X-Session-ID")


def test_v1_ask_reuses_x_session_id() -> None:
    first = client.post(
        "/v1/ask",
        json={"question": "What is the data retention policy?"},
    )
    assert first.status_code == 200, first.text
    session_id = first.headers.get("X-Session-ID")
    assert session_id

    second = client.post(
        "/v1/ask",
        headers={"X-Session-ID": session_id},
        json={"question": "What is the gift acceptance policy timeline?"},
    )
    assert second.status_code == 200, second.text


def test_feedback_without_auth_returns_not_found_for_unknown_request() -> None:
    response = client.post(
        "/feedback/",
        json={"request_id": str(uuid.uuid4()), "rating": "helpful"},
    )
    assert response.status_code == 404


def test_ask_pii_returns_400() -> None:
    token = _pilot_token()
    r = client.post(
        "/questions/ask",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "email me copies at ops@example.com about this policy"},
    )
    assert r.status_code == 400
    body = r.json()
    assert body.get("type") == "error_pii"
    assert body.get("pii_categories")
    assert "request_id" not in body


def test_ask_pii_in_conversation_context_is_not_rescanned() -> None:
    """The PII gate scans ONLY the current question (commit e525f1c). Whether earlier turns
    must also be scanned is open decision OD-12 (PRD SAF-10); revisit this test when it closes.

    History is not re-scanned, otherwise one blocked message that leaked into the
    context would reject every later turn. PII typed in the current question is
    still rejected: see test_ask_pii_returns_400.
    """
    token = _pilot_token()
    r = client.post(
        "/questions/ask",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "question": "Is that person eligible for leave?",
            "conversation_context": [
                {
                    "role": "user",
                    "content": "Can john.smith@bklynlibrary.org take time off?",
                },
                {"role": "assistant", "content": "Some prior answer..."},
            ],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json().get("type") != "error_pii"


def test_ask_conversation_context_max_four_turns() -> None:
    token = _pilot_token()
    r = client.post(
        "/questions/ask",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "question": "What about the next topic?",
            "conversation_context": [
                {"role": "user", "content": "Question one?"},
                {"role": "assistant", "content": "Answer one."},
                {"role": "user", "content": "Question two?"},
                {"role": "assistant", "content": "Answer two."},
                {"role": "user", "content": "Question three?"},
            ],
        },
    )
    assert r.status_code == 422


def test_v1_ask_alias_matches_questions_ask() -> None:
    token = _pilot_token()
    legacy = client.post(
        "/questions/ask",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What is the data retention policy?"},
    )
    v1 = client.post(
        "/v1/ask",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What is the data retention policy?"},
    )
    assert legacy.status_code == v1.status_code
    assert legacy.json().get("type") == v1.json().get("type")


def test_internal_corpus_requires_admin() -> None:
    r = client.get("/v1/internal/corpus")
    assert r.status_code == 401


def test_internal_corpus_ok() -> None:
    user = os.environ.get("ADMIN_BASIC_USER", "vizion_build")
    password = os.environ["ADMIN_BASIC_PASSWORD"]
    r = client.get("/v1/internal/corpus", auth=(user, password))
    assert r.status_code == 200, r.text
    data = r.json()
    assert "doc_count" in data
    assert "documents" in data


def test_ask_without_corpus_refusal_200() -> None:
    """No Pinecone vectors in CI — expect grounded refusal, not 5xx."""
    token = _pilot_token()
    r = client.post(
        "/questions/ask",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What is the gift acceptance policy timeline?"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("type") == "refusal_oo_corpus"


def test_feedback_wrong_session_forbidden() -> None:
    token_a = _pilot_token()
    ask = client.post(
        "/questions/ask",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"question": "What is the data retention policy?"},
    )
    assert ask.status_code == 200, ask.text
    request_id = ask.json()["request_id"]

    token_b = _pilot_token()
    fb = client.post(
        "/feedback/",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"request_id": request_id, "rating": "helpful"},
    )
    assert fb.status_code == 403


def test_ask_answer_with_retrieval_and_generation_mocked() -> None:
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()

    async def _seed() -> None:
        async with async_session_factory() as session:
            session.add(
                Document(
                    document_id=doc_id,
                    title="Integration Doc",
                    version="ci-1",
                    policy_type="generic_policy",
                    source_format=SourceFormat.md,
                    ingest_status=IngestStatus.indexed,
                )
            )
            session.add(
                Chunk(
                    chunk_id=chunk_id,
                    document_id=doc_id,
                    ordinal=0,
                    text="Donors must disclose gifts over $500.",
                    token_count=12,
                )
            )
            await session.commit()

    asyncio.run(_seed())

    fake = RetrievedChunk(
        chunk_id=chunk_id,
        score=0.95,
        document_id=doc_id,
        title="Integration Doc",
        policy_type="generic_policy",
        version="ci-1",
        section_heading="Gifts",
        text="Donors must disclose gifts over $500.",
    )

    token = _pilot_token()
    with (
        patch.object(VectorRetriever, "query", new_callable=AsyncMock, return_value=[fake]),
        patch(
            "ask_bpl_orchestrator.services.ask_service.generation.generate_answer",
            new_callable=AsyncMock,
            return_value=(
                "Per policy, disclose gifts over $500.",
                False,
                [chunk_id],
                "{}",
            ),
        ),
    ):
        r = client.post(
            "/questions/ask",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "What must donors disclose?"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "answer"
    assert "disclose" in (body.get("answer") or "")

    req = uuid.UUID(body["request_id"])
    asyncio.run(_cleanup_mocked_ask(req, chunk_id, doc_id))


async def _cleanup_mocked_ask(request_id: uuid.UUID, chunk_id: uuid.UUID, doc_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        await session.execute(delete(Question).where(Question.request_id == request_id))
        await session.execute(delete(Chunk).where(Chunk.chunk_id == chunk_id))
        await session.execute(delete(Document).where(Document.document_id == doc_id))
        await session.commit()


@pytest.mark.asyncio
async def test_hydrate_ordered_skips_chunks_on_superseded_documents() -> None:
    doc_new = uuid.uuid4()
    doc_old = uuid.uuid4()
    chunk_id = uuid.uuid4()

    async with async_session_factory() as session:
        session.add_all(
            [
                Document(
                    document_id=doc_new,
                    title="New",
                    version="2",
                    policy_type="generic_policy",
                    source_format=SourceFormat.md,
                    ingest_status=IngestStatus.indexed,
                ),
                Document(
                    document_id=doc_old,
                    title="Old",
                    version="1",
                    policy_type="generic_policy",
                    source_format=SourceFormat.md,
                    ingest_status=IngestStatus.indexed,
                    superseded_by_document_id=doc_new,
                ),
                Chunk(
                    chunk_id=chunk_id,
                    document_id=doc_old,
                    ordinal=0,
                    text="Stale",
                    token_count=1,
                ),
            ]
        )
        await session.commit()

    retriever = VectorRetriever()
    async with async_session_factory() as session:
        out = await retriever._hydrate_ordered(session, {chunk_id: 0.99})
    assert out == []

    async with async_session_factory() as session:
        await session.execute(delete(Chunk).where(Chunk.chunk_id == chunk_id))
        await session.execute(delete(Document).where(Document.document_id == doc_old))
        await session.execute(delete(Document).where(Document.document_id == doc_new))
        await session.commit()
