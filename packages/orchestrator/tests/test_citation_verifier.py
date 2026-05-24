"""Citation verification logic used in ask_service (TRD-GRD-4)."""

from __future__ import annotations

import uuid

from ask_bpl_orchestrator.services.retrieval import RetrievedChunk


def verify_citations(
    *,
    cited: list[uuid.UUID] | None,
    retrieval_ids: set[uuid.UUID],
    refusal_flag: bool,
    answer: str,
) -> bool:
    """Mirror ask_service citation gate for unit testing."""
    return (
        bool(cited)
        and all(i in retrieval_ids for i in cited)
        and not refusal_flag
        and answer.strip() != ""
    )


def test_valid_citations_pass():
    a, b = uuid.uuid4(), uuid.uuid4()
    assert verify_citations(cited=[a], retrieval_ids={a, b}, refusal_flag=False, answer="ok")


def test_unknown_chunk_fails():
    a, foreign = uuid.uuid4(), uuid.uuid4()
    assert not verify_citations(cited=[foreign], retrieval_ids={a}, refusal_flag=False, answer="ok")


def test_empty_answer_fails():
    chunk = uuid.uuid4()
    assert not verify_citations(cited=[chunk], retrieval_ids={chunk}, refusal_flag=False, answer="  ")


def test_model_refusal_flag_fails():
    chunk = uuid.uuid4()
    assert not verify_citations(cited=[chunk], retrieval_ids={chunk}, refusal_flag=True, answer="text")


def test_retrieved_chunk_carries_section_heading():
    chunk_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    row = RetrievedChunk(
        chunk_id=chunk_id,
        score=0.9,
        document_id=doc_id,
        title="Gift Policy",
        policy_type="gift_acceptance",
        version="1",
        section_heading="Approval Thresholds",
        text="Gifts over $5000 need director approval.",
    )
    assert row.section_heading == "Approval Thresholds"
