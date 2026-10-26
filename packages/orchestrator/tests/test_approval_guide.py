"""Patch 0023: the curator guide teaches approval by file (recipe G) and no longer tells curators to reset by hand."""

from __future__ import annotations

from pathlib import Path

ORCH = Path(__file__).resolve().parents[1]

GUIDE = ORCH.parents[1] / "docs" / "CURATOR_WORKFLOW.md"


def test_the_guide_explains_approving_by_file_and_no_longer_tells_curators_to_reset_by_hand() -> None:
    g = GUIDE.read_text()
    low = " ".join(g.lower().split())
    assert "### G. Approve a reviewed document" in g and "Approved SHA-256" in g and "file_sha256" in g
    assert "reviewer **and** a review date" in g  # the 0020 guide test pins this phrase
    assert "stops answering at once" in low and "approved_file_differs" in g
    assert "reset the approval yourself" not in low and "does not reset its approval" not in low
    assert "keeps the approval" not in low
    assert g.index("### F.") < g.index("### G.") < g.index("## 5. Validate")  # recipes stay in order, before section 5


def test_every_finding_code_and_warning_this_patch_adds_has_a_row_in_the_guide_error_table() -> None:
    g = GUIDE.read_text()
    for needle in ("`approved_file_differs`", "marked Eligible without an approved file hash", "64 hexadecimal characters"):
        assert needle in g, needle
    src = (ORCH / "ask_bpl_orchestrator" / "corpus_report.py").read_text() + (ORCH / "ask_bpl_orchestrator" / "ingest" / "inventory.py").read_text()
    assert "marked Eligible without an approved file hash" in src and "64 hexadecimal characters" in src


def test_the_guide_never_calls_a_hash_a_review_of_the_content() -> None:
    low = " ".join(GUIDE.read_text().lower().split())
    assert "an approval covers a file, not its meaning" in low
