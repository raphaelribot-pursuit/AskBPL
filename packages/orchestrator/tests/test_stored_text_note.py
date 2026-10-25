"""Patch 0021: the corpus report notes stored text on a document the workbook keeps out of answers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pytest

from ask_bpl_orchestrator import corpus_report as cr
from tests.test_corpus_report import codes, doc, facts_with, sources, wrow


def _report(tmp_path: Path, row: dict[str, Any], d: cr.DbDoc) -> cr.CorpusReport:
    return cr.build_report(sources(tmp_path, [row]), facts_with(d), inventory_name="x")


def _note(rep: cr.CorpusReport) -> Optional[cr.Finding]:
    return next((f for f in rep.findings if f.code == "stored_text_on_blocked_document"), None)


# ------------------------------------------------------------------------------------------------ report note
def test_blocked_document_with_validated_review_record_and_chunks_gets_the_pending_decision_note(tmp_path: Path) -> None:
    d = doc("a.pdf", elig="blocked", member=False, chunks=21, answerable=False, extraction="validated")
    f = _note(_report(tmp_path, wrow("S1", "a.pdf", parse="FAIL: scanned"), d))
    assert f is not None and f.severity == cr.NOTE
    assert "activate" in f.text and "21" in f.text and "validated review record" in f.text
    assert "--purge-vectors" in f.todo and "Decide" in f.todo


def test_blocked_document_without_review_record_gets_the_purge_note(tmp_path: Path) -> None:
    d = doc("a.pdf", elig="blocked", member=False, chunks=4, answerable=False, extraction="standard")
    f = _note(_report(tmp_path, wrow("S1", "a.pdf", parse="FAIL: scanned"), d))
    assert f is not None and f.severity == cr.NOTE and "validated review record" not in f.text
    assert "--purge-vectors" in f.todo and "pending" not in f.text
    assert _report(tmp_path, wrow("S1", "a.pdf", parse="FAIL: scanned"), d).disagreements == []


@pytest.mark.parametrize("life", ["Excluded", "Superseded by S2"])
def test_excluded_and_superseded_documents_with_chunks_get_the_note(tmp_path: Path, life: str) -> None:
    d = doc("a.pdf", elig=life.split()[0].lower(), member=False, chunks=2, answerable=False, superseded=life.startswith("Sup"))
    rep = _report(tmp_path, wrow("S1", "a.pdf", life=life), d)
    f = _note(rep)
    assert f is not None and f.severity == cr.NOTE and life.split()[0].lower() in f.text
    assert rep.disagreements == []


def test_the_note_is_a_note_not_a_disagreement_so_strict_does_not_fail_on_it(tmp_path: Path) -> None:
    d = doc("a.pdf", elig="blocked", member=False, chunks=21, answerable=False, extraction="validated")
    rep = _report(tmp_path, wrow("S1", "a.pdf", parse="FAIL: scanned"), d)
    assert codes(rep, "S1") == {"stored_text_on_blocked_document"}
    assert rep.disagreements == []


def test_no_note_without_chunks_or_for_a_document_that_may_answer(tmp_path: Path) -> None:
    empty = doc("a.pdf", elig="blocked", member=False, chunks=0, answerable=False)
    assert _note(_report(tmp_path, wrow("S1", "a.pdf", parse="FAIL: scanned"), empty)) is None
    live = doc("b.pdf")
    assert _note(_report(tmp_path, wrow("S1", "b.pdf"), live)) is None


def test_an_answerable_blocked_document_gets_the_urgent_finding_not_the_note(tmp_path: Path) -> None:
    d = doc("a.pdf", elig="authority_pending", member=True, chunks=5, answerable=True)
    rep = _report(tmp_path, wrow("S1", "a.pdf", parse="FAIL: scanned"), d)
    assert "answerable_but_not_allowed" in codes(rep, "S1")
    assert _note(rep) is None


def test_the_note_is_printed_in_the_notes_section(tmp_path: Path) -> None:
    d = doc("a.pdf", elig="blocked", member=False, chunks=21, answerable=False, extraction="validated")
    text = cr.render(_report(tmp_path, wrow("S1", "a.pdf", parse="FAIL: scanned"), d))
    assert "NOTES (1)" in text and "stored_text_on_blocked_document" in text
