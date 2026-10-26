"""Patch 0011: refusal causes (PRD RTG-6).

What these tests protect:
  * every refusal is logged with the real cause, and staff see only plain wording (UX spec: no labels);
  * "could not confirm an answer would match the policy text" appears ONLY when that is what happened;
  * a broken search or model is a 5xx, never a refusal that could pass as a correct "no";
  * "relevant text exists but may not be cited as current" is told apart from "nothing found".

No network. The model and the vector search are faked. DB tests use their own rows and clean up.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pinecone.errors.exceptions import PineconeError
from sqlalchemy import delete

from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.db.models import (
    Chunk,
    Document,
    Eligibility,
    IngestStatus,
    Question,
    SourceFormat,
)
from ask_bpl_orchestrator.db.session import async_session_factory
from ask_bpl_orchestrator.evals.scoring import outcome_of
from ask_bpl_orchestrator.main import app
from ask_bpl_orchestrator.services import generation
from ask_bpl_orchestrator.services.intent_guard import flagged_intents, intent_causes
from ask_bpl_orchestrator.services.refusal import (
    NOT_ENOUGH_INFORMATION,
    TECHNICAL_CAUSES,
    TECHNICAL_HTTP_STATUS,
    USER_MESSAGES,
    RefusalCause,
    classify_generation_failure,
    classify_retrieval_gate_failure,
    is_technical,
    user_message,
)
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk, VectorRetriever
from ask_bpl_orchestrator.services.routing_service import _PLACEHOLDER_MARKERS

client = TestClient(app)
_REAL_PINECONE_SCORES = VectorRetriever._pinecone_scores  # captured before any test stubs it
GENERATE = "ask_bpl_orchestrator.services.ask_service.generation.generate_answer"
SETTINGS = get_settings()
FLOOR, STRONG = SETTINGS.grounding_threshold, SETTINGS.grounding_strong_threshold

# Words that would tell staff HOW the system decided. None may appear in any staff-facing message.
FORBIDDEN_IN_STAFF_TEXT = [
    "grounding",
    "threshold",
    "retriev",
    "citation",
    "classif",
    "embedding",
    "pinecone",
    "json",
    "weak evidence",
    "absent",
    "ambiguous",
    "score",
    "verif",
]


@pytest.fixture(autouse=True)
def _no_live_vector_lookup():
    with patch.object(VectorRetriever, "_pinecone_scores", new_callable=AsyncMock, return_value={}):
        yield


# ---- wording and tables (no DB)


def test_every_cause_has_a_message_and_a_technical_status_where_needed() -> None:
    assert set(USER_MESSAGES) == set(RefusalCause)
    assert set(TECHNICAL_HTTP_STATUS) == set(TECHNICAL_CAUSES)
    assert all(s in (502, 503) for s in TECHNICAL_HTTP_STATUS.values())


def test_staff_wording_has_no_labels_or_technical_terms() -> None:
    for cause, text in USER_MESSAGES.items():
        lowered = text.lower()
        for word in FORBIDDEN_IN_STAFF_TEXT:
            assert word not in lowered, f"{cause.value}: {word!r} in {text!r}"


def test_staff_wording_never_shows_placeholder_text() -> None:
    for text in USER_MESSAGES.values():
        assert not any(m in text.lower() for m in _PLACEHOLDER_MARKERS), text


def test_absent_source_and_weak_evidence_read_the_same_to_staff() -> None:
    """The distinction is for the log. Different wording would reveal which detector fired."""
    assert user_message(RefusalCause.absent_source) == user_message(RefusalCause.weak_evidence)
    assert user_message(RefusalCause.absent_source) == NOT_ENOUGH_INFORMATION


def test_the_not_enough_information_sentence_is_the_ux_spec_sentence() -> None:
    assert (
        NOT_ENOUGH_INFORMATION
        == "I could not find enough approved policy information to answer reliably."
    )


def test_only_the_three_technical_causes_are_technical() -> None:
    assert {c for c in RefusalCause if is_technical(c)} == {
        RefusalCause.retrieval_unavailable,
        RefusalCause.generation_unavailable,
        RefusalCause.model_output_invalid,
    }


# ---- classifiers (no DB)


@pytest.mark.parametrize(
    "best, excluded, expected",
    [
        (0.0, 0.0, RefusalCause.absent_source),  # nothing came back
        (FLOOR - 0.01, 0.0, RefusalCause.absent_source),  # below the floor
        (FLOOR, 0.0, RefusalCause.weak_evidence),  # reached the floor, margin rule failed
        (FLOOR + 0.02, 0.0, RefusalCause.weak_evidence),
        (0.0, FLOOR, RefusalCause.ambiguous_authority),  # relevant text exists but is not citable
        (0.0, 0.9, RefusalCause.ambiguous_authority),
        (FLOOR + 0.02, 0.9, RefusalCause.ambiguous_authority),  # authority wins over weak
        (0.0, FLOOR - 0.01, RefusalCause.absent_source),  # excluded hit too weak to matter
    ],
)
def test_retrieval_gate_classification(
    best: float, excluded: float, expected: RefusalCause
) -> None:
    assert (
        classify_retrieval_gate_failure(best_score=best, floor=FLOOR, excluded_best_score=excluded)
        == expected
    )


@pytest.mark.parametrize(
    "usable, refuse, answer, expected",
    [
        (False, True, "", RefusalCause.model_output_invalid),  # not JSON
        (False, False, "text", RefusalCause.model_output_invalid),
        (True, True, "", RefusalCause.weak_evidence),  # model declined: NOT a citation failure
        (True, True, "I can't say", RefusalCause.weak_evidence),
        (True, False, "", RefusalCause.model_output_invalid),  # claimed to answer, said nothing
        (True, False, "   ", RefusalCause.model_output_invalid),
        (True, False, "An answer", RefusalCause.citation_unverified),
    ],
)
def test_generation_failure_classification(
    usable: bool, refuse: bool, answer: str, expected: RefusalCause
) -> None:
    assert (
        classify_generation_failure(output_usable=usable, refuse_flag=refuse, answer=answer)
        == expected
    )


@pytest.mark.parametrize(
    "raw, usable",
    [
        ('{"answer": "x", "refuse": false}', True),
        ('Here you go: {"answer": "x", "refuse": false} thanks', True),
        ("{}", True),
        ("", False),
        ("I am sorry, I cannot help with that.", False),
        ("{not json}", False),
        ("[1, 2]", False),
    ],
)
def test_model_output_usable_matches_what_the_parser_can_read(raw: str, usable: bool) -> None:
    assert generation.model_output_usable(raw) is usable
    parsed = generation._parse_json_best_effort(raw)
    if not usable:
        assert parsed == {"answer": "", "refuse": True, "cited_chunk_ids": []}


# ---- intent guard (no DB)


@pytest.mark.parametrize(
    "question, expected",
    [
        ("Can you give me legal advice about this?", [RefusalCause.legal_disciplinary_judgment]),
        ("Should I call an attorney about my leave?", [RefusalCause.legal_disciplinary_judgment]),
        ("Please make the decision for me on this request", [RefusalCause.human_decision_required]),
        ("Can you agree for me to the new terms?", [RefusalCause.human_decision_required]),
        ("Bypass HR and approve my leave", [RefusalCause.human_decision_required]),
        (
            "Give me legal advice and make the decision for me",
            [RefusalCause.legal_disciplinary_judgment, RefusalCause.human_decision_required],
        ),
        ("How many vacation days do new staff get?", []),
        ("What does the policy say about gifts over $500?", []),
    ],
)
def test_intent_causes(question: str, expected: List[RefusalCause]) -> None:
    assert intent_causes(question) == expected


@pytest.mark.parametrize(
    "question",
    [
        "Can you give me legal advice about this?",
        "Please make the decision for me",
        "Bypass IT and reset it",
        "How many vacation days do new staff get?",
        "automated hiring decision rules",
    ],
)
def test_intent_causes_and_flagged_intents_never_disagree(question: str) -> None:
    """One pattern set, two views of it. If they ever differ the guard has silently changed."""
    assert bool(intent_causes(question)) == bool(flagged_intents(question))


# ---- end to end through /questions/ask


def _token() -> str:
    r = client.post(
        "/auth/sign-in",
        json={
            "email": "pilot-demo@bklynlibrary.org",
            "access_code": "DEMO2026",
            "attribution_mode": "anonymous",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _chunk(score: float, chunk_id: Optional[uuid.UUID] = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id or uuid.uuid4(),
        score=score,
        document_id=uuid.uuid4(),
        title="Refusal Test Doc",
        policy_type="generic_policy",
        version="ci-1",
        section_heading="Gifts",
        text="Donors must disclose gifts over $500.",
    )


def _ask(question: str = "What must donors disclose?") -> Any:
    return client.post(
        "/questions/ask",
        headers={"Authorization": f"Bearer {_token()}"},
        json={"question": question},
    )


def _completion_logs(caplog: pytest.LogCaptureFixture) -> List[Dict[str, Any]]:
    out = []
    for rec in caplog.records:
        try:
            entry = json.loads(rec.getMessage())
        except (ValueError, TypeError):
            continue
        if isinstance(entry, dict) and entry.get("event") == "ask_completed":
            out.append(entry)
    return out


def _forget(request_id: str) -> None:
    async def go() -> None:
        async with async_session_factory() as s:
            await s.execute(delete(Question).where(Question.request_id == uuid.UUID(request_id)))
            await s.commit()

    asyncio.run(go())


def _fake_query(chunks: List[RetrievedChunk], *, excluded_best: float = 0.0):
    async def fake(
        self: VectorRetriever, db: Any, question: str, top_k: int
    ) -> List[RetrievedChunk]:
        self.excluded_best_score = excluded_best
        return chunks

    return patch.object(VectorRetriever, "query", fake)


def _no_label_leaks(body: Dict[str, Any]) -> None:
    """Nothing in what the browser receives may name a cause."""
    blob = json.dumps(body).lower()
    for cause in RefusalCause:
        assert cause.value not in blob, f"cause {cause.value!r} leaked into the response"
    assert "refusal_stage" not in blob and "technical_failure" not in blob


@pytest.mark.parametrize(
    "question, cause",
    [
        ("Can you give me legal advice about my leave?", RefusalCause.legal_disciplinary_judgment),
        (
            "Please make the decision for me about this request",
            RefusalCause.human_decision_required,
        ),
    ],
)
def test_intent_guard_refusal_logs_its_real_cause(
    caplog, question: str, cause: RefusalCause
) -> None:
    caplog.set_level(logging.INFO)
    with _fake_query([]):
        r = _ask(question)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "refusal_oo_corpus"
    assert body["refusal_explanation"] == user_message(cause)
    _no_label_leaks(body)
    log = _completion_logs(caplog)[-1]
    assert log["refusal_reason"] == cause.value
    assert log["refusal_stage"] == "intent_guard"
    assert log["retrieval_hit"] is False
    _forget(body["request_id"])


def test_nothing_found_is_absent_source(caplog) -> None:
    caplog.set_level(logging.INFO)
    with _fake_query([]):
        r = _ask()
    body = r.json()
    assert r.status_code == 200 and body["type"] == "refusal_oo_corpus"
    assert body["refusal_explanation"] == NOT_ENOUGH_INFORMATION
    log = _completion_logs(caplog)[-1]
    assert (log["refusal_reason"], log["refusal_stage"]) == ("absent_source", "retrieval_gate")
    _no_label_leaks(body)
    _forget(body["request_id"])


def test_one_middling_chunk_is_weak_evidence(caplog) -> None:
    caplog.set_level(logging.INFO)
    middling = FLOOR + (STRONG - FLOOR) / 2  # above the floor, below strong, only one chunk
    with _fake_query([_chunk(middling)]):
        r = _ask()
    body = r.json()
    assert r.status_code == 200
    assert body["refusal_explanation"] == NOT_ENOUGH_INFORMATION
    log = _completion_logs(caplog)[-1]
    assert (log["refusal_reason"], log["retrieval_hit"], log["grounding_passed"]) == (
        "weak_evidence",
        True,
        False,
    )
    _forget(body["request_id"])


def test_relevant_text_that_may_not_be_cited_is_ambiguous_authority(caplog) -> None:
    caplog.set_level(logging.INFO)
    with _fake_query([], excluded_best=0.9):
        r = _ask()
    body = r.json()
    assert r.status_code == 200 and body["type"] == "refusal_oo_corpus"
    assert body["refusal_explanation"] == user_message(RefusalCause.ambiguous_authority)
    assert body["refusal_explanation"] != NOT_ENOUGH_INFORMATION
    assert _completion_logs(caplog)[-1]["refusal_reason"] == "ambiguous_authority"
    _no_label_leaks(body)
    _forget(body["request_id"])


def test_model_refusal_does_not_claim_a_citation_check_failed(caplog) -> None:
    """The reported bug: the model says it cannot answer, and staff were told citations could not be verified."""
    caplog.set_level(logging.INFO)
    stub = AsyncMock(
        return_value=("", True, [], '{"answer": "", "refuse": true, "cited_chunk_ids": []}')
    )
    with _fake_query([_chunk(0.95)]), patch(GENERATE, stub):
        r = _ask()
    body = r.json()
    assert r.status_code == 200
    assert body["type"] == "refusal_oo_corpus"
    assert body["refusal_explanation"] == NOT_ENOUGH_INFORMATION
    assert "citation" not in body["refusal_explanation"].lower()
    assert body["refusal_explanation"] != user_message(RefusalCause.citation_unverified)
    log = _completion_logs(caplog)[-1]
    assert (log["refusal_reason"], log["refusal_stage"]) == ("weak_evidence", "model")
    _no_label_leaks(body)
    _forget(body["request_id"])


def test_model_refusal_that_still_lists_citations_is_still_not_a_citation_failure() -> None:
    """Previously this shape returned refusal_citation_invalid. An explicit refusal is not a citation problem."""
    c = _chunk(0.95)
    stub = AsyncMock(return_value=("", True, [c.chunk_id], '{"refuse": true}'))
    with _fake_query([c]), patch(GENERATE, stub):
        r = _ask()
    body = r.json()
    assert body["type"] == "refusal_oo_corpus"
    assert body["refusal_explanation"] == NOT_ENOUGH_INFORMATION
    _forget(body["request_id"])


def test_answer_citing_something_never_retrieved_is_the_real_citation_failure(caplog) -> None:
    caplog.set_level(logging.INFO)
    stub = AsyncMock(
        return_value=("Disclose gifts over $500.", False, [uuid.uuid4()], '{"refuse": false}')
    )
    with _fake_query([_chunk(0.95)]), patch(GENERATE, stub):
        r = _ask()
    body = r.json()
    assert r.status_code == 200
    assert body["type"] == "refusal_citation_invalid"
    assert body["refusal_explanation"] == user_message(RefusalCause.citation_unverified)
    log = _completion_logs(caplog)[-1]
    assert (log["refusal_reason"], log["refusal_stage"]) == (
        "citation_unverified",
        "citation_check",
    )
    assert body["citations"] == []
    _forget(body["request_id"])


def test_answer_with_no_citations_is_a_citation_failure_of_the_plain_type() -> None:
    stub = AsyncMock(return_value=("Disclose gifts over $500.", False, [], '{"refuse": false}'))
    with _fake_query([_chunk(0.95)]), patch(GENERATE, stub):
        r = _ask()
    body = r.json()
    assert body["type"] == "refusal_oo_corpus"
    assert body["refusal_explanation"] == user_message(RefusalCause.citation_unverified)
    _forget(body["request_id"])


def test_model_reply_that_is_not_json_is_a_502_not_a_refusal(caplog) -> None:
    caplog.set_level(logging.INFO)
    stub = AsyncMock(return_value=("", True, [], "I am sorry, I cannot help with that."))
    with _fake_query([_chunk(0.95)]), patch(GENERATE, stub):
        r = _ask()
    assert r.status_code == 502, r.text
    body = r.json()
    assert body["type"] == "error_unavailable"
    assert body["message"] == user_message(RefusalCause.model_output_invalid)
    assert "answer" not in body and "citations" not in body
    log = _completion_logs(caplog)[-1]
    assert (log["technical_failure"], log["refusal"], log["refusal_reason"]) == (
        "model_output_invalid",
        False,
        None,
    )
    _no_label_leaks(body)
    _forget(body["request_id"])


def test_search_failure_is_a_503_not_a_no_policy_refusal(caplog) -> None:
    """A Pinecone outage used to read as "I couldn't locate relevant policy excerpts"."""
    caplog.set_level(logging.INFO)
    index = MagicMock()
    index.query.side_effect = PineconeError("quota exceeded")
    keyed = SETTINGS.model_copy(update={"pinecone_api_key": "pc-test"})
    with (
        patch.object(
            VectorRetriever, "_pinecone_scores", _REAL_PINECONE_SCORES
        ),  # undo the autouse stub
        patch.object(
            VectorRetriever, "embed_question", new_callable=AsyncMock, return_value=[0.0] * 8
        ),
        patch.object(VectorRetriever, "_pinecone_index", return_value=index),
        patch("ask_bpl_orchestrator.services.retrieval.get_settings", return_value=keyed),
    ):
        r = _ask()
    assert r.status_code == 503, r.text
    body = r.json()
    assert body["type"] == "error_unavailable"
    assert body["message"] == user_message(RefusalCause.retrieval_unavailable)
    assert _completion_logs(caplog)[-1]["technical_failure"] == "retrieval_unavailable"
    _no_label_leaks(body)
    _forget(body["request_id"])


def test_missing_model_key_is_a_503_not_a_refusal(caplog) -> None:
    caplog.set_level(logging.INFO)
    no_key = SETTINGS.model_copy(update={"anthropic_api_key": ""})
    with (
        _fake_query([_chunk(0.95)]),
        patch("ask_bpl_orchestrator.services.ask_service.get_settings", return_value=no_key),
    ):
        r = _ask()
    assert r.status_code == 503, r.text
    body = r.json()
    assert body["type"] == "error_unavailable"
    assert body["message"] == user_message(RefusalCause.generation_unavailable)
    assert _completion_logs(caplog)[-1]["technical_failure"] == "generation_unavailable"
    _forget(body["request_id"])


def test_a_good_answer_is_unchanged_and_logs_no_refusal_fields(caplog) -> None:
    caplog.set_level(logging.INFO)
    c = _chunk(0.95)

    async def seed() -> None:
        async with async_session_factory() as s:
            s.add(
                Document(
                    document_id=c.document_id,
                    title="Refusal Test Doc",
                    version="ci-1",
                    policy_type="generic_policy",
                    source_format=SourceFormat.md,
                    ingest_status=IngestStatus.indexed,
                    eligibility=Eligibility.eligible,
                    source_sha256="a" * 64, approved_sha256="a" * 64,  # an approved file (patch 0023)
                )
            )
            s.add(
                Chunk(
                    chunk_id=c.chunk_id,
                    document_id=c.document_id,
                    ordinal=0,
                    text=c.text,
                    token_count=8,
                )
            )
            await s.commit()

    async def unseed(rid: str) -> None:
        async with async_session_factory() as s:
            await s.execute(delete(Question).where(Question.request_id == uuid.UUID(rid)))
            await s.execute(delete(Chunk).where(Chunk.chunk_id == c.chunk_id))
            await s.execute(delete(Document).where(Document.document_id == c.document_id))
            await s.commit()

    asyncio.run(seed())
    stub = AsyncMock(
        return_value=("Disclose gifts over $500.", False, [c.chunk_id], '{"refuse": false}')
    )
    with _fake_query([c]), patch(GENERATE, stub):
        r = _ask()
    body = r.json()
    assert r.status_code == 200 and body["type"] == "answer"
    log = _completion_logs(caplog)[-1]
    assert log["refusal"] is False and log["refusal_reason"] is None
    assert "refusal_stage" not in log and "technical_failure" not in log
    asyncio.run(unseed(body["request_id"]))


# ---- retrieval: what was excluded (DB)


def _doc(**kw: Any) -> Document:
    base = dict(
        document_id=uuid.uuid4(),
        title="Excluded Doc",
        version="1",
        policy_type="generic_policy",
        source_format=SourceFormat.md,
        ingest_status=IngestStatus.indexed,
    )
    base.update(kw)
    return Document(**base)


async def _hydrate(retriever: VectorRetriever, scores: Dict[uuid.UUID, float]):
    async with async_session_factory() as s:
        return await retriever._hydrate_ordered(s, scores)


async def _purge(chunk_ids: List[uuid.UUID], doc_ids: List[uuid.UUID]) -> None:
    async with async_session_factory() as s:
        await s.execute(delete(Chunk).where(Chunk.chunk_id.in_(chunk_ids)))
        await s.execute(delete(Document).where(Document.document_id.in_(doc_ids)))
        await s.commit()


@pytest.mark.asyncio
async def test_hydrate_counts_uncitable_hits_but_not_stale_vectors_or_eligible_ones() -> None:
    pending = _doc(eligibility=Eligibility.authority_pending, test_index_member=False)
    eligible = _doc(eligibility=Eligibility.eligible, source_sha256="a" * 64, approved_sha256="a" * 64)  # an approved file (patch 0023)
    c_pending, c_eligible, c_stale = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with async_session_factory() as s:
        s.add_all([pending, eligible])
        await s.flush()
        s.add_all(
            [
                Chunk(
                    chunk_id=c_pending,
                    document_id=pending.document_id,
                    ordinal=0,
                    text="p",
                    token_count=1,
                ),
                Chunk(
                    chunk_id=c_eligible,
                    document_id=eligible.document_id,
                    ordinal=0,
                    text="e",
                    token_count=1,
                ),
            ]
        )
        await s.commit()
    try:
        r = VectorRetriever()
        out = await _hydrate(r, {c_pending: 0.91, c_eligible: 0.70, c_stale: 0.99})
        assert [c.chunk_id for c in out] == [c_eligible]
        assert r.excluded_count == 1  # the stale vector (no chunk row) is not an authority question
        assert r.excluded_best_score == pytest.approx(0.91)
    finally:
        await _purge([c_pending, c_eligible], [pending.document_id, eligible.document_id])


@pytest.mark.asyncio
async def test_test_index_document_becomes_excluded_when_the_test_index_is_switched_off() -> None:
    """The go-live rehearsal: ALLOW_TEST_INDEX=false must turn today's answers into 'not confirmed current'."""
    doc = _doc(eligibility=Eligibility.authority_pending, test_index_member=True)
    cid = uuid.uuid4()
    async with async_session_factory() as s:
        s.add(doc)
        await s.flush()
        s.add(Chunk(chunk_id=cid, document_id=doc.document_id, ordinal=0, text="t", token_count=1))
        await s.commit()
    try:
        on = VectorRetriever()
        on.settings = SETTINGS.model_copy(update={"allow_test_index": True})
        assert [c.chunk_id for c in await _hydrate(on, {cid: 0.8})] == [cid]
        assert on.excluded_count == 0

        off = VectorRetriever()
        off.settings = SETTINGS.model_copy(update={"allow_test_index": False})
        assert await _hydrate(off, {cid: 0.8}) == []
        assert (off.excluded_count, off.excluded_best_score) == (1, pytest.approx(0.8))
    finally:
        await _purge([cid], [doc.document_id])


