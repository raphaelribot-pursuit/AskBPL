"""Tests for the production citation verifier (GRD-5, NFR-2, BASE-4).

The function under test is imported from the service module that ask_service calls.
Do not re-implement it here.
"""

from __future__ import annotations

import uuid

from ask_bpl_orchestrator.services.citation_verifier import verify_citations
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk


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


def test_no_citations_fails():
    chunk = uuid.uuid4()
    assert not verify_citations(cited=[], retrieval_ids={chunk}, refusal_flag=False, answer="ok")
    assert not verify_citations(cited=None, retrieval_ids={chunk}, refusal_flag=False, answer="ok")


def test_one_foreign_citation_among_valid_ones_fails():
    a, foreign = uuid.uuid4(), uuid.uuid4()
    assert not verify_citations(cited=[a, foreign], retrieval_ids={a}, refusal_flag=False, answer="ok")


def test_ask_service_uses_the_production_verifier():
    from ask_bpl_orchestrator.services import ask_service

    assert ask_service.verify_citations is verify_citations
