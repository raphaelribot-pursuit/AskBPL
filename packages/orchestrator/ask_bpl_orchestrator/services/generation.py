"""Claude generation with closed-corpus constraint (TRD-GEN)."""

from __future__ import annotations

import json
import logging
import uuid
from typing import List, Optional

import anthropic

from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk

log = logging.getLogger("ask_bpl.generation")

SYSTEM_PROMPT = """You are Ask BPL, an internal Brooklyn Public Library assistant.
You answer ONLY using the RETRIEVAL_BLOCK JSON provided by the user (curated policy excerpts).
If the retrieval does not support a confident answer, you must refuse briefly in plain language without inventing facts.
Use clear, accessible language for diverse staff roles; no legal advice; no internal engineering jargon.

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

Example — Annual Leave Accrual:

  Staff: "I started in March 2025. How much annual leave have I earned?"

  Ask BPL: Based on the Annual Leave Policy, here's your estimated accrual:

  Since you started in March 2025, you're in your first year of service.
  First-year employees earn 4.0385 hours per pay period (26 biweekly pay
  periods per year).

  From March 2025 to now (approximately 14 months / about 30 pay periods),
  you would have earned approximately:
  30 pay periods × 4.0385 hours = ~121.2 hours (~17.3 days)

  However, please keep in mind:
  - There's a 90-day waiting period before new hires can USE annual leave
  - The plan year runs July 1 through June 30
  - Maximum carry-over to the next plan year is 7 days; excess transfers
    to your sick leave bank

  Note: This is an estimate based on the policy formula. For your official
  balance, please contact Human Resources.

  Source: Annual Leave Policy (HR04), "Accruing Annual Leave"

What you should NOT do with calculations:
  - Never present a calculation as the staff member's official balance
  - Never make assumptions about their start date or years of service
    — always ask
  - Never account for days they've used unless they tell you
  - Never calculate anything that requires data not in the policy
    (e.g., actual payroll records, sick leave balances, FMLA usage)

Respond as a single JSON object with keys:
  "answer": string (plain-language answer, or empty string if refusing)
  "refuse": boolean (true when you cannot answer strictly from retrieval)
  "cited_chunk_ids": array of UUID strings you relied on (subset of provided chunk ids); empty if refusing
Do not include markdown fences. Do not cite chunks you did not use."""


async def generate_answer(
    *,
    question: str,
    chunks: List[RetrievedChunk],
    conversation_context: Optional[List[dict[str, str]]] = None,
) -> tuple[str, bool, List[uuid.UUID], str]:
    """Return (answer_text, refuses, cited_ids, raw_model_text)."""
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

    user_prompt = (
        "QUESTION:\n"
        f"{question}\n\n"
        "RETRIEVAL_BLOCK:\n"
        f"{json.dumps(pack, ensure_ascii=False)}"
    )

    messages: list[dict[str, str]] = []
    if conversation_context:
        for turn in conversation_context:
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_prompt})

    message = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1200,
        system=SYSTEM_PROMPT,
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
