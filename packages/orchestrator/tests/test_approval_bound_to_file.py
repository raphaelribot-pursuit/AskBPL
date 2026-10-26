"""Patch 0023: an approval covers the file that was reviewed, not whatever file later has the same name
(PRD ING-2, ING-5, GATE-02, R-14; Handoff 14 finding 3, Handoff 16 option 0022-B).

Before this patch, re-ingesting a changed policy file left the document `eligible`: the approval of the old text
silently covered the new text. These tests exist to stop that, and to stop the new rule from (a) being bypassed by a
re-ingest, (b) being granted by ingest rather than by the workbook, (c) hiding behind an unreadable or invalid hash,
or (d) breaking the marked test index, which has no approval to bind.
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import re
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import AsyncMock, patch

import openpyxl
import pytest
from sqlalchemy import delete, select, text

from ask_bpl_orchestrator import corpus_report as cr
from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.db.models import Chunk, Document, Eligibility, ExtractionStatus, IngestStatus, SourceFormat
from ask_bpl_orchestrator.db.session import async_session_factory
from ask_bpl_orchestrator.ingest.inventory import (
    InventoryRow, apply_inventory_to_db, derive_eligibility, load_inventory, parse_approved_hash,
)
from ask_bpl_orchestrator.services.eligibility import is_retrievable, retrievable_clause

ORCH = Path(__file__).resolve().parents[1]
A, B, C = "a" * 64, "b" * 64, "c" * 64
ON = get_settings().model_copy(update={"allow_test_index": True})
OFF = get_settings().model_copy(update={"allow_test_index": False})


# ------------------------------------------------------------------------------------------------ hash parsing
@pytest.mark.parametrize("raw,expected", [
    (A, A), (A.upper(), A), (f"  {A}  ", A), (f"sha256:{A}", A), (f"SHA256:{A.upper()}", A),
    ("ab cd " + "e" * 60, "abcd" + "e" * 60),  # spreadsheets and chat clients wrap long strings
])
def test_a_valid_hash_is_normalised(raw: str, expected: str) -> None:
    assert parse_approved_hash(raw) == (expected, None)


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_an_empty_cell_is_not_a_warning(raw: Optional[str]) -> None:
    assert parse_approved_hash(raw) == (None, None)


@pytest.mark.parametrize("raw", ["a" * 63, "a" * 65, "g" * 64, "not a hash", "0x" + "a" * 62, "a" * 32, "12345"])
def test_an_invalid_hash_is_ignored_with_a_warning_never_guessed(raw: str) -> None:
    got, warning = parse_approved_hash(raw)
    assert got is None and warning and "64 hexadecimal" in warning


# ------------------------------------------------------------------------------------------------ the workbook
HEADER = ["Source ID", "File name", "Parse check", "In current pilot index", "Lifecycle status (ING-9)", "Reviewer / date"]


def workbook(path: Path, rows: list[list[Any]], *, with_hash_column: bool = True) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Source Inventory"
    ws.append(HEADER + (["Approved SHA-256"] if with_hash_column else []))
    for r in rows:
        ws.append(r if with_hash_column else r[:6])
    wb.save(path)
    return path


GOOD = ["SRC-1", "a.pdf", "Pass", "No", "Eligible", "B. Bilissalou / 2026-10-12"]


def test_a_workbook_without_the_column_still_loads_and_nothing_is_eligible(tmp_path: Path) -> None:
    inv = load_inventory(workbook(tmp_path / "old.xlsx", [GOOD + [None]], with_hash_column=False))
    row = inv["a"]
    assert row.eligibility == Eligibility.authority_pending and row.approved_sha256 is None
    assert any("approved file hash" in w for w in row.warnings)


def test_a_reviewed_row_with_a_valid_hash_is_eligible_and_carries_the_hash(tmp_path: Path) -> None:
    row = load_inventory(workbook(tmp_path / "w.xlsx", [GOOD + [A.upper()]]))["a"]
    assert row.eligibility == Eligibility.eligible and row.approved_sha256 == A and row.warnings == []


def test_an_invalid_hash_makes_the_row_pending_and_says_two_things(tmp_path: Path) -> None:
    row = load_inventory(workbook(tmp_path / "w.xlsx", [GOOD + ["a" * 63]]))["a"]
    assert row.eligibility == Eligibility.authority_pending and row.approved_sha256 is None
    assert any("64 hexadecimal" in w for w in row.warnings) and any("approved file hash" in w for w in row.warnings)


def test_a_hash_without_a_reviewer_does_not_make_a_row_eligible(tmp_path: Path) -> None:
    row = load_inventory(workbook(tmp_path / "w.xlsx", [["SRC-1", "a.pdf", "Pass", "No", "Eligible", None, A]]))["a"]
    assert row.eligibility == Eligibility.authority_pending and row.approved_sha256 is None


@pytest.mark.parametrize("life", ["Authority pending", "Excluded", "Superseded by SRC-9"])
def test_a_hash_on_a_row_that_is_not_eligible_is_not_carried(tmp_path: Path, life: str) -> None:
    row = load_inventory(workbook(tmp_path / "w.xlsx", [["SRC-1", "a.pdf", "Pass", "Yes", life, "B. B / 2026-10-12", A]]))["a"]
    assert row.approved_sha256 is None


def test_a_failed_parse_check_still_blocks_whatever_the_hash_says() -> None:
    elig, _ = derive_eligibility("Eligible", "FAIL: scanned", "X", date(2026, 1, 1), A)
    assert elig == Eligibility.blocked


def test_the_marked_test_index_needs_no_hash(tmp_path: Path) -> None:
    row = load_inventory(workbook(tmp_path / "w.xlsx", [["SRC-1", "a.pdf", "Pass", "Yes", "Authority pending", None, None]]))["a"]
    assert row.eligibility == Eligibility.authority_pending and row.test_index_member and row.warnings == []


# ------------------------------------------------------------------------------------------------ the rule (python mirror)
HASHES = [None, A, B]


@pytest.mark.parametrize("approved,stored", list(itertools.product(HASHES, HASHES)))
def test_an_eligible_document_answers_only_when_both_hashes_exist_and_match(approved: Optional[str], stored: Optional[str]) -> None:
    doc = SimpleNamespace(ingest_status=IngestStatus.indexed, superseded_by_document_id=None, extraction_status="standard",
                          eligibility=Eligibility.eligible, test_index_member=False, approved_sha256=approved, source_sha256=stored)
    assert is_retrievable(doc, ON) is (approved is not None and approved == stored)


def test_a_stand_in_without_the_columns_is_never_an_approved_document() -> None:
    doc = SimpleNamespace(ingest_status=IngestStatus.indexed, superseded_by_document_id=None, extraction_status="standard",
                          eligibility=Eligibility.eligible, test_index_member=False)
    assert is_retrievable(doc, ON) is False


@pytest.mark.parametrize("approved,stored", list(itertools.product(HASHES, HASHES)))
def test_the_test_index_is_unaffected_by_hashes(approved: Optional[str], stored: Optional[str]) -> None:
    doc = SimpleNamespace(ingest_status=IngestStatus.indexed, superseded_by_document_id=None, extraction_status="standard",
                          eligibility=Eligibility.authority_pending, test_index_member=True, approved_sha256=approved, source_sha256=stored)
    assert is_retrievable(doc, ON) is True and is_retrievable(doc, OFF) is False


@pytest.mark.parametrize("elig", [Eligibility.blocked, Eligibility.excluded, Eligibility.superseded])
def test_a_matching_hash_cannot_rescue_a_document_the_workbook_keeps_out(elig: Eligibility) -> None:
    doc = SimpleNamespace(ingest_status=IngestStatus.indexed, superseded_by_document_id=None, extraction_status="standard",
                          eligibility=elig, test_index_member=True, approved_sha256=A, source_sha256=A)
    assert is_retrievable(doc, ON) is False


def test_a_matching_hash_does_not_override_review_required_or_supersession_or_a_failed_ingest() -> None:
    base = dict(ingest_status=IngestStatus.indexed, superseded_by_document_id=None, extraction_status="standard",
                eligibility=Eligibility.eligible, test_index_member=False, approved_sha256=A, source_sha256=A)
    assert is_retrievable(SimpleNamespace(**base), ON) is True
    assert is_retrievable(SimpleNamespace(**{**base, "extraction_status": ExtractionStatus.review_required}), ON) is False
    assert is_retrievable(SimpleNamespace(**{**base, "superseded_by_document_id": uuid.uuid4()}), ON) is False
    assert is_retrievable(SimpleNamespace(**{**base, "ingest_status": IngestStatus.failed}), ON) is False


# ------------------------------------------------------------------------------------------------ database helpers
async def _make(*, elig: Eligibility = Eligibility.eligible, source: Optional[str] = A, approved: Optional[str] = A,
                member: bool = False, path: Optional[str] = None, sid: Optional[str] = None, chunks: int = 1) -> uuid.UUID:
    did = uuid.uuid4()
    async with async_session_factory() as s:
        s.add(Document(
            document_id=did, title="t", version="t", policy_type="generic_policy", source_format=SourceFormat.md,
            ingest_status=IngestStatus.indexed, eligibility=elig, test_index_member=member,
            source_path=path or f"zz{did.hex[:8]}.pdf", source_id=sid, source_sha256=source, approved_sha256=approved,
        ))
        await s.flush()
        for i in range(chunks):
            s.add(Chunk(chunk_id=uuid.uuid4(), document_id=did, ordinal=i, text="Staff must record gifts.", token_count=4))
        await s.commit()
    return did


async def _drop(ids: list[uuid.UUID]) -> None:
    async with async_session_factory() as s:
        await s.execute(delete(Chunk).where(Chunk.document_id.in_(ids)))
        await s.execute(delete(Document).where(Document.document_id.in_(ids)))
        await s.commit()


async def _answerable(ids: list[uuid.UUID], settings=ON) -> set[uuid.UUID]:
    async with async_session_factory() as s:
        return set((await s.execute(select(Document.document_id).where(Document.document_id.in_(ids)).where(retrievable_clause(settings)))).scalars().all())


async def _load(did: uuid.UUID) -> Document:
    async with async_session_factory() as s:
        d = await s.get(Document, did)
        s.expunge(d)
        return d


# ------------------------------------------------------------------------------------------------ the rule (SQL)
@pytest.mark.parametrize("approved,stored", list(itertools.product(HASHES, HASHES)))
def test_sql_and_python_agree_on_every_hash_combination(approved: Optional[str], stored: Optional[str]) -> None:
    async def go() -> None:
        did = await _make(source=stored, approved=approved)
        try:
            doc = await _load(did)
            assert (did in await _answerable([did])) is is_retrievable(doc, ON) is (approved is not None and approved == stored)
        finally:
            await _drop([did])

    asyncio.run(go())


@pytest.mark.parametrize("elig", list(Eligibility))
@pytest.mark.parametrize("member", [False, True])
@pytest.mark.parametrize("approved,stored", [(None, None), (A, A), (A, B)])
@pytest.mark.parametrize("allow", [False, True])
def test_sql_and_python_agree_across_eligibility_membership_hashes_and_the_test_index_setting(elig, member, approved, stored, allow) -> None:
    cfg = get_settings().model_copy(update={"allow_test_index": allow})

    async def go() -> None:
        did = await _make(elig=elig, member=member, source=stored, approved=approved)
        try:
            assert (did in await _answerable([did], cfg)) is is_retrievable(await _load(did), cfg)
        finally:
            await _drop([did])

    asyncio.run(go())


def test_the_new_columns_exist_and_are_nullable() -> None:
    async def go() -> dict[str, str]:
        async with async_session_factory() as s:
            rows = (await s.execute(text(
                "SELECT column_name, is_nullable, character_maximum_length FROM information_schema.columns "
                "WHERE table_name = 'documents' AND column_name IN ('source_sha256', 'approved_sha256')"))).all()
            return {r[0]: f"{r[1]}/{r[2]}" for r in rows}

    assert asyncio.run(go()) == {"source_sha256": "YES/64", "approved_sha256": "YES/64"}


# ------------------------------------------------------------------------------------------------ ingest records the file hash
@pytest.mark.asyncio
async def test_ingest_records_the_hash_and_a_changed_file_stops_an_approved_document_answering(tmp_path: Path) -> None:
    """The point of the patch: approve, change the file, re-ingest: no longer answers. Restore the file: answers again."""
    from ask_bpl_orchestrator.ingest import service

    src = tmp_path / "policy.md"
    original = "# Gifts\n\nStaff must record gifts over $500.\n"
    src.write_text(original, encoding="utf-8")
    h_original = hashlib.sha256(original.encode()).hexdigest()
    doc_id = service._document_uuid("policy.md")
    kwargs = dict(absolute_path=src, corpus_root=tmp_path, policy_slug="generic_policy", title="Policy", version_label="v1")
    try:
        with (
            patch.object(service, "split_text_with_sections",
                         return_value=[SimpleNamespace(text="Staff must record gifts over $500.", section_heading="Gifts")]),
            patch.object(service, "embed_snippet", new_callable=AsyncMock, return_value=[0.0]),
            patch.object(service, "pinecone_bulk_upsert"),
            patch.object(service, "pinecone_bulk_delete"),
        ):
            await service.ingest_file(**kwargs)
            d = await _load(doc_id)
            assert d.source_sha256 == h_original and d.approved_sha256 is None  # ingest records, it never approves
            assert doc_id not in await _answerable([doc_id])

            async with async_session_factory() as s:  # the workbook approval, as apply-inventory records it
                row = await s.get(Document, doc_id)
                row.eligibility, row.approved_sha256, row.test_index_member = Eligibility.eligible, h_original, False
                await s.commit()
            assert doc_id in await _answerable([doc_id])

            src.write_text(original + "\nGifts over $50 must now be recorded.\n", encoding="utf-8")  # the file changes
            await service.ingest_file(**kwargs)
            d = await _load(doc_id)
            assert d.eligibility == Eligibility.eligible and d.approved_sha256 == h_original  # approval untouched...
            assert d.source_sha256 != h_original and doc_id not in await _answerable([doc_id])  # ...but it no longer covers the file

            src.write_text(original, encoding="utf-8")  # the reviewed file comes back
            await service.ingest_file(**kwargs)
            assert (await _load(doc_id)).source_sha256 == h_original and doc_id in await _answerable([doc_id])
    finally:
        await _drop([doc_id])


@pytest.mark.asyncio
async def test_a_failed_ingest_does_not_leave_an_approved_document_answerable(tmp_path: Path) -> None:
    from ask_bpl_orchestrator.ingest import service

    src = tmp_path / "p.md"
    src.write_text("# T\n\nText.\n", encoding="utf-8")
    doc_id = service._document_uuid("p.md")
    did_kwargs = dict(absolute_path=src, corpus_root=tmp_path, policy_slug="generic_policy", title="P", version_label="v1")
    try:
        with (
            patch.object(service, "split_text_with_sections", return_value=[SimpleNamespace(text="Text.", section_heading=None)]),
            patch.object(service, "embed_snippet", new_callable=AsyncMock, return_value=[0.0]),
            patch.object(service, "pinecone_bulk_upsert"), patch.object(service, "pinecone_bulk_delete"),
        ):
            await service.ingest_file(**did_kwargs)
            h = (await _load(doc_id)).source_sha256
            async with async_session_factory() as s:
                row = await s.get(Document, doc_id)
                row.eligibility, row.approved_sha256 = Eligibility.eligible, h
                await s.commit()
            assert doc_id in await _answerable([doc_id])
            with patch.object(service, "load_bytes", side_effect=RuntimeError("cannot read")), pytest.raises(RuntimeError):
                await service.ingest_file(**did_kwargs)
            assert doc_id not in await _answerable([doc_id])  # status failed: nothing answers from it
    finally:
        await _drop([doc_id])


def test_only_the_inventory_step_ever_writes_an_approval() -> None:
    """Ingest records the file's hash and must never approve it. The workbook, through apply-inventory, is the only writer."""
    writers = set()
    for path in (ORCH / "ask_bpl_orchestrator").rglob("*.py"):
        code = re.sub(r'"""(.*?)"""', "", path.read_text(), flags=re.S)
        if re.search(r"\.approved_sha256\s*=(?!=)", code):
            writers.add(path.relative_to(ORCH).as_posix())
    assert writers == {"ask_bpl_orchestrator/ingest/inventory.py"}
    svc = (ORCH / "ask_bpl_orchestrator/ingest/service.py").read_text()
    assert "approved_sha256" not in svc and "document_row.source_sha256 = file_sha256" in svc


