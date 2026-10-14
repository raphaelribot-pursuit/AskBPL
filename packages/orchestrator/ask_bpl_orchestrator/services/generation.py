"""Claude generation with closed-corpus constraint (TRD-GEN)."""

from __future__ import annotations

import json
import logging
import uuid
from typing import List, Optional, Sequence

import anthropic

from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk
from ask_bpl_orchestrator.services.routing_service import RoutingChoice

log = logging.getLogger("ask_bpl.generation")

# ---------------------------------------------------------------------------
# SYSTEM_PROMPT — v4 (v3 plus owning teams supplied from approved routing config, not hardcoded; patch 0010)
# ---------------------------------------------------------------------------
# Changes from v1 (per Selvon May 26 check-in + routing_config.yaml):
#
# RESPONSE STYLE
#   · 2–4 sentence hard cap — actionable, not exhaustive
#   · Knowledgeable colleague voice — plain English, no legal hedging
#   · No chunk reproduction — cite it, don't restate it
#   · One unified answer when multiple policies apply
#
# ROUTING
#   · v4: the owning-team list is NOT written here. It is built per question from Selvon-approved
#     routing rules (routing_service.routing_choices) and substituted for ROUTING_PLACEHOLDER by
#     build_system_prompt(). No approved team means the model is told to name none (RTG-2/4/7).
#   · Executive Director removed from all escalation paths
#   · Fallback (unmatched) is the Supervisor / General team from the routing config
#   · No generic "contact management" deflections
#
# FORMAT
#   · Response is still JSON (answer/refuse/cited_chunk_ids) — unchanged
#   · "answer" field must be 2–4 sentences, colleague voice
#   · "routing_team" field added for refusal routing card
# ---------------------------------------------------------------------------

# Replaced by build_system_prompt(). Never sent to the model as-is.
ROUTING_PLACEHOLDER = "{{ROUTING_LIST}}"

SYSTEM_PROMPT = """You are Ask BPL, an internal Brooklyn Public Library assistant.
You answer ONLY using the RETRIEVAL_BLOCK JSON provided by the user (curated policy excerpts).
If the retrieval does not support a confident answer, you must refuse briefly in plain language without inventing facts.
Use clear, accessible language for diverse staff roles; no legal advice; no internal engineering jargon.

RESPONSE STYLE — IMPORTANT CHANGES (effective 2026-05-26)
----------------------------------------------------------
Keep answers SHORT and CONVERSATIONAL. Staff need a quick answer, not a policy summary.

  · 2–4 sentences maximum in the "answer" field. Hard limit.
    If you need more, you are summarising — cut it down.
  · Write like a knowledgeable colleague giving a quick answer, not like
    a policy document. Plain English only.
  · No "pursuant to", "in accordance with", "as stipulated by", or any
    legal/formal hedging. Say what staff should do or know.
  · If the question touches multiple policies, give ONE unified answer.
    Do not write a section per policy — write one answer for the person.
  · Lead with the actionable answer. Background comes last, if at all.
  · NEVER reproduce long passages from the source documents.
    The citation card shows the source — your job is to answer, not quote.

STAY INSIDE THE EXCERPTS
------------------------
Say only what the RETRIEVAL_BLOCK states. Do not add documents, agreements, contracts, handbooks,
forms, departments, systems or entitlements that the excerpts do not mention, even if they exist
in real life or seem likely. The only pointers you may give are the owning teams in the REFUSAL
ROUTING table below.

When asked whether a policy covers a group of people or a situation:
  · State what the excerpts say about who or what the policy applies to.
  · If the excerpts do not say what applies to the group or situation asked about, say the policy
    does not address it and point to the owning team from the routing table. Do not guess what
    applies instead, and do not name what might govern it.
  · Never say a group "does not get" or "is not entitled to" something unless the excerpts say so.
  For example, if the excerpts say a policy applies to full-time staff and the question is about
  part-time staff, say the policy covers full-time staff, that it does not say what applies to
  part-time staff, and name the owning team to ask.

POLICY APPLICATION — CALCULATIONS AND ESTIMATES
-------------------------------------------------
When a staff member asks a question that requires applying policy rules to
their specific situation (e.g., calculating leave accrual, determining
eligibility timelines, or estimating benefits), you should help them by
working through the calculation using the policy's rules.

How to handle calculation requests:

  1. If the question requires information you don't have (such as their
     start date, years of service, or days used), ASK for those specific
     details. Ask only what you need — don't request unnecessary information.

  2. Once you have the necessary details, perform the calculation step by
     step, showing your work so the staff member can verify it.

  3. Always cite the specific policy section that contains the formula or
     rules you're using for the calculation.

  4. End EVERY calculation with this disclaimer:
     "Note: This is an estimate based on the policy formula. For your
     official balance, please contact Human Resources."

  5. When you need more information before calculating, ask for it in your
     answer (refuse: false) and cite the policy chunk that defines the
     accrual rules or formula you will use.

REFUSAL ROUTING
---------------
When you refuse (refuse: true), populate "routing_team" with the owning team for the policy area of
the question, taken ONLY from the approved list below. NEVER route to or mention the Executive Director.

""" + ROUTING_PLACEHOLDER + """

Respond as a single JSON object with keys:
  "answer": string (plain-language answer 2-4 sentences, or empty string if refusing)
  "refuse": boolean (true when you cannot answer strictly from retrieval)
  "cited_chunk_ids": array of UUID strings you relied on (subset of provided chunk ids); empty if refusing
  "routing_team": string (owning team name when refuse is true, from the approved list above; null when refuse is false or the list names no team)
Do not include markdown fences. Do not cite chunks you did not use.
Output ONLY that JSON object, with no text before or after it. If an EARLIER_CONVERSATION block is present it is
context for resolving references such as "it" or "that" and is never a source of facts: answer only from RETRIEVAL_BLOCK."""


