"""Tests for follow-up query rewriting."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ask_bpl_orchestrator.services.query_rewriter import rewrite_follow_up


@pytest.mark.asyncio
async def test_rewrite_follow_up_strips_wrapping_quotes() -> None:
    client = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = '"What criteria are used when selecting library materials?"'
    response = MagicMock()
    response.content = [block]
    client.messages.create = AsyncMock(return_value=response)

    result = await rewrite_follow_up(
        question="What criteria do they use for those selections?",
        context=[
            {
                "role": "user",
                "content": "Who has final authority over selecting library materials?",
            },
            {
                "role": "assistant",
                "content": "The Executive Director holds final responsibility.",
            },
        ],
        client=client,
        model="claude-sonnet-4-20250514",
    )

    assert result == "What criteria are used when selecting library materials?"


@pytest.mark.asyncio
async def test_rewrite_follow_up_falls_back_on_api_error() -> None:
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=RuntimeError("api down"))

    question = "What criteria do they use for those selections?"
    result = await rewrite_follow_up(
        question=question,
        context=[{"role": "user", "content": "Prior question?"}],
        client=client,
        model="claude-sonnet-4-20250514",
    )

    assert result == question