# ------------------------------------------------------------------------------------------------ apply-inventory
def _row(sid: str, name: str, *, elig: Eligibility = Eligibility.eligible, approved: Optional[str] = A) -> InventoryRow:
    return InventoryRow(source_id=sid, file_name=name, eligibility=elig, test_index_member=False,
                        reviewer="B. Bilissalou", reviewed_at=date(2026, 10, 12), approved_sha256=approved if elig == Eligibility.eligible else None)


def _apply(ids: list[uuid.UUID], rows: list[InventoryRow]) -> list[str]:
    async def go() -> list[str]:
        async with async_session_factory() as s:
            return await apply_inventory_to_db(s, {r.key: r for r in rows}, scope=ids)

    return asyncio.run(go())


def test_apply_records_the_approval_and_stays_quiet_when_the_stored_file_is_the_approved_one() -> None:
    t = uuid.uuid4().hex[:8]
    did = asyncio.run(_make(elig=Eligibility.authority_pending, source=A, approved=None, path=f"zz{t}.pdf"))
    try:
        lines = _apply([did], [_row(f"T{t}", f"zz{t}.pdf")])
        d = asyncio.run(_load(did))
        assert d.eligibility == Eligibility.eligible and d.approved_sha256 == A
        assert not [l for l in lines if l.startswith("warning:")] and did in asyncio.run(_answerable([did]))
    finally:
        asyncio.run(_drop([did]))


