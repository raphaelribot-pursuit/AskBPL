"""Rewrite follow-up questions into standalone retrieval queries."""

from __future__ import annotations

import logging

import anthropic

log = logging.getLogger(__name__)

REWRITE_SYSTEM_PROMPT = """You are a query rewriter for a policy Q&A system.
Given a conversation history and a follow-up question, rewrite the follow-up
into a standalone question that can be understood without the conversation
history. The rewritten question should:
- Resolve all pronouns (they, those, it, this, etc.) to their actual referents
- Include the specific policy topic or subject being discussed
- Be a natural question a staff member would ask about a policy
- Be concise (one sentence)
Respond with ONLY the rewritten question. No explanation, no preamble."""


async def rewrite_follow_up(
    *,
    question: str,
    context: list[dict[str, str]],
    client: anthropic.AsyncAnthropic,
    model: str,
) -> str:
    """Rewrite a follow-up question into a standalone query using conversation context."""
    messages: list[dict[str, str]] = []
    for turn in context:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append(
        {
            "role": "user",
            "content": (
                f'The user just asked this follow-up question: "{question}"\n\n'
                "Rewrite it as a standalone question that resolves all pronouns "
                "and references from the conversation above."
            ),
        }
    )

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=150,
            system=REWRITE_SYSTEM_PROMPT,
            messages=messages,
        )
    except Exception:
        log.warning("query rewrite failed; using original question", exc_info=True)
        return question

    rewritten = ""
    for block in response.content:
        if block.type == "text":
            rewritten = block.text.strip()
            break

    if not rewritten:
        return question

    if rewritten.startswith('"') and rewritten.endswith('"'):
        rewritten = rewritten[1:-1]
    elif rewritten.startswith("'") and rewritten.endswith("'"):
        rewritten = rewritten[1:-1]

    return rewritten.strip() or question
