"""Claude generation with closed-corpus constraint (TRD-GEN)."""

from __future__ import annotations

import json
import uuid
from typing import List, Optional

import anthropic

from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk


SYSTEM_PROMPT = """You are Ask BPL, an internal Brooklyn Public Library assistant.
You answer ONLY using the RETRIEVAL_BLOCK JSON provided by the user (curated policy excerpts).
If the retrieval does not support a confident answer, you must refuse briefly in plain language without inventing facts.
Use clear, accessible language for diverse staff roles; no legal advice; no internal engineering jargon.
Respond as a single JSON object with keys:
  "answer": string (plain-language answer, or empty string if refusing)
  "refuse": boolean (true when you cannot answer strictly from retrieval)
  "cited_chunk_ids": array of UUID strings you relied on (subset of provided chunk ids); empty if refusing
Do not include markdown fences. Do not cite chunks you did not use."""


async def generate_answer(*, question: str, chunks: List[RetrievedChunk]) -> tuple[str, bool, List[uuid.UUID], str]:
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

    message = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1200,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
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
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {"answer": "", "refuse": True, "cited_chunk_ids": []}