def test_apply_warns_with_both_hash_prefixes_when_the_stored_file_is_not_the_approved_one() -> None:
    t = uuid.uuid4().hex[:8]
    did = asyncio.run(_make(elig=Eligibility.authority_pending, source=B, approved=None, path=f"zz{t}.pdf"))
    try:
        lines = _apply([did], [_row(f"T{t}", f"zz{t}.pdf")])
        warn = next(l for l in lines if l.startswith(f"warning:T{t}:"))
        assert B[:12] in warn and A[:12] in warn and "cannot answer" in warn
        d = asyncio.run(_load(did))
        assert d.approved_sha256 == A and did not in asyncio.run(_answerable([did]))  # recorded, and the rule withholds it
    finally:
        asyncio.run(_drop([did]))


def test_apply_says_when_no_file_hash_was_ever_stored() -> None:
    t = uuid.uuid4().hex[:8]
    did = asyncio.run(_make(elig=Eligibility.authority_pending, source=None, approved=None, path=f"zz{t}.pdf"))
    try:
        warn = next(l for l in _apply([did], [_row(f"T{t}", f"zz{t}.pdf")]) if l.startswith(f"warning:T{t}:"))
        assert "before patch 0023" in warn and "re-ingested" in warn
        assert did not in asyncio.run(_answerable([did]))
    finally:
        asyncio.run(_drop([did]))