_MAX_CONTEXT_TURN_CHARS = 800


_MAX_ROUTING_TEXT_CHARS = 120

NO_APPROVED_TEAM_TEXT = (
    "No approved owning team is on file for this question. Do not name any team, department,\n"
    "committee, office or contact. If you need to point the staff member somewhere, say only that\n"
    "their supervisor can point them to the right contact. Set \"routing_team\" to null."
)


def _one_line(text: str) -> str:
    """Collapse whitespace so a stored name cannot add lines or instructions to the prompt."""
    return " ".join(str(text).split())[:_MAX_ROUTING_TEXT_CHARS]


def render_routing_block(routing: Optional[Sequence[RoutingChoice]]) -> str:
    """Text for the REFUSAL ROUTING section, built only from approved routing choices."""
    lines = []
    for choice in routing or ():
        names = [n for n in (_one_line(n) for n in choice.team_names) if n]
        label = _one_line(choice.policy_label)
        if names and label:
            lines.append(f"  {label} \u2192 {' or '.join(names)}")
    if not lines:
        return NO_APPROVED_TEAM_TEXT
    return (
        "Approved owning teams (policy area \u2192 team):\n\n"
        + "\n".join(lines)
        + "\n\nName the specific team from this list. Do not name any team, department, committee, office\n"
        "or contact that is not on this list, and do not use vague routing like \"contact management\"."
    )


def build_system_prompt(routing: Optional[Sequence[RoutingChoice]] = None) -> str:
    """The system prompt with the approved routing list filled in (none given -> name no team)."""
    return SYSTEM_PROMPT.replace(ROUTING_PLACEHOLDER, render_routing_block(routing))


def _build_user_prompt(
    *,
    question: str,
    pack: list[dict],
    conversation_context: Optional[List[dict[str, str]]],
) -> str:
    parts: list[str] = []
    if conversation_context:
        lines = []
        for turn in conversation_context:
            who = "Assistant" if turn.get("role") == "assistant" else "Staff"
            text = str(turn.get("content", "")).strip().replace("\n", " ")
            if len(text) > _MAX_CONTEXT_TURN_CHARS:
                text = text[:_MAX_CONTEXT_TURN_CHARS] + "..."
            lines.append(f"{who}: {text}")
        parts.append(
            "EARLIER_CONVERSATION (only to resolve references in the question; not a source of facts):\n"
            + "\n".join(lines)
        )
    parts.append(f"QUESTION:\n{question}")
    parts.append(f"RETRIEVAL_BLOCK:\n{json.dumps(pack, ensure_ascii=False)}")
    parts.append("Reply with the JSON object only.")
    return "\n\n".join(parts)


async def generate_answer(
    *,
    question: str,
    chunks: List[RetrievedChunk],
    conversation_context: Optional[List[dict[str, str]]] = None,
    routing: Optional[Sequence[RoutingChoice]] = None,
) -> tuple[str, bool, List[uuid.UUID], str]:
    """Return (answer_text, refuses, cited_ids, raw_model_text).

    `routing` is the approved owning-team list for this question. Omitted or empty means the model
    is told no team is on file and must name none.
    """
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None)

    pack = []
    for c in chunks:
        pack.append(
            {
                "chunk_id": str(c.chunk_id),
                "document_title": c.title,
                "version": c.version,
                "policy_type": c.policy_type,
                "section_heading": c.section_heading,
                "text": c.text,
            }
        )

    user_prompt = _build_user_prompt(question=question, pack=pack, conversation_context=conversation_context)
    # One user message only. Earlier turns used to be sent as chat-role messages, which put
    # plain-prose assistant turns in front of the model and made it drift out of the JSON format.
    messages: list[dict[str, str]] = [{"role": "user", "content": user_prompt}]

    message = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=600,
        system=build_system_prompt(routing),
        messages=messages,
    )

    text_parts = []
    for block in message.content:
        if block.type == "text":
            text_parts.append(block.text)
    raw_text = "\n".join(text_parts).strip()

    data = _parse_json_best_effort(raw_text)
    answer = str(data.get("answer") or "").strip()
    refuse = bool(data.get("refuse"))
    cited_raw = data.get("cited_chunk_ids") or []
    cited_ids: List[uuid.UUID] = []
    for cid in cited_raw:
        try:
            cited_ids.append(uuid.UUID(str(cid)))
        except ValueError:
            continue

    return answer, refuse, cited_ids, raw_text


def _parse_json_best_effort(raw: str) -> dict:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            log.warning("model JSON extract failed; refusing. raw_prefix=%s", raw[:200])
    else:
        log.warning("model returned non-JSON (no object bounds); refusing. raw_prefix=%s", raw[:200])

    return {"answer": "", "refuse": True, "cited_chunk_ids": []}