def test_go_live_rehearsal_end_to_end_refuses_as_not_confirmed_current() -> None:
    doc = _doc(eligibility=Eligibility.authority_pending, test_index_member=True)
    cid = uuid.uuid4()

    async def seed() -> None:
        async with async_session_factory() as s:
            s.add(doc)
            await s.flush()
            s.add(
                Chunk(chunk_id=cid, document_id=doc.document_id, ordinal=0, text="t", token_count=1)
            )
            await s.commit()

    asyncio.run(seed())
    off = SETTINGS.model_copy(update={"allow_test_index": False})
    try:
        with (
            patch.object(
                VectorRetriever,
                "_pinecone_scores",
                new_callable=AsyncMock,
                return_value={cid: 0.92},
            ),
            patch("ask_bpl_orchestrator.services.retrieval.get_settings", return_value=off),
        ):
            r = _ask("How many days of annual leave do new staff get?")
        body = r.json()
        assert r.status_code == 200 and body["type"] == "refusal_oo_corpus"
        assert body["refusal_explanation"] == user_message(RefusalCause.ambiguous_authority)
        _forget(body["request_id"])
    finally:
        asyncio.run(_purge([cid], [doc.document_id]))


@pytest.mark.asyncio
async def test_retrieval_flags_reset_between_queries() -> None:
    r = VectorRetriever()
    r.excluded_best_score, r.excluded_count, r.search_failed = 0.9, 3, True
    async with async_session_factory() as s:
        assert await r.query(s, "anything", 5) == []  # _pinecone_scores is stubbed to {}
    assert (r.excluded_best_score, r.excluded_count, r.search_failed) == (0.0, 0, False)


# ---- the eval cannot mistake an outage for a refusal


def test_eval_scores_an_unavailable_response_as_an_error_not_a_refusal() -> None:
    """Out-of-scope eval cases expect a refusal. A broken search or model must never satisfy that."""
    for status in (502, 503):
        assert outcome_of(status, {"type": "error_unavailable", "message": "x"}) == "error"
    assert outcome_of(200, {"type": "refusal_oo_corpus"}) == "refusal"
