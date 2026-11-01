"""Patch 0049 (FR-01; GRD-5, GRD-8): the model cites short labels C1, C2... instead of chunk UUIDs.

BPL-FR-01 was refused as `refusal_citation_invalid` in 4 recorded runs (2026-10-28 to 2026-11-01): a real answer whose
citations included an id that was not retrieved, i.e. a miscopied UUID. Labels remove the copying; the server maps them
back, and the citation gate (services/citation_verifier.py) is unchanged. No network: the Anthropic client is faked.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from ask_bpl_orchestrator.services import generation
from ask_bpl_orchestrator.services.citation_verifier import verify_citations
from ask_bpl_orchestrator.services.generation import SYSTEM_PROMPT, chunk_labels, resolve_cited_labels
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk


def _chunk(text: str) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=uuid.uuid4(), score=0.6, document_id=uuid.uuid4(), title="Fundraising Policy",
                          policy_type="fundraising", version="v", section_heading=None, text=text)


CHUNKS = [_chunk("Development manages fundraising."), _chunk("Gifts are acknowledged."), _chunk("Grants need approval.")]


async def _ask(cited: list) -> tuple:
    reply = json.dumps({"answer": "The Development team.", "refuse": False, "cited_chunk_ids": cited, "routing_team": None})
    create = AsyncMock(return_value=SimpleNamespace(content=[SimpleNamespace(type="text", text=reply)]))
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    with patch.object(generation.anthropic, "AsyncAnthropic", return_value=client):
        result = await generation.generate_answer(question="Who manages fundraising?", chunks=CHUNKS)
    return result, create.call_args.kwargs["messages"][0]["content"]


def _gate(ids) -> bool:
    return verify_citations(cited=ids, retrieval_ids={c.chunk_id for c in CHUNKS}, refusal_flag=False, answer="x")


@pytest.mark.asyncio
async def test_the_model_is_shown_labels_not_uuids() -> None:
    _, body = await _ask(["C1"])
    pack = json.loads(body.split("RETRIEVAL_BLOCK:\n", 1)[1].split("\n\nReply with", 1)[0])
    assert [p["chunk_id"] for p in pack] == ["C1", "C2", "C3"]
    for c in CHUNKS:
        assert str(c.chunk_id) not in body


@pytest.mark.asyncio
async def test_cited_labels_map_back_to_the_retrieved_chunks_and_pass_the_gate() -> None:
    (answer, refuse, cited, _), _ = await _ask(["C1", " c3 "])
    assert cited == [CHUNKS[0].chunk_id, CHUNKS[2].chunk_id]
    assert _gate(cited) and not refuse and answer


@pytest.mark.asyncio
async def test_the_exact_uuid_of_an_offered_chunk_is_still_accepted() -> None:
    (_, _, cited, _), _ = await _ask([str(CHUNKS[1].chunk_id).upper()])
    assert cited == [CHUNKS[1].chunk_id] and _gate(cited)


@pytest.mark.parametrize("bad", [["C4"], ["C1", "C9"], ["chunk 1"], [str(uuid.uuid4())], ["C1", "not-a-uuid"]])
def test_an_unknown_citation_fails_closed_instead_of_being_dropped(bad: list) -> None:
    ids, unknown = resolve_cited_labels(bad, chunk_labels(CHUNKS), CHUNKS)
    assert unknown >= 1 and len(ids) == len(bad)
    assert not _gate(ids)


def test_labels_are_numbered_from_one_per_request() -> None:
    assert chunk_labels(CHUNKS) == ["C1", "C2", "C3"] and chunk_labels([]) == []


def test_the_prompt_asks_for_labels() -> None:
    flat = " ".join(SYSTEM_PROMPT.split())
    assert 'array of the chunk labels you relied on, exactly as given in RETRIEVAL_BLOCK (for example ["C1", "C3"])' in flat
    assert "UUID" not in SYSTEM_PROMPT