@pytest.mark.parametrize("new", [Eligibility.authority_pending, Eligibility.blocked, Eligibility.excluded, Eligibility.superseded])
def test_apply_clears_a_recorded_approval_when_the_row_stops_being_eligible(new: Eligibility) -> None:
    t = uuid.uuid4().hex[:8]
    did = asyncio.run(_make(elig=Eligibility.eligible, source=A, approved=A, path=f"zz{t}.pdf"))
    try:
        _apply([did], [_row(f"T{t}", f"zz{t}.pdf", elig=new)])
        assert asyncio.run(_load(did)).approved_sha256 is None
    finally:
        asyncio.run(_drop([did]))


@pytest.mark.parametrize("new", [Eligibility.authority_pending, Eligibility.blocked, Eligibility.excluded, Eligibility.superseded])
def test_apply_never_records_an_approval_for_a_row_that_is_not_eligible_even_if_the_row_carries_a_hash(new: Eligibility) -> None:
    """The loader already drops the hash on such rows; apply must hold the line itself (defence in depth)."""
    t = uuid.uuid4().hex[:8]
    did = asyncio.run(_make(elig=Eligibility.authority_pending, source=A, approved=None, path=f"zz{t}.pdf"))
    try:
        row = InventoryRow(source_id=f"T{t}", file_name=f"zz{t}.pdf", eligibility=new, test_index_member=False, approved_sha256=A)
        _apply([did], [row])
        assert asyncio.run(_load(did)).approved_sha256 is None
    finally:
        asyncio.run(_drop([did]))


