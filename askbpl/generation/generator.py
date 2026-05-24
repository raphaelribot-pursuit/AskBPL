"""Claude generation with closed-corpus constraint (TRD-GEN-1, TRD-GEN-2)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import anthropic
import yaml

from generation.system_prompt import get_system_prompt
from ingestion.policy_metadata import PROJECT_ROOT
from retrieval.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

GENERATION_PATH = PROJECT_ROOT / "config" / "generation.yaml"


@dataclass(frozen=True)
class GenerationResult:
    """Parsed model output."""

    answer: str
    refuses: bool
    cited_vector_ids: List[str]
    raw_text: str


def load_generation_config(path: Path = GENERATION_PATH) -> dict:
    """Load pinned generation model settings (TRD-GEN-1)."""
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def generate_answer(
    *,
    question: str,
    chunks: List[RetrievedChunk],
    routing_owners: Optional[List[str]] = None,
    config: dict | None = None,
) -> GenerationResult:
    """Call Claude with retrieval context (TRD-GEN-1, TRD-GEN-2)."""
    cfg = config or load_generation_config()
    client = anthropic.Anthropic()

    pack = [
        {
            "vector_id": c.vector_id,
            "document_title": c.source_document,
            "version": c.document_version,
            "policy_type": c.policy_type,
            "section_heading": c.section,
            "text": c.text,
        }
        for c in chunks
    ]

    routing_block = {"owning_teams": routing_owners or []}

    user_prompt = (
        "QUESTION:\n"
        f"{question}\n\n"
        "RETRIEVAL_BLOCK:\n"
        f"{json.dumps(pack, ensure_ascii=False)}\n\n"
        "ROUTING_BLOCK:\n"
        f"{json.dumps(routing_block, ensure_ascii=False)}"
    )

    message = client.messages.create(
        model=str(cfg["model"]),
        max_tokens=int(cfg["max_tokens"]),
        system=get_system_prompt(),
        messages=[{"role": "user", "content": user_prompt}],
    )

    text_parts: List[str] = []
    for block in message.content:
        if block.type == "text":
            text_parts.append(block.text)
    raw_text = "\n".join(text_parts).strip()
    data = _parse_json_best_effort(raw_text)

    answer = str(data.get("answer") or "").strip()
    refuses = bool(data.get("refuse"))
    cited_raw = data.get("cited_vector_ids") or []
    cited_ids = [str(cid) for cid in cited_raw if cid]

    return GenerationResult(
        answer=answer,
        refuses=refuses,
        cited_vector_ids=cited_ids,
        raw_text=raw_text,
    )


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
            logger.warning("model JSON extract failed; refusing")
    else:
        logger.warning("model returned non-JSON; refusing")
    return {"answer": "", "refuse": True, "cited_vector_ids": []}
