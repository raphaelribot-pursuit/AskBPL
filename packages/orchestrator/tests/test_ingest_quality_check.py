"""ING-3, patch 0039: an automatic text-quality check before a PDF is sent to the embedding service.

Thresholds were calibrated on every PDF the team holds (2026-11-01): the scanned Conflict of Interest file has 90% thin
pages and a median of 0 characters per page; every text PDF has at most 14% thin pages and a median of at least 647.
Collection Maintenance (SRC-08) shows 33 split-word samples; every other file shows 5 or fewer.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from ask_bpl_orchestrator.ingest import batch
from ask_bpl_orchestrator.ingest.quality import assess_pdf

ORCH = Path(__file__).resolve().parents[1]
CORPUS = ORCH / "sample_corpus"
SCAN = CORPUS / "pilot" / "06 - Conflict of Interest (06.14) (1) (1).pdf"  # image-only pages
TEXT = CORPUS / "pilot" / "04 - Annual Leave Policy (01.06) (1).pdf"
SPLIT = CORPUS / "wave1" / "02d - Collection Maintenance Procedures (updated 2026).pdf"
INVENTORY = CORPUS / "AskBPL_Source_Inventory_v0_1.xlsx"


def test_a_scanned_pdf_is_judged_unreadable() -> None:
    report = assess_pdf(SCAN)

    assert report.unreadable
    assert "thin" in report.reason


def test_an_ordinary_text_pdf_is_judged_readable() -> None:
    report = assess_pdf(TEXT)

    assert not report.unreadable and report.reason == ""


@pytest.mark.parametrize("manifest", ["corpus_manifest_pilot.yaml", "corpus_manifest_wave1.yaml", "corpus_manifest_wave2.yaml"])
def test_no_document_in_the_shipped_manifests_is_refused_by_the_check(manifest: str) -> None:
    m = yaml.safe_load((CORPUS / manifest).read_text())
    for d in m["documents"]:
        path = CORPUS / m["corpus_root"] / d["path"]
        if path.suffix.lower() != ".pdf" or d.get("validated_extraction"):
            continue  # the scanned SRC-13 is ingested from its validated record, never from its image pages
        assert not assess_pdf(path).unreadable, d["path"]


def test_heavy_word_splitting_is_flagged_but_does_not_make_a_pdf_unreadable() -> None:
    report = assess_pdf(SPLIT)

    assert report.split_words >= 15 and report.split_warning
    assert not report.unreadable


def _manifest(tmp_path: Path, files: dict[str, Path]) -> Path:
    root = tmp_path / "docs"
    root.mkdir()
    for name, src in files.items():
        shutil.copy(src, root / name)
    m = tmp_path / "manifest.yaml"
    m.write_text(yaml.safe_dump({"corpus_root": "docs", "documents": [{"path": n, "policy": "generic_policy", "title": n} for n in files]}))
    return m


async def test_batch_refuses_an_unreviewed_scan_before_anything_is_embedded(tmp_path: Path) -> None:
    calls: list = []

    async def fake_ingest(**kw):
        calls.append(kw)

    manifest = _manifest(tmp_path, {"Unlisted scanned policy.pdf": SCAN, "Unlisted text policy.pdf": TEXT})
    with patch.object(batch, "ingest_file", side_effect=fake_ingest):
        lines = await batch.ingest_manifest(manifest, INVENTORY)

    refused = [ln for ln in lines if ln.startswith("refused:Unlisted scanned policy.pdf:text_quality:")]
    assert refused and "EXTRACTION_REVIEW" in refused[0]
    assert [Path(str(c["absolute_path"])).name for c in calls] == ["Unlisted text policy.pdf"]


async def test_batch_warns_about_split_words_and_still_ingests(tmp_path: Path) -> None:
    calls: list = []

    async def fake_ingest(**kw):
        calls.append(kw)

    manifest = _manifest(tmp_path, {"Unlisted split policy.pdf": SPLIT})
    with patch.object(batch, "ingest_file", side_effect=fake_ingest):
        lines = await batch.ingest_manifest(manifest, INVENTORY)

    assert any(ln.startswith("warning:Unlisted split policy.pdf:split_words:") for ln in lines)
    assert any(ln.startswith("indexed:Unlisted split policy.pdf") for ln in lines)
    assert len(calls) == 1


async def test_a_validated_scan_is_not_checked_against_its_image_pages(tmp_path: Path) -> None:
    """SRC-13 goes through its validated record; the quality check must not refuse it."""
    calls: list = []

    async def fake_ingest(**kw):
        calls.append(kw)

    with patch.object(batch, "ingest_file", side_effect=fake_ingest):
        lines = await batch.ingest_manifest(CORPUS / "corpus_manifest_pilot.yaml", INVENTORY)

    assert not [ln for ln in lines if ":text_quality:" in ln]
    assert any("Conflict of Interest" in Path(str(c["absolute_path"])).name for c in calls)