def test_apply_clears_the_approval_of_a_document_with_no_inventory_row() -> None:
    t = uuid.uuid4().hex[:8]
    did = asyncio.run(_make(elig=Eligibility.eligible, source=A, approved=A, path=f"zz{t}-unlisted.pdf"))
    other = asyncio.run(_make(elig=Eligibility.authority_pending, source=A, approved=None, path=f"zz{t}-other.pdf"))
    try:
        lines = _apply([did, other], [_row(f"T{t}", f"zz{t}-other.pdf", elig=Eligibility.authority_pending)])
        d = asyncio.run(_load(did))
        assert any(l.startswith("unlisted:") for l in lines) and d.approved_sha256 is None and d.eligibility == Eligibility.authority_pending
    finally:
        asyncio.run(_drop([did, other]))


# ------------------------------------------------------------------------------------------------ the corpus report
def _facts(ids: list[uuid.UUID]) -> cr.CorpusFacts:
    return asyncio.run(cr.gather_corpus_facts(get_settings(), cr.alembic_head(), scope=ids))


def _report(t: str, ids: list[uuid.UUID], tmp_path: Path) -> cr.CorpusReport:
    rows = cr.read_sources(workbook(tmp_path / "w.xlsx", [[f"T{t}", f"zz{t}.pdf", "Pass", "No", "Eligible", "B. B / 2026-10-12", A]]))
    return cr.build_report(rows, _facts(ids))


