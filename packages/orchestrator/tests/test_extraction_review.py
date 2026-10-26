"""Extraction review and controlled activation of scanned policies (patch 0009; PRD ING-3, ING-11, GATE-04).

Hermetic: no OCR engine, no network, no Pinecone. A fake page reader stands in for Tesseract. DB tests need
Postgres like the other integration tests and clean up after themselves.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import openpyxl
import pytest
import yaml
from sqlalchemy import delete, select

from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.db.models import (
    Chunk,
    Document,
    Eligibility,
    ExtractionStatus,
    IngestStatus,
    SourceFormat,
)
from ask_bpl_orchestrator.db.session import async_session_factory
from ask_bpl_orchestrator.ingest import batch, service
from ask_bpl_orchestrator.ingest.extraction_review import (
    RECORD_FILE,
    REVIEW_FILE,
    TEXT_FILE,
    ExtractionValidationError,
    PageReading,
    finalize_review,
    prepare_review,
    verify_record,
)
from ask_bpl_orchestrator.ingest.inventory import (
    InventoryRow,
    apply_inventory_to_db,
    derive_eligibility,
    load_inventory,
)
from ask_bpl_orchestrator.services.eligibility import is_retrievable, retrievable_clause

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "sample_corpus" / "AskBPL_Source_Inventory_v0_1.xlsx"
NOW = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 14)

PAGE_TEXT = {
    1: "I. Introduction. Covered Persons must act with integrity and avoid any conflict of interest. " * 6,
    2: "Covered Persons include trustees, officers and key employees of the Library. " * 8,
    3: "Signed: ________",
}


def fake_reader(pdf: Path, dpi: int):
    return [
        PageReading(page=n, textlayer=PAGE_TEXT[n] if n == 1 else "", ocr_text=PAGE_TEXT[n],
                    confidence=95.0 if n < 3 else 55.0, image_png=b"\x89PNG fake")
        for n in (1, 2, 3)
    ]


@pytest.fixture()
def pdf(tmp_path: Path) -> Path:
    p = tmp_path / "scan.pdf"
    p.write_bytes(b"%PDF-1.4 stand-in bytes for hashing only")
    return p


def _prepare(pdf: Path, tmp_path: Path) -> Path:
    out = tmp_path / "packet"
    prepare_review(pdf, "SRC-T1", out, dpi=100, reader=fake_reader, now=NOW)
    return out


def _complete(packet: Path, *, verdicts=None, reviewer="Bath Bilissalou", on="2026-10-14", confirmed=True,
              notes=None) -> None:
    review = yaml.safe_load((packet / REVIEW_FILE).read_text(encoding="utf-8"))
    review.update(reviewer=reviewer, reviewed_on=on, confirmed=confirmed)
    for page in review["pages"]:
        page["verdict"] = (verdicts or {}).get(page["page"], "verified")
        page["note"] = (notes or {}).get(page["page"], "")
    (packet / REVIEW_FILE).write_text(yaml.safe_dump(review), encoding="utf-8")


# ------------------------------------------------------------------ prepare
def test_prepare_writes_packet_and_flags_weak_pages(pdf: Path, tmp_path: Path) -> None:
    packet = _prepare(pdf, tmp_path)
    for name in ("review.yaml", "source.json", "report.html", "pages/page-01.txt", "pages/page-01.ocr.txt",
                 "pages/page-01.textlayer.txt", "pages/page-03.png"):
        assert (packet / name).is_file(), name
    source = json.loads((packet / "source.json").read_text())
    by_page = {p["page"]: p for p in source["pages"]}
    assert by_page[1]["flags"] == [] and by_page[2]["flags"] == []
    assert set(by_page[3]["flags"]) == {"thin", "low_confidence"}
    assert source["pdf_sha256"] and source["source_id"] == "SRC-T1"
    review = yaml.safe_load((packet / REVIEW_FILE).read_text())
    assert review["confirmed"] is False and {p["verdict"] for p in review["pages"]} == {"pending"}


def test_prepare_refuses_to_overwrite_review_work(pdf: Path, tmp_path: Path) -> None:
    packet = _prepare(pdf, tmp_path)
    with pytest.raises(ExtractionValidationError, match="already exists"):
        prepare_review(pdf, "SRC-T1", packet, dpi=100, reader=fake_reader, now=NOW)
    prepare_review(pdf, "SRC-T1", packet, dpi=100, reader=fake_reader, now=NOW, force=True)  # explicit restart


def test_prepare_rejects_bad_source_id_and_missing_pdf(tmp_path: Path, pdf: Path) -> None:
    with pytest.raises(ExtractionValidationError):
        prepare_review(pdf, "../etc", tmp_path / "a", dpi=100, reader=fake_reader)
    with pytest.raises(ExtractionValidationError):
        prepare_review(tmp_path / "nope.pdf", "SRC-T1", tmp_path / "b", dpi=100, reader=fake_reader)


# ------------------------------------------------------------------ finalize
def test_finalize_refuses_an_untouched_packet(pdf: Path, tmp_path: Path) -> None:
    packet = _prepare(pdf, tmp_path)
    with pytest.raises(ExtractionValidationError) as err:
        finalize_review(packet, today=TODAY)
    msg = str(err.value)
    assert "reviewer" in msg and "confirmed" in msg and "page 1" in msg
    assert not (packet / RECORD_FILE).exists() and not (packet / TEXT_FILE).exists()  # nothing written on failure


@pytest.mark.parametrize("kwargs,needle", [
    ({"reviewer": ""}, "reviewer"),
    ({"reviewer": "  x "}, "reviewer"),
    ({"on": ""}, "YYYY-MM-DD"),
    ({"on": "14/10/2026"}, "YYYY-MM-DD"),
    ({"on": "2026-09-01"}, "before the review packet"),
    ({"on": "2027-01-01"}, "future"),
    ({"confirmed": False}, "confirmed"),
])
def test_finalize_rejects_incomplete_sign_off(pdf: Path, tmp_path: Path, kwargs, needle) -> None:
    packet = _prepare(pdf, tmp_path)
    _complete(packet, **kwargs)
    with pytest.raises(ExtractionValidationError, match=needle):
        finalize_review(packet, today=TODAY)
    assert not (packet / RECORD_FILE).exists()


def test_excluded_page_needs_a_reason_and_something_must_remain(pdf: Path, tmp_path: Path) -> None:
    packet = _prepare(pdf, tmp_path)
    _complete(packet, verdicts={3: "excluded"})
    with pytest.raises(ExtractionValidationError, match="page 3: an excluded page needs a note"):
        finalize_review(packet, today=TODAY)
    _complete(packet, verdicts={1: "excluded", 2: "excluded", 3: "excluded"},
              notes={n: "blank page, no policy text" for n in (1, 2, 3)})
    with pytest.raises(ExtractionValidationError, match="no validated text"):
        finalize_review(packet, today=TODAY)


def test_verified_page_with_empty_text_is_rejected(pdf: Path, tmp_path: Path) -> None:
    packet = _prepare(pdf, tmp_path)
    (packet / "pages" / "page-02.txt").write_text("  \n", encoding="utf-8")
    _complete(packet)
    with pytest.raises(ExtractionValidationError, match="page 2: marked verified but its text is empty"):
        finalize_review(packet, today=TODAY)


def test_finalize_success_records_edits_exclusions_and_hashes(pdf: Path, tmp_path: Path) -> None:
    packet = _prepare(pdf, tmp_path)
    page2 = packet / "pages" / "page-02.txt"
    page2.write_text(page2.read_text().replace("trustees", "trustees (corrected)"), encoding="utf-8")
    _complete(packet, verdicts={3: "excluded"}, notes={3: "signature line only, no policy text"})
    record_path = finalize_review(packet, today=TODAY)
    rec = json.loads(record_path.read_text())
    assert rec["reviewer"] == "Bath Bilissalou" and rec["reviewed_on"] == "2026-10-14"
    assert rec["edited_pages"] == [2] and rec["excluded_pages"] == [3]
    assert rec["pdf_sha256"] and rec["validated_text_sha256"]
    text = (packet / TEXT_FILE).read_text()
    assert text.startswith("## Page 1") and "## Page 2" in text and "## Page 3" not in text
    assert "trustees (corrected)" in text
    ve = verify_record(record_path, pdf)
    assert ve.page_count == 3 and ve.reviewer == "Bath Bilissalou" and ve.source_id == "SRC-T1"
    assert len(ve.record_sha256) == 64 and ve.text == text


# ------------------------------------------------------------------ verify (fail closed)
@pytest.fixture()
def finalized(pdf: Path, tmp_path: Path) -> Path:
    packet = _prepare(pdf, tmp_path)
    _complete(packet)
    return finalize_review(packet, today=TODAY)


def test_verify_rejects_a_changed_pdf(finalized: Path, pdf: Path) -> None:
    pdf.write_bytes(pdf.read_bytes() + b"x")
    with pytest.raises(ExtractionValidationError, match="not the file that was reviewed"):
        verify_record(finalized, pdf)


def test_verify_rejects_edited_text(finalized: Path, pdf: Path) -> None:
    (finalized.parent / TEXT_FILE).write_text("tampered", encoding="utf-8")
    with pytest.raises(ExtractionValidationError, match="changed after the review"):
        verify_record(finalized, pdf)


def test_verify_rejects_missing_or_altered_record(finalized: Path, pdf: Path, tmp_path: Path) -> None:
    with pytest.raises(ExtractionValidationError, match="not found"):
        verify_record(tmp_path / "nope.json", pdf)
    rec = json.loads(finalized.read_text())
    for key in ("reviewer", "reviewed_on", "validated_text_sha256", "pdf_sha256"):
        broken = dict(rec)
        broken.pop(key)
        finalized.write_text(json.dumps(broken), encoding="utf-8")
        with pytest.raises(ExtractionValidationError):
            verify_record(finalized, pdf)
    finalized.write_text(json.dumps({**rec, "schema_version": 99}), encoding="utf-8")
    with pytest.raises(ExtractionValidationError, match="schema_version"):
        verify_record(finalized, pdf)
    finalized.write_text("{not json", encoding="utf-8")
    with pytest.raises(ExtractionValidationError, match="not valid JSON"):
        verify_record(finalized, pdf)


def test_verify_ignores_path_tricks_in_text_file_name(finalized: Path, pdf: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text((finalized.parent / TEXT_FILE).read_text(), encoding="utf-8")
    rec = json.loads(finalized.read_text())
    rec["validated_text_file"] = "../outside.md"  # must resolve to the file name next to the record only
    (finalized.parent / TEXT_FILE).unlink()
    finalized.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(ExtractionValidationError, match="not found next to the record"):
        verify_record(finalized, pdf)


# ------------------------------------------------------------------ inventory: the workbook alone cannot activate
def _workbook(path: Path, parse: str, lifecycle: str, in_pilot: str = "Yes") -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Source Inventory"
    ws.append(["Source ID", "File name", "Parse check", "In current pilot index", "Lifecycle status (ING-9)",
               "Reviewer / date"])
    ws.append(["SRC-T1", "scan.pdf", parse, in_pilot, lifecycle, None])
    wb.save(path)
    return path


def test_validated_parse_check_is_a_claim_not_a_pass(tmp_path: Path) -> None:
    row = load_inventory(_workbook(tmp_path / "a.xlsx", "Validated by manual review", "Authority pending"))["scan"]
    assert row.extraction_validated_claim and row.eligibility == Eligibility.authority_pending
    assert row.test_index_member
    # editing only the parse check is not enough while the lifecycle still says blocked
    still = load_inventory(_workbook(tmp_path / "b.xlsx", "Validated by manual review",
                                     "Authority pending; extraction blocked"))["scan"]
    assert still.eligibility == Eligibility.blocked
    # and an ordinary pass is not a claim
    plain = load_inventory(_workbook(tmp_path / "c.xlsx", "Pass: text layer present", "Authority pending"))["scan"]
    assert not plain.extraction_validated_claim


def test_shipped_inventory_activates_conflict_of_interest_only_with_both_keys() -> None:
    """SRC-13 was activated on 2026-10-25 (DEC-15). Two keys are needed and both are pinned: the workbook claims the
    validation, and the manifest names the record. It is a marked test-index document, never BPL-confirmed."""
    import yaml

    inv = load_inventory(INVENTORY)
    coi = next(r for r in inv.values() if r.source_id == "SRC-13")
    assert coi.eligibility == Eligibility.authority_pending and coi.test_index_member
    assert coi.extraction_validated_claim
    assert [r.source_id for r in inv.values() if r.extraction_validated_claim] == ["SRC-13"]  # no other row claims one
    assert not any(r.eligibility == Eligibility.eligible for r in inv.values())
    manifest = yaml.safe_load((ROOT / "sample_corpus" / "corpus_manifest_pilot.yaml").read_text())
    named = [d for d in manifest["documents"] if d.get("validated_extraction")]
    assert len(named) == 1 and "Conflict of Interest" in named[0]["path"]
    assert named[0]["validated_extraction"].endswith("extraction_reviews/SRC-13/validation_record.json")


async def _add_doc(session, *, path: str, extraction_status=ExtractionStatus.standard,
                   eligibility=Eligibility.authority_pending, member=True) -> uuid.UUID:
    doc_id = uuid.uuid4()
    session.add(Document(
        document_id=doc_id, title="scan", version="t", policy_type="generic_policy", source_format=SourceFormat.pdf,
        ingest_status=IngestStatus.indexed, eligibility=eligibility, test_index_member=member,
        extraction_status=extraction_status, source_path=path,
        # An eligible document is approved for its stored file, so only the rule under test can stop it (patch 0023).
        source_sha256="a" * 64 if eligibility == Eligibility.eligible else None,
        approved_sha256="a" * 64 if eligibility == Eligibility.eligible else None,
    ))
    await session.flush()
    session.add(Chunk(chunk_id=uuid.uuid4(), document_id=doc_id, ordinal=0, text="Covered Persons.", token_count=2))
    return doc_id


async def _cleanup(ids) -> None:
    async with async_session_factory() as s:
        await s.execute(delete(Chunk).where(Chunk.document_id.in_(list(ids))))
        await s.execute(delete(Document).where(Document.document_id.in_(list(ids))))
        await s.commit()


def _claim_row(tag: str) -> InventoryRow:
    return InventoryRow(source_id=f"SRC-T{tag}", file_name=f"zz-{tag} Scan.pdf", eligibility=Eligibility.authority_pending,
                        test_index_member=True, extraction_validated_claim=True)


@pytest.mark.asyncio
async def test_apply_inventory_keeps_claim_blocked_without_a_stored_record() -> None:
    tag = uuid.uuid4().hex[:8]
    row = _claim_row(tag)
    async with async_session_factory() as s:
        doc_id = await _add_doc(s, path=f"zz-{tag} Scan.pdf", extraction_status=ExtractionStatus.standard)
        await s.commit()
    try:
        async with async_session_factory() as s:
            lines = await apply_inventory_to_db(s, {row.key: row}, scope=[doc_id])
        async with async_session_factory() as s:
            doc = await s.get(Document, doc_id)
        assert doc.eligibility == Eligibility.blocked and not doc.test_index_member
        assert any("no verified review record" in ln for ln in lines)
        assert not is_retrievable(doc, get_settings().model_copy(update={"allow_test_index": True}))
    finally:
        await _cleanup([doc_id])


@pytest.mark.asyncio
async def test_apply_inventory_activates_only_with_record_and_claim_together() -> None:
    tag = uuid.uuid4().hex[:8]
    row = _claim_row(tag)
    async with async_session_factory() as s:
        doc_id = await _add_doc(s, path=f"zz-{tag} Scan.pdf", extraction_status=ExtractionStatus.validated)
        await s.commit()
    try:
        async with async_session_factory() as s:
            await apply_inventory_to_db(s, {row.key: row}, scope=[doc_id])
        async with async_session_factory() as s:
            doc = await s.get(Document, doc_id)
        assert doc.eligibility == Eligibility.authority_pending and doc.test_index_member
        assert is_retrievable(doc, get_settings().model_copy(update={"allow_test_index": True}))
        # the test-index switch still governs it: off means not answerable
        assert not is_retrievable(doc, get_settings().model_copy(update={"allow_test_index": False}))
    finally:
        await _cleanup([doc_id])


@pytest.mark.asyncio
async def test_review_required_is_never_answerable_even_if_eligible() -> None:
    cfg = get_settings().model_copy(update={"allow_test_index": True})
    async with async_session_factory() as s:
        eligible = await _add_doc(s, path=f"zz-{uuid.uuid4().hex[:6]}-a.pdf", eligibility=Eligibility.eligible,
                                  member=False, extraction_status=ExtractionStatus.review_required)
        pending = await _add_doc(s, path=f"zz-{uuid.uuid4().hex[:6]}-b.pdf", eligibility=Eligibility.authority_pending,
                                 member=True, extraction_status=ExtractionStatus.review_required)
        ok = await _add_doc(s, path=f"zz-{uuid.uuid4().hex[:6]}-c.pdf", eligibility=Eligibility.eligible,
                            member=False, extraction_status=ExtractionStatus.validated)
        await s.commit()
    try:
        async with async_session_factory() as s:
            rows = (await s.execute(
                select(Document.document_id).where(retrievable_clause(cfg),
                                                   Document.document_id.in_([eligible, pending, ok])))).scalars().all()
            docs = {i: await s.get(Document, i) for i in (eligible, pending, ok)}
        assert set(rows) == {ok}
        assert [is_retrievable(docs[i], cfg) for i in (eligible, pending, ok)] == [False, False, True]
    finally:
        await _cleanup([eligible, pending, ok])


# ------------------------------------------------------------------ ingest wiring
def _ingest_patches():
    return (
        patch.object(service, "split_text_with_sections",
                     side_effect=lambda text, **kw: [SimpleNamespace(text=text[:200], section_heading="Page 1")]),
        patch.object(service, "embed_snippet", new_callable=AsyncMock, return_value=[0.0]),
        patch.object(service, "pinecone_bulk_upsert"),
        patch.object(service, "pinecone_bulk_delete"),
    )


@pytest.mark.asyncio
async def test_ingest_uses_validated_text_and_resets_status_on_plain_reingest(finalized: Path, pdf: Path, tmp_path: Path) -> None:
    ve = verify_record(finalized, pdf)
    doc_id = service._document_uuid("scan.pdf")
    kwargs = dict(absolute_path=pdf, corpus_root=pdf.parent, policy_slug="generic_policy", title="Scan", version_label="v1")
    p1, p2, p3, p4 = _ingest_patches()
    try:
        with p1 as split, p2, p3, p4:
            with patch.object(service, "load_bytes", side_effect=AssertionError("must not run OCR/extraction")):
                await service.ingest_file(**kwargs, validated_extraction=ve)
            assert split.call_args.args[0] == ve.text  # the signed-off text, not machine output
            async with async_session_factory() as s:
                d = await s.get(Document, doc_id)
                assert d.extraction_status == ExtractionStatus.validated
                assert d.extraction_validated_by == "Bath Bilissalou" and d.extraction_validated_at == date(2026, 10, 14)
                assert d.extraction_record_sha256 == ve.record_sha256 and d.page_count == 3
            # re-ingesting by ordinary extraction must not leave a stale 'validated' on new text
            with patch.object(service, "load_bytes", return_value="machine text"):
                await service.ingest_file(**kwargs)
            async with async_session_factory() as s:
                d = await s.get(Document, doc_id)
                assert d.extraction_status == ExtractionStatus.standard
                assert d.extraction_validated_by is None and d.extraction_record_sha256 is None
            with patch.object(service, "load_bytes", return_value="machine text"):
                await service.ingest_file(**kwargs, extraction_review_required=True)
            async with async_session_factory() as s:
                assert (await s.get(Document, doc_id)).extraction_status == ExtractionStatus.review_required
    finally:
        await _cleanup([doc_id])


def _manifest(tmp_path: Path, pdf: Path, *, record: str | None, review: str | None = None) -> Path:
    entry = {"path": pdf.name, "policy": "generic_policy", "title": "Scan"}
    if record:
        entry["validated_extraction"] = record
    if review:
        entry["extraction_review"] = review
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(yaml.safe_dump({"corpus_root": ".", "documents": [entry]}), encoding="utf-8")
    return manifest


@pytest.mark.asyncio
async def test_batch_claim_without_record_fails_closed(pdf: Path, tmp_path: Path) -> None:
    inv = _workbook(tmp_path / "inv.xlsx", "Validated by manual review", "Authority pending")
    with patch.object(batch, "ingest_file", new_callable=AsyncMock) as ingest:
        lines = await batch.ingest_manifest(_manifest(tmp_path, pdf, record=None), inv)
    assert lines[0].startswith("failed:scan.pdf:inventory says extraction is validated")
    ingest.assert_not_called()


@pytest.mark.asyncio
async def test_batch_rejects_a_record_that_does_not_match_the_file(finalized: Path, pdf: Path, tmp_path: Path) -> None:
    inv = _workbook(tmp_path / "inv.xlsx", "Validated by manual review", "Authority pending")
    manifest = _manifest(tmp_path, pdf, record=str(finalized.relative_to(tmp_path)))
    pdf.write_bytes(b"a different file")
    with patch.object(batch, "ingest_file", new_callable=AsyncMock) as ingest:
        lines = await batch.ingest_manifest(manifest, inv)
    assert lines[0].startswith("failed:scan.pdf:validation record rejected") and "not the file that was reviewed" in lines[0]
    ingest.assert_not_called()


@pytest.mark.asyncio
async def test_batch_passes_a_verified_record_to_ingest(finalized: Path, pdf: Path, tmp_path: Path) -> None:
    inv = _workbook(tmp_path / "inv.xlsx", "Validated by manual review", "Authority pending")
    manifest = _manifest(tmp_path, pdf, record=str(finalized.relative_to(tmp_path)))
    with patch.object(batch, "ingest_file", new_callable=AsyncMock) as ingest:
        lines = await batch.ingest_manifest(manifest, inv)
    assert lines == ["indexed:scan.pdf:validated"]
    kw = ingest.call_args.kwargs
    assert kw["validated_extraction"].reviewer == "Bath Bilissalou" and kw["extraction_review_required"] is False


@pytest.mark.asyncio
async def test_batch_still_refuses_a_blocked_row_even_with_a_valid_record(finalized: Path, pdf: Path, tmp_path: Path) -> None:
    """Key two (the workbook) is independent of key one (the record): a record alone activates nothing."""
    inv = _workbook(tmp_path / "inv.xlsx", "FAIL: scanned or image-only", "Authority pending; extraction blocked")
    manifest = _manifest(tmp_path, pdf, record=str(finalized.relative_to(tmp_path)))
    with patch.object(batch, "ingest_file", new_callable=AsyncMock) as ingest:
        lines = await batch.ingest_manifest(manifest, inv)
    assert lines[0].startswith("refused:scan.pdf:blocked")
    ingest.assert_not_called()


@pytest.mark.asyncio
async def test_batch_review_required_flag_is_passed_through(pdf: Path, tmp_path: Path) -> None:
    inv = _workbook(tmp_path / "inv.xlsx", "Pass: text layer present", "Authority pending")
    with patch.object(batch, "ingest_file", new_callable=AsyncMock) as ingest:
        lines = await batch.ingest_manifest(_manifest(tmp_path, pdf, record=None, review="required"), inv)
    assert lines == ["indexed:scan.pdf:review_required"]
    assert ingest.call_args.kwargs["extraction_review_required"] is True


def test_derive_eligibility_is_unchanged_for_failed_parse_checks() -> None:
    assert derive_eligibility("Authority pending", "FAIL: scanned", None, None)[0] == Eligibility.blocked
    assert derive_eligibility("Authority pending", "Validated by manual review", None, None)[0] == Eligibility.authority_pending


def test_cli_prepare_refuses_without_ocr_tools_message(tmp_path: Path, pdf: Path, capsys) -> None:
    """A missing OCR stack is a clear error here, not silently empty pages as in the ingest fallback."""
    from ask_bpl_orchestrator.ingest import extraction_review as er

    with patch.object(er, "read_pages_with_ocr", side_effect=ExtractionValidationError("OCR tools are missing (x)")):
        with pytest.raises(SystemExit) as exit_info:
            er.main(["prepare", "--pdf", str(pdf), "--source-id", "SRC-T1", "--out", str(tmp_path / "o"), "--dpi", "100"])
    assert exit_info.value.code == 1 and "OCR tools are missing" in capsys.readouterr().err
