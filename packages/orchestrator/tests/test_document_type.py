"""ING-10, patch 0060: keep policy, procedure and guidance distinct.

The workbook's "Source type" is stored on each document (askbpl-apply-inventory), carried on every retrieved passage and
shown to the model, whose prompt says a procedure or guidance is never called a policy. No network.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from ask_bpl_orchestrator.db.models import Document
from ask_bpl_orchestrator.ingest.inventory import DOCUMENT_TYPES, apply_row, load_inventory, normalize_document_type
from ask_bpl_orchestrator.services import generation
from ask_bpl_orchestrator.services.generation import SYSTEM_PROMPT
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk

INVENTORY = Path(__file__).resolve().parents[1] / "sample_corpus" / "AskBPL_Source_Inventory_v0_1.xlsx"


@pytest.mark.parametrize(
    "raw,want",
    [
        ("Policy", "policy"),
        ("Policy (governance)", "policy"),
        ("Policy (draft indicators)", "policy"),
        ("Procedure", "procedure"),
        ("Procedures", "procedure"),
        ("Supporting guidance", "guidance"),
        ("Guidelines", "guidance"),
        ("Design deck", "design_deck"),
        ("Evaluation material", "evaluation_material"),
        ("", None),
        (None, None),
        ("Memo", None),
    ],
)
def test_the_workbook_source_type_maps_to_one_document_type(raw, want) -> None:
    assert normalize_document_type(raw) == want
    assert want is None or want in DOCUMENT_TYPES


def test_the_shipped_workbook_types_every_row_and_marks_the_procedure() -> None:
    rows = {r.source_id: r for r in load_inventory(INVENTORY).values()}
    assert rows["SRC-08"].document_type == "procedure"  # Collection Maintenance Procedures
    assert rows["SRC-02"].document_type == "policy"  # Policy (governance)
    assert all(r.document_type in DOCUMENT_TYPES for r in rows.values()), {s: r.document_type for s, r in rows.items()}
    assert not [w for r in rows.values() for w in r.warnings if "Source type" in w]


def test_apply_row_records_the_type_on_the_document() -> None:
    row = next(r for r in load_inventory(INVENTORY).values() if r.source_id == "SRC-08")
    doc = Document(title="x", version="v", policy_type="collection_maintenance")
    apply_row(doc, row)
    assert doc.document_type == "procedure"


def _chunk(doc_type):
    return RetrievedChunk(chunk_id=uuid.uuid4(), score=0.6, document_id=uuid.uuid4(), title="Collection Maintenance Procedures",
                          policy_type="collection_maintenance", version="v", section_heading=None, text="Staff may not take weeded items.",
                          document_type=doc_type)


@pytest.mark.asyncio
@pytest.mark.parametrize("doc_type,shown", [("procedure", "procedure"), ("policy", "policy"), (None, "not recorded")])
async def test_the_model_sees_each_passages_document_type(doc_type, shown) -> None:
    reply = json.dumps({"answer": "No.", "refuse": False, "cited_chunk_ids": ["C1"], "routing_team": None})
    create = AsyncMock(return_value=SimpleNamespace(content=[SimpleNamespace(type="text", text=reply)]))
    with patch.object(generation.anthropic, "AsyncAnthropic", return_value=SimpleNamespace(messages=SimpleNamespace(create=create))):
        await generation.generate_answer(question="Can staff keep weeded books?", chunks=[_chunk(doc_type)])
    body = create.call_args.kwargs["messages"][0]["content"]
    pack = json.loads(body.split("RETRIEVAL_BLOCK:\n", 1)[1].split("\n\nReply with", 1)[0])
    assert pack[0]["document_type"] == shown


def test_the_prompt_says_a_procedure_is_never_called_a_policy() -> None:
    flat = " ".join(SYSTEM_PROMPT.split())
    assert "PROCEDURES ARE NOT POLICIES" in SYSTEM_PROMPT
    assert 'whose document_type is "procedure" or "guidance", name it as that' in flat
    assert "never call it a policy" in flat