def test_a_changed_file_is_a_disagreement_that_names_both_hashes_and_the_way_out(tmp_path: Path) -> None:
    t = uuid.uuid4().hex[:8]
    did = asyncio.run(_make(source=B, approved=A, path=f"zz{t}.pdf"))
    try:
        rep = _report(t, [did], tmp_path)
        f = next(f for f in rep.disagreements if f.code == "approved_file_differs")
        assert B[:12] in f.text and A[:12] in f.text and "covers only the file that was reviewed" in f.text and "Approved SHA-256" in f.todo
        assert "not_answerable_though_expected" not in {x.code for x in rep.findings}  # the specific finding replaces the vague one
    finally:
        asyncio.run(_drop([did]))


def test_a_document_ingested_before_the_patch_is_reported_as_needing_a_reingest(tmp_path: Path) -> None:
    t = uuid.uuid4().hex[:8]
    did = asyncio.run(_make(source=None, approved=A, path=f"zz{t}.pdf"))
    try:
        f = next(f for f in _report(t, [did], tmp_path).disagreements if f.code == "approved_file_differs")
        assert "before patch 0023" in f.text
    finally:
        asyncio.run(_drop([did]))


def test_a_matching_hash_is_clean_and_counted_as_confirmed(tmp_path: Path) -> None:
    t = uuid.uuid4().hex[:8]
    did = asyncio.run(_make(source=A, approved=A, path=f"zz{t}.pdf"))
    try:
        rep = _report(t, [did], tmp_path)
        assert rep.disagreements == [] and rep.answerable_now == 1 and rep.eligible == 1
    finally:
        asyncio.run(_drop([did]))


def test_stored_documents_print_the_full_file_hash_and_say_so_when_it_is_unknown(tmp_path: Path) -> None:
    t = uuid.uuid4().hex[:8]
    a = asyncio.run(_make(elig=Eligibility.authority_pending, member=True, source=A, approved=None, path=f"zz{t}.pdf"))
    b = asyncio.run(_make(elig=Eligibility.authority_pending, member=True, source=None, approved=None, path=f"zz{t}-b.pdf"))
    try:
        rows = cr.read_sources(workbook(tmp_path / "w.xlsx", [
            [f"T{t}", f"zz{t}.pdf", "Pass", "Yes", "Authority pending", None, None],
            [f"T{t}b", f"zz{t}-b.pdf", "Pass", "Yes", "Authority pending", None, None]]))
        text_ = cr.render(cr.build_report(rows, _facts([a, b])))
        assert f"file_sha256={A}" in text_ and "file_sha256=unknown (re-ingest to record it)" in text_
        assert "must equal" in text_
    finally:
        asyncio.run(_drop([a, b]))


@pytest.mark.parametrize("approved,stored", list(itertools.product(HASHES, HASHES)))
def test_the_corpus_report_and_the_vector_report_agree_with_the_rule_on_every_hash_combination(approved, stored) -> None:
    from ask_bpl_orchestrator import vector_report as vr

    did = asyncio.run(_make(source=stored, approved=approved))
    try:
        want = approved is not None and approved == stored
        mine = next(d for d in asyncio.run(vr.gather_db_facts(get_settings(), vr.alembic_head(), scope=[did])).docs)
        theirs = next(d for d in _facts([did]).docs)
        assert mine.answerable is want and theirs.answerable is want
    finally:
        asyncio.run(_drop([did]))

