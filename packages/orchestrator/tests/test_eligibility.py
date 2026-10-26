"""Eligibility gate (PRD R-14, ING-2, ING-9, GATE-02, GATE-03). Needs Postgres like the integration tests."""

from __future__ import annotations

import asyncio
import itertools
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.db.models import (
    Chunk,
    Document,
    Eligibility,
    IngestStatus,
    Question,
    SourceFormat,
)
from ask_bpl_orchestrator.db.session import async_session_factory
from ask_bpl_orchestrator.ingest.inventory import (
    InventoryRow,
    apply_inventory_to_db,
    derive_eligibility,
    load_inventory,
    normalize_name,
)
from ask_bpl_orchestrator.main import app
from ask_bpl_orchestrator.services.eligibility import is_retrievable
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk, VectorRetriever

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "sample_corpus" / "AskBPL_Source_Inventory_v0_1.xlsx"
PILOT_DIR = ROOT / "sample_corpus" / "pilot"
client = TestClient(app)

SIGN_IN = {"email": "pilot-demo@bklynlibrary.org", "access_code": "DEMO2026", "attribution_mode": "anonymous"}


# ---------------------------------------------------------------- inventory parsing

def test_unknown_lifecycle_fails_closed() -> None:
    with pytest.raises(ValueError):
        derive_eligibility("Approved-ish", "Pass", None, None)


def test_eligible_requires_reviewer_date_and_the_approved_file_hash() -> None:
    elig, warns = derive_eligibility("Eligible", "Pass", None, None)
    assert elig == Eligibility.authority_pending and warns
    elig, warns = derive_eligibility("Eligible", "Pass", "B. Bilissalou", date(2026, 10, 12))  # no hash (patch 0023)
    assert elig == Eligibility.authority_pending and "approved file hash" in warns[0]
    elig, warns = derive_eligibility("Eligible", "Pass", None, None, "a" * 64)  # hash alone is not a review
    assert elig == Eligibility.authority_pending and "reviewer and date" in warns[0]
    elig, warns = derive_eligibility("Eligible", "Pass", "B. Bilissalou", date(2026, 10, 12), "a" * 64)
    assert elig == Eligibility.eligible and not warns


def test_failed_parse_check_always_blocks() -> None:
    elig, _ = derive_eligibility("Authority pending", "FAIL: scanned", None, None)
    assert elig == Eligibility.blocked
    # even a reviewed "Eligible" row cannot override a failed parse check
    elig, _ = derive_eligibility("Eligible", "FAIL: scanned", "X", date(2026, 1, 1))
    assert elig == Eligibility.blocked


def test_normalize_name_ignores_copy_suffix_but_keeps_policy_number() -> None:
    a = normalize_name("02 - Materials Selection Policy (04.05) (1) (1).pdf")
    b = normalize_name("pilot/02 - Materials Selection Policy (04.05) (1).pdf")
    assert a == b and "(04.05)" in a


def test_shipped_inventory_counts_match_workbook() -> None:
    inv = load_inventory(INVENTORY)
    by = list(inv.values())
    assert len(by) == 30
    assert sum(r.eligibility == Eligibility.eligible for r in by) == 0  # nothing is BPL-confirmed yet
    assert sum(r.eligibility == Eligibility.excluded for r in by) == 1
    assert sum(r.eligibility == Eligibility.blocked for r in by) == 0  # SRC-13 was activated 2026-10-25 (DEC-15)
    assert sum(r.eligibility == Eligibility.authority_pending for r in by) == 29
    assert sum(r.test_index_member for r in by) == 8  # all 8 pilot PDFs, including the validated COI scan
    coi = next(r for r in by if r.source_id == "SRC-13")
    assert coi.eligibility == Eligibility.authority_pending and coi.test_index_member  # answers only as a marked test-index document


def test_every_pilot_pdf_maps_to_an_inventory_row() -> None:
    inv = load_inventory(INVENTORY)
    pdfs = sorted(PILOT_DIR.glob("*.pdf"))
    assert len(pdfs) == 8
    assert all(normalize_name(p.name) in inv for p in pdfs)


