"""Earlier chat turns must reach the model as data inside ONE user message (not as chat roles),
and the reply parser must behave as documented. No network: Anthropic client is faked."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from ask_bpl_orchestrator.services import generation
from ask_bpl_orchestrator.services.generation import SYSTEM_PROMPT, _parse_json_best_effort
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk

CID = uuid.uuid4()
CHUNK = RetrievedChunk(chunk_id=CID, score=0.6, document_id=uuid.uuid4(), title="Annual Leave Policy",
                       policy_type="annual_leave", version="v", section_heading=None, text="90 day waiting period")
GOOD = f'{{"answer": "Yes, 90 days.", "refuse": false, "cited_chunk_ids": ["{CID}"], "routing_team": null}}'


def _fake_client(reply_text: str):
    create = AsyncMock(return_value=SimpleNamespace(content=[SimpleNamespace(type="text", text=reply_text)]))
    return SimpleNamespace(messages=SimpleNamespace(create=create)), create


async def _run(context, reply=GOOD):
    client, create = _fake_client(reply)
    with patch.object(generation.anthropic, "AsyncAnthropic", return_value=client):
        result = await generation.generate_answer(question="Is there a waiting period?", chunks=[CHUNK],
                                                  conversation_context=context)
    return result, create.call_args.kwargs


CONTEXT = [
    {"role": "user", "content": "How many days can I carry over?"},
    {"role": "assistant", "content": "Up to 7 days carry over; the rest goes to your sick leave bank."},
]


@pytest.mark.asyncio
async def test_earlier_turns_are_folded_into_a_single_user_message() -> None:
    _, kwargs = await _run(CONTEXT)
    msgs = kwargs["messages"]
    assert len(msgs) == 1 and msgs[0]["role"] == "user"
    assert not any(m["role"] == "assistant" for m in msgs)  # no prose-in-assistant-role to imitate
    body = msgs[0]["content"]
    assert "EARLIER_CONVERSATION" in body
    assert "Staff: How many days can I carry over?" in body
    assert "Assistant: Up to 7 days carry over" in body
    # current question and excerpts still present, in that order
    assert body.index("EARLIER_CONVERSATION") < body.index("QUESTION:") < body.index("RETRIEVAL_BLOCK:")
    assert body.rstrip().endswith("Reply with the JSON object only.")


@pytest.mark.asyncio
async def test_no_context_means_no_earlier_block_and_one_message() -> None:
    _, kwargs = await _run(None)
    assert len(kwargs["messages"]) == 1
    assert "EARLIER_CONVERSATION" not in kwargs["messages"][0]["content"]


@pytest.mark.asyncio
async def test_system_prompt_demands_json_only_and_denies_history_as_a_source() -> None:
    _, kwargs = await _run(CONTEXT)
    assert kwargs["system"] == SYSTEM_PROMPT
    assert "Output ONLY that JSON object" in SYSTEM_PROMPT
    assert "never a source of facts" in SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_long_earlier_turn_is_truncated() -> None:
    long_turn = [{"role": "assistant", "content": "x" * 5000}]
    _, kwargs = await _run(long_turn)
    body = kwargs["messages"][0]["content"]
    assert "x" * 801 not in body and "..." in body


@pytest.mark.asyncio
async def test_answer_and_citation_are_parsed_from_a_good_reply() -> None:
    (answer, refuse, cited, _), _ = await _run(CONTEXT)
    assert (answer, refuse, cited) == ("Yes, 90 days.", False, [CID])


# --- documented behaviour of the reply parser (what the live drift looked like) ---

def test_prose_before_json_is_recovered() -> None:
    data = _parse_json_best_effort("Yes, 90 days.\n\n" + GOOD)
    assert data["refuse"] is False and data["cited_chunk_ids"] == [str(CID)]


def test_prose_only_reply_falls_back_to_refusal() -> None:
    data = _parse_json_best_effort("Yes, new hires wait 90 days.")
    assert data == {"answer": "", "refuse": True, "cited_chunk_ids": []}


def test_truncated_json_falls_back_to_refusal() -> None:
    data = _parse_json_best_effort('{"answer": "Yes, 90 days.", "refuse": false, "cited_chunk_ids": ["')
    assert data["refuse"] is True and data["cited_chunk_ids"] == []


# --- closed-corpus wording (structural: proves the rule is in the prompt, not that the model obeys it) ---

def test_prompt_forbids_adding_documents_or_entitlements_not_in_excerpts() -> None:
    assert "STAY INSIDE THE EXCERPTS" in SYSTEM_PROMPT
    assert "Do not add documents, agreements, contracts" in SYSTEM_PROMPT
    assert "The only pointers you may give are the owning teams" in SYSTEM_PROMPT


def test_prompt_handles_scope_questions_without_inventing_what_applies_instead() -> None:
    assert "say the policy" in SYSTEM_PROMPT and "does not address it" in SYSTEM_PROMPT
    assert 'Never say a group "does not get"' in SYSTEM_PROMPT


def test_the_rule_comes_before_the_calculation_section_and_routing_table_it_refers_to() -> None:
    i_rule = SYSTEM_PROMPT.index("STAY INSIDE THE EXCERPTS")
    assert i_rule < SYSTEM_PROMPT.index("POLICY APPLICATION")
    assert i_rule < SYSTEM_PROMPT.index("REFUSAL ROUTING\n")
