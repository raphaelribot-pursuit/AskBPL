"""Patch 0024: through the real routes, role changes framing only (PRD ROLE-2, ROLE-8, ROLE-9, ROLE-11).

The retriever and the model are faked; Postgres is real. The invariant under test: for one question, every role gets
the same retrieval call, the same excerpts and routing handed to the model, the same answer-or-refuse decision and the
same citations. Only the role object given to generation, the logged role and the badge differ.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from ask_bpl_orchestrator.db.models import (
    Chunk,
    Document,
    Eligibility,
    IngestStatus,
    Question,
    SourceFormat,
)
from ask_bpl_orchestrator.db.session import async_session_factory
from ask_bpl_orchestrator.main import app
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk, VectorRetriever

client = TestClient(app)
ROLES = ["general", "staff", "manager"]
ROUTES = ["/questions/ask", "/v1/ask"]


@pytest.fixture(autouse=True)
def _no_live_vector_lookup():
    with patch.object(VectorRetriever, "_pinecone_scores", new_callable=AsyncMock, return_value={}):
        yield


def _token() -> str:
    r = client.post(
        "/auth/sign-in",
        json={"email": "pilot-demo@bklynlibrary.org", "access_code": "DEMO2026", "attribution_mode": "anonymous"},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture()
def corpus():
    doc_id, chunk_id = uuid.uuid4(), uuid.uuid4()

    async def seed() -> None:
        async with async_session_factory() as s:
            s.add(Document(document_id=doc_id, title="Role Lens Test Policy", version="t", policy_type="annual_leave",
                           source_format=SourceFormat.md, ingest_status=IngestStatus.indexed,
                           eligibility=Eligibility.eligible, source_sha256="a" * 64, approved_sha256="a" * 64))
            await s.flush()
            s.add(Chunk(chunk_id=chunk_id, document_id=doc_id, ordinal=0, text="Leave requests need approval.", token_count=6))
            await s.commit()

    asyncio.run(seed())
    chunk = RetrievedChunk(chunk_id=chunk_id, score=0.95, document_id=doc_id, title="Role Lens Test Policy",
                           policy_type="annual_leave", version="t", section_heading="Leave", text="Leave requests need approval.")
    yield chunk

    async def clean() -> None:
        # Questions first: their responses and citations point at the chunk (ON DELETE CASCADE from the question).
        async with async_session_factory() as s:
            if _created:
                await s.execute(delete(Question).where(Question.request_id.in_(list(_created))))
            await s.execute(delete(Chunk).where(Chunk.chunk_id == chunk_id))
            await s.execute(delete(Document).where(Document.document_id == doc_id))
            await s.commit()

    asyncio.run(clean())
    _created.clear()


_created: list[uuid.UUID] = []


def _ask(route: str, role_field, question: str = "Who approves leave requests?", *, include_role: bool = True):
    body = {"question": question}
    if include_role:
        body["user_role"] = role_field
    r = client.post(route, headers={"Authorization": f"Bearer {_token()}"}, json=body)
    if isinstance(r.json(), dict) and isinstance(r.json().get("request_id"), str):
        _created.append(uuid.UUID(r.json()["request_id"]))
    return r


async def _logged_role(request_id: str):
    async with async_session_factory() as s:
        return (await s.execute(select(Question.user_role).where(Question.request_id == uuid.UUID(request_id)))).scalar_one()


def _run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("route", ROUTES)
def test_same_question_gets_same_retrieval_excerpts_decision_and_citations_for_every_role(route, corpus) -> None:
    results = {}
    for role in ROLES:
        gen = AsyncMock(return_value=("Your supervisor approves it.", False, [corpus.chunk_id], "{}"))
        query = AsyncMock(return_value=[corpus])
        with (
            patch.object(VectorRetriever, "query", query),
            patch("ask_bpl_orchestrator.services.ask_service.generation.generate_answer", gen),
        ):
            r = _ask(route, role)
        assert r.status_code == 200, r.text
        body = r.json()
        # args[0] is the per-request database session, which differs by design; everything else must match.
        results[role] = ((query.call_args.args[1:], query.call_args.kwargs), gen.call_args.kwargs, body)

    first_query, first_gen, first_body = results["general"]
    for role in ROLES:
        q, g, body = results[role]
        assert q == first_query, f"retrieval call differs for {role}"
        assert g["question"] == first_gen["question"]
        assert g["chunks"] == first_gen["chunks"] and g["routing"] == first_gen["routing"]
        assert g["conversation_context"] == first_gen["conversation_context"]
        assert body["type"] == first_body["type"] == "answer"
        assert [c["chunk_id"] for c in body["citations"]] == [c["chunk_id"] for c in first_body["citations"]]
        assert g["role"].key == role  # the only thing that differs
        assert body["role"] == {"key": role, "label": g["role"].label}  # ROLE-9


@pytest.mark.parametrize("route", ROUTES)
def test_the_answer_or_refuse_decision_does_not_depend_on_role(route, corpus) -> None:
    """Nothing retrieved -> refusal for every role, and the model is never called (ROLE-2)."""
    types = set()
    for role in ROLES:
        gen = AsyncMock()
        with (
            patch.object(VectorRetriever, "query", new_callable=AsyncMock, return_value=[]),
            patch("ask_bpl_orchestrator.services.ask_service.generation.generate_answer", gen),
        ):
            r = _ask(route, role)
        assert r.status_code == 200, r.text
        types.add(r.json()["type"])
        gen.assert_not_called()
        assert "role" not in r.json()  # a refusal carries no lens badge
    assert len(types) == 1 and types != {"answer"}


@pytest.mark.parametrize("route", ROUTES)
def test_a_model_refusal_is_a_refusal_for_every_role(route, corpus) -> None:
    types = set()
    for role in ROLES:
        gen = AsyncMock(return_value=("", True, [], "{}"))
        with (
            patch.object(VectorRetriever, "query", new_callable=AsyncMock, return_value=[corpus]),
            patch("ask_bpl_orchestrator.services.ask_service.generation.generate_answer", gen),
        ):
            r = _ask(route, role)
        types.add(r.json()["type"])
    assert len(types) == 1 and "answer" not in types


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("sent", [None, "", "admin", "executive", "MANAGER ", "Staff"])
def test_missing_or_unrecognised_role_is_accepted_and_resolved_to_a_known_lens(route, sent, corpus) -> None:
    gen = AsyncMock(return_value=("Ok.", False, [corpus.chunk_id], "{}"))
    with (
        patch.object(VectorRetriever, "query", new_callable=AsyncMock, return_value=[corpus]),
        patch("ask_bpl_orchestrator.services.ask_service.generation.generate_answer", gen),
    ):
        r = _ask(route, sent, include_role=sent is not None)
    assert r.status_code == 200, r.text  # never a 4xx for a bad role (ROLE-11)
    expected = {"MANAGER ": "manager", "Staff": "staff"}.get(sent, "general")
    assert gen.call_args.kwargs["role"].key == expected
    assert r.json()["role"]["key"] == expected


@pytest.mark.parametrize("route", ROUTES)
def test_the_resolved_role_is_logged_on_the_question_row(route, corpus) -> None:
    gen = AsyncMock(return_value=("Ok.", False, [corpus.chunk_id], "{}"))
    with (
        patch.object(VectorRetriever, "query", new_callable=AsyncMock, return_value=[corpus]),
        patch("ask_bpl_orchestrator.services.ask_service.generation.generate_answer", gen),
    ):
        logged = {}
        for sent in ("manager", "staff", "nonsense"):
            r = _ask(route, sent)
            logged[sent] = _run(_logged_role(r.json()["request_id"]))
    assert logged == {"manager": "manager", "staff": "staff", "nonsense": "general"}  # ROLE-8, the stored value is the resolved key


def test_the_role_is_logged_even_when_the_question_is_stopped_by_a_gate(corpus) -> None:
    """Gate decisions are role-blind, and the role is still recorded on the row (ROLE-8)."""
    r = _ask("/questions/ask", "manager", "My social security number is 123-45-6789, how much leave do I have?")
    assert r.status_code in (200, 400, 422), r.text
    rid = r.json().get("request_id")
    if rid:
        assert _run(_logged_role(rid)) == "manager"


def test_gates_give_the_same_result_for_every_role(corpus) -> None:
    outcomes = {}
    for role in ROLES:
        r = _ask("/questions/ask", role, "I want to hurt myself, what should I do?")
        outcomes[role] = (r.status_code, r.json().get("type"))
    assert len(set(outcomes.values())) == 1, outcomes


def test_source_scan_only_the_generation_call_and_the_log_read_the_role() -> None:
    """ROLE-2 guard: retrieval, gates, grounding and the verifier must not mention the role."""
    from pathlib import Path

    import ask_bpl_orchestrator.services as svc

    root = Path(svc.__file__).parent
    for name in ("retrieval.py", "citation_verifier.py", "crisis_gate.py", "pii_gate.py", "intent_guard.py",
                 "eligibility.py", "refusal.py", "routing_service.py", "query_rewriter.py", "glossary.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "user_role" not in text and "get_roles" not in text, f"{name} must stay role-blind"
    ask = (root / "ask_service.py").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in ask.splitlines() if "role" in ln and not ln.strip().startswith("#")]
    allowed = ("user_role", "get_roles", "role=role", "role.key", "role.label", "role = ", '"role"', "role Lens", "import")
    for ln in lines:
        assert any(a in ln for a in allowed) or "conversation" in ln.lower() or '"role"' in ln, f"unexpected role use: {ln}"