def test_loader_downgrades_unreviewed_eligible_row(tmp_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Source Inventory"
    ws.append(["Source ID", "File name", "Parse check", "In current pilot index",
               "Lifecycle status (ING-9)", "Reviewer / date"])
    ws.append(["SRC-X", "x.pdf", "Pass", "Yes", "Eligible", None])
    path = tmp_path / "inv.xlsx"
    wb.save(path)
    row = load_inventory(path)["x"]
    assert row.eligibility == Eligibility.authority_pending
    assert row.test_index_member and row.warnings


# ---------------------------------------------------------------- DB fixtures

async def _add_doc(session, *, eligibility, member=False, status=IngestStatus.indexed, source_path=None,
                   superseded_by=None):
    doc_id, chunk_id = uuid.uuid4(), uuid.uuid4()
    session.add(Document(
        document_id=doc_id, title=f"{eligibility.value} doc", version="t", policy_type="generic_policy",
        source_format=SourceFormat.md, ingest_status=status, eligibility=eligibility,
        test_index_member=member, source_path=source_path or f"t/{doc_id}.md",
        superseded_by_document_id=superseded_by,
        # An eligible document answers only with an approved file (patch 0023).
        source_sha256="a" * 64 if eligibility == Eligibility.eligible else None,
        approved_sha256="a" * 64 if eligibility == Eligibility.eligible else None,
    ))
    await session.flush()
    session.add(Chunk(chunk_id=chunk_id, document_id=doc_id, ordinal=0,
                      text="Staff must record gifts over $500.", token_count=7))
    return doc_id, chunk_id


async def _cleanup(doc_ids, request_ids=()) -> None:
    async with async_session_factory() as s:
        for r in request_ids:
            await s.execute(delete(Question).where(Question.request_id == r))
        await s.execute(delete(Chunk).where(Chunk.document_id.in_(list(doc_ids))))
        await s.execute(delete(Document).where(Document.document_id.in_(list(doc_ids))))
        await s.commit()


# ---------------------------------------------------------------- GATE-03 retrieval

@pytest.mark.asyncio
@pytest.mark.parametrize("allow_test_index", [True, False])
async def test_retrieval_truth_table_matches_python_mirror(allow_test_index: bool) -> None:
    """SQL filter and is_retrievable agree for every eligibility x membership combination."""
    cfg = get_settings().model_copy(update={"allow_test_index": allow_test_index})
    created: dict[uuid.UUID, uuid.UUID] = {}
    async with async_session_factory() as s:
        for elig, member in itertools.product(Eligibility, (False, True)):
            doc_id, chunk_id = await _add_doc(s, eligibility=elig, member=member)
            created[chunk_id] = doc_id
        await s.commit()
    try:
        retriever = VectorRetriever()
        retriever.settings = cfg
        async with async_session_factory() as s:
            got = {c.chunk_id for c in await retriever._hydrate_ordered(s, {c: 0.9 for c in created})}
            for chunk_id, doc_id in created.items():
                doc = await s.get(Document, doc_id)
                assert (chunk_id in got) == is_retrievable(doc, cfg), (doc.eligibility, doc.test_index_member)
        allowed = {Eligibility.eligible} | ({Eligibility.authority_pending} if allow_test_index else set())
        async with async_session_factory() as s:
            for chunk_id in got:
                doc = await s.get(Document, created[chunk_id])
                assert doc.eligibility in allowed
                if doc.eligibility == Eligibility.authority_pending:
                    assert doc.test_index_member  # pending docs need the OD-11 marker
        # blocked / excluded / superseded NEVER appear, whatever the flags
        async with async_session_factory() as s:
            for chunk_id in got:
                doc = await s.get(Document, created[chunk_id])
                assert doc.eligibility not in {Eligibility.blocked, Eligibility.excluded, Eligibility.superseded}
    finally:
        await _cleanup(created.values())


@pytest.mark.asyncio
async def test_not_indexed_and_superseded_rows_are_never_retrieved() -> None:
    async with async_session_factory() as s:
        _, c_failed = await _add_doc(s, eligibility=Eligibility.eligible, status=IngestStatus.failed)
        d_new, _c = await _add_doc(s, eligibility=Eligibility.eligible)
        d_old, c_old = await _add_doc(s, eligibility=Eligibility.eligible, superseded_by=d_new)
        await s.commit()
    try:
        async with async_session_factory() as s:
            out = await VectorRetriever()._hydrate_ordered(s, {c_failed: 0.9, c_old: 0.9})
        assert out == []
    finally:
        async with async_session_factory() as s:
            ids = (await s.execute(select(Chunk.document_id).where(Chunk.chunk_id.in_([c_failed, c_old, _c])))).scalars().all()
        await _cleanup(ids)


# ---------------------------------------------------------------- GATE-03 end to end

def _ask(token: str, question: str = "Who has to record gifts over $500?"):
    return client.post("/questions/ask", headers={"Authorization": f"Bearer {token}"}, json={"question": question})


def _token() -> str:
    r = client.post("/auth/sign-in", json=SIGN_IN)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_end_to_end_only_answerable_chunks_reach_model_and_citations() -> None:
    """Instrumented: record what the generator is handed, then compare with eligibility."""
    ids: dict[Eligibility, tuple[uuid.UUID, uuid.UUID]] = {}

    async def _seed() -> None:
        async with async_session_factory() as s:
            for elig in Eligibility:
                ids[elig] = await _add_doc(s, eligibility=elig, member=(elig == Eligibility.authority_pending))
            await s.commit()

    asyncio.run(_seed())
    seen: dict[str, list] = {}

    async def fake_generate(*, question, chunks, conversation_context=None, routing=None):
        seen["chunks"] = [c.chunk_id for c in chunks]
        return "Staff record gifts over $500.", False, list(seen["chunks"]), "{}"

    scores = {chunk: 0.95 for (_, chunk) in ids.values()}
    try:
        with (
            patch.object(VectorRetriever, "_pinecone_scores", new_callable=AsyncMock, return_value=scores),
            patch("ask_bpl_orchestrator.services.ask_service.generation.generate_answer", side_effect=fake_generate),
        ):
            r = _ask(_token())
        assert r.status_code == 200, r.text
        body = r.json()
        allowed = {ids[Eligibility.eligible][1], ids[Eligibility.authority_pending][1]}
        forbidden = {ids[e][1] for e in (Eligibility.blocked, Eligibility.excluded, Eligibility.superseded)}
        assert set(seen["chunks"]) == allowed
        assert not (set(seen["chunks"]) & forbidden)
        cited = {c["chunk_id"] for c in body["citations"]}
        assert cited == {str(x) for x in allowed}
        assert not (cited & {str(x) for x in forbidden})
        # the test-index source is labelled, the eligible one is not
        flags = {c["chunk_id"]: c["test_index"] for c in body["citations"]}
        assert flags[str(ids[Eligibility.authority_pending][1])] is True
        assert flags[str(ids[Eligibility.eligible][1])] is False
        assert "Test index" in body["index_label"]
    finally:
        asyncio.run(_cleanup([d for d, _ in ids.values()], [uuid.UUID(body["request_id"])] if "body" in dir() else []))


def test_only_blocked_source_yields_refusal_not_answer() -> None:
    ids: list = []

    async def _seed() -> None:
        async with async_session_factory() as s:
            ids.append(await _add_doc(s, eligibility=Eligibility.blocked))
            await s.commit()

    asyncio.run(_seed())
    called = AsyncMock()
    try:
        with (
            patch.object(VectorRetriever, "_pinecone_scores", new_callable=AsyncMock, return_value={ids[0][1]: 0.99}),
            patch("ask_bpl_orchestrator.services.ask_service.generation.generate_answer", called),
        ):
            r = _ask(_token())
        assert r.status_code == 200
        body = r.json()
        assert body["type"] != "answer" and not body["citations"]
        called.assert_not_called()  # nothing grounded -> model never sees blocked text
        asyncio.run(_cleanup([ids[0][0]], [uuid.UUID(body["request_id"])]))
    finally:
        asyncio.run(_cleanup([ids[0][0]]))


def test_citation_to_ineligible_document_is_rejected_even_if_retrieval_leaks() -> None:
    """Second line of defence: a leaked chunk cited by the model becomes a refusal."""
    ids: list = []

    async def _seed() -> None:
        async with async_session_factory() as s:
            ids.append(await _add_doc(s, eligibility=Eligibility.blocked))
            await s.commit()

    asyncio.run(_seed())
    doc_id, chunk_id = ids[0]
    leaked = RetrievedChunk(chunk_id=chunk_id, score=0.95, document_id=doc_id, title="x",
                            policy_type="generic_policy", version="t", section_heading=None, text="t")
    req = None
    try:
        with (
            patch.object(VectorRetriever, "query", new_callable=AsyncMock, return_value=[leaked]),
            patch("ask_bpl_orchestrator.services.ask_service.generation.generate_answer",
                  new_callable=AsyncMock, return_value=("Answer.", False, [chunk_id], "{}")),
        ):
            r = _ask(_token())
        body = r.json()
        req = uuid.UUID(body["request_id"])
        assert body["type"] == "refusal_citation_invalid"
        assert body["citations"] == []
    finally:
        asyncio.run(_cleanup([doc_id], [req] if req else []))


def test_document_viewer_hides_non_answerable_documents() -> None:
    ids: dict = {}

    async def _seed() -> None:
        async with async_session_factory() as s:
            ids["blocked"] = await _add_doc(s, eligibility=Eligibility.blocked)
            ids["pending"] = await _add_doc(s, eligibility=Eligibility.authority_pending, member=True)
            await s.commit()

    asyncio.run(_seed())
    try:
        h = {"Authorization": f"Bearer {_token()}"}
        assert client.get(f"/documents/{ids['blocked'][0]}/text", headers=h).status_code == 404
        ok = client.get(f"/documents/{ids['pending'][0]}/text", headers=h)
        assert ok.status_code == 200 and ok.json()["test_index"] is True
    finally:
        asyncio.run(_cleanup([d for d, _ in ids.values()]))


# ---------------------------------------------------------------- applying the inventory

def _synthetic_inventory(*rows: InventoryRow) -> dict:
    """Test-only inventory with unique names/IDs so tests never collide with real documents."""
    return {r.key: r for r in rows}


def _row(source_id: str, file_name: str, elig: Eligibility, member: bool) -> InventoryRow:
    return InventoryRow(source_id=source_id, file_name=file_name, eligibility=elig, test_index_member=member)


@pytest.mark.asyncio
async def test_apply_inventory_sets_dispositions_and_denies_unlisted() -> None:
    tag = uuid.uuid4().hex[:8]
    inv = _synthetic_inventory(
        _row(f"SRC-T{tag}-A", f"zz-{tag} Blocked Policy (99.01).pdf", Eligibility.blocked, False),
        _row(f"SRC-T{tag}-B", f"zz-{tag} Pending Policy (99.02).pdf", Eligibility.authority_pending, True),
    )
    async with async_session_factory() as s:
        blocked, _ = await _add_doc(s, eligibility=Eligibility.authority_pending, member=True,
                                    source_path=f"zz-{tag} Blocked Policy (99.01) (1).pdf")
        pending, _ = await _add_doc(s, eligibility=Eligibility.authority_pending, member=False,
                                    source_path=f"zz-{tag} Pending Policy (99.02).pdf")
        stray, _ = await _add_doc(s, eligibility=Eligibility.eligible, member=True, source_path=f"notes/{tag}-stray.md")
        await s.commit()
    ids = [blocked, pending, stray]
    try:
        async with async_session_factory() as s:
            lines = await apply_inventory_to_db(s, inv, scope=ids)
        async with async_session_factory() as s:
            d_blocked, d_pending, d_stray = [await s.get(Document, i) for i in ids]
        assert (d_blocked.eligibility, d_blocked.source_id, d_blocked.test_index_member) == (
            Eligibility.blocked, f"SRC-T{tag}-A", False)
        assert (d_pending.eligibility, d_pending.source_id, d_pending.test_index_member) == (
            Eligibility.authority_pending, f"SRC-T{tag}-B", True)
        # a stored document that is not in the inventory is NOT answerable
        assert d_stray.eligibility == Eligibility.authority_pending and not d_stray.test_index_member
        assert not is_retrievable(d_stray, get_settings().model_copy(update={"allow_test_index": True}))
        assert any(l.startswith(f"unlisted:notes/{tag}-stray.md") for l in lines)
    finally:
        await _cleanup(ids)


@pytest.mark.asyncio
async def test_reingest_preserves_eligibility(tmp_path: Path) -> None:
    from ask_bpl_orchestrator.ingest import service

    src = tmp_path / "policy.md"
    src.write_text("# Gifts\n\nStaff must record gifts over $500.\n", encoding="utf-8")
    doc_id = service._document_uuid("policy.md")
    kwargs = dict(absolute_path=src, corpus_root=tmp_path, policy_slug="generic_policy",
                  title="Policy", version_label="v1")
    try:
        with (
            # hermetic: no tokenizer download, no embedding call, no Pinecone
            patch.object(service, "split_text_with_sections",
                         return_value=[SimpleNamespace(text="Staff must record gifts over $500.", section_heading="Gifts")]),
            patch.object(service, "embed_snippet", new_callable=AsyncMock, return_value=[0.0]),
            patch.object(service, "pinecone_bulk_upsert"),
            patch.object(service, "pinecone_bulk_delete"),
        ):
            await service.ingest_file(**kwargs)  # brand-new, no inventory row -> default deny
            async with async_session_factory() as s:
                d = await s.get(Document, doc_id)
                assert d.eligibility == Eligibility.authority_pending and not d.test_index_member
                d.eligibility, d.test_index_member = Eligibility.eligible, False
                await s.commit()
            await service.ingest_file(**kwargs)  # re-ingest must not reset the disposition
            async with async_session_factory() as s:
                assert (await s.get(Document, doc_id)).eligibility == Eligibility.eligible
    finally:
        await _cleanup([doc_id])


@pytest.mark.asyncio
async def test_batch_ingest_passes_every_manifest_entry_with_its_inventory_row_and_the_scan_with_its_record() -> None:
    """Since SRC-13's activation (DEC-15) nothing in the shipped manifest is blocked. Refusal of blocked, excluded and
    superseded rows is pinned against a temporary workbook in test_corpus_report.py. The scanned COI file is only
    ingested because its committed validation record verifies against the PDF; a stale record fails here."""
    from ask_bpl_orchestrator.ingest import batch

    manifest = ROOT / "sample_corpus" / "corpus_manifest_pilot.yaml"
    calls: list = []

    async def fake_ingest(**kw):
        calls.append(kw)

    with patch.object(batch, "ingest_file", side_effect=fake_ingest):
        lines = await batch.ingest_manifest(manifest, INVENTORY)

    assert [l for l in lines if l.startswith(("refused:", "failed:"))] == []
    assert len(calls) == 8  # every manifest entry
    assert all(c["inventory_row"] is not None and c["inventory_row"].test_index_member for c in calls)
    validated = [c for c in calls if c["validated_extraction"] is not None]
    assert len(validated) == 1 and "Conflict of Interest" in str(validated[0]["absolute_path"])
    assert validated[0]["inventory_row"].source_id == "SRC-13"
    assert sum(l.endswith(":validated") for l in lines) == 1


# ---------------------------------------------------------------- 0003a: fresh-index delete, empty DB

def test_bulk_delete_tolerates_missing_namespace_on_new_index() -> None:
    from unittest.mock import MagicMock

    from ask_bpl_orchestrator.ingest import service

    class NotFound(Exception):
        pass

    idx = MagicMock()
    idx.delete.side_effect = NotFound("Namespace not found")
    cfg = MagicMock(pinecone_api_key="k")
    with patch.object(service, "get_pinecone_index", return_value=idx), patch.object(service, "get_settings", return_value=cfg):
        service.pinecone_bulk_delete(["a", "b"])  # must not raise
    idx.delete.side_effect = NotFound("Invalid API key")
    with patch.object(service, "get_pinecone_index", return_value=idx), patch.object(service, "get_settings", return_value=cfg):
        with pytest.raises(NotFound):  # other errors still surface
            service.pinecone_bulk_delete(["a"])


@pytest.mark.asyncio
async def test_apply_inventory_reports_empty_database() -> None:
    from unittest.mock import MagicMock

    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    lines = await apply_inventory_to_db(db, load_inventory(INVENTORY))
    assert lines[0] == "found:0:stored documents"
    assert any(l.startswith("error:no stored documents") for l in lines)


@pytest.mark.asyncio
async def test_apply_inventory_refuses_duplicate_documents_and_changes_nothing() -> None:
    """Same policy ingested under two source paths (e.g. 'x.pdf' and 'pilot/x.pdf')."""
    tag = uuid.uuid4().hex[:8]
    name = f"zz-{tag} Annual Leave (99.03).pdf"
    sid = f"SRC-T{tag}-D"
    inv = _synthetic_inventory(_row(sid, name, Eligibility.authority_pending, True))
    async with async_session_factory() as s:
        a, _ = await _add_doc(s, eligibility=Eligibility.authority_pending, member=True, source_path=name)
        b, _ = await _add_doc(s, eligibility=Eligibility.authority_pending, member=True, source_path=f"pilot/{name}")
        await s.commit()
    try:
        async with async_session_factory() as s:
            lines = await apply_inventory_to_db(s, inv, scope=[a, b])
        assert any(l.startswith(f"error:duplicate:{sid}:2 stored documents") for l in lines)
        assert any("nothing was changed" in l for l in lines)
        async with async_session_factory() as s:
            for i in (a, b):
                d = await s.get(Document, i)
                assert d.source_id is None  # untouched, no constraint violation either
    finally:
        await _cleanup([a, b])
