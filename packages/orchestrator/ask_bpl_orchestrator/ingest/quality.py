"""Automatic text-quality check for PDFs before ingest (PRD ING-3, GATE-04; patch 0039).

Runs on the text the configured reader (PDF_READER) would extract. Nothing is stored or sent anywhere.

- **Unreadable** (the batch refuses the file): half or more of the pages are thin (under 100 characters), or the median
  page has fewer than 200 characters. This is the signature of a scanned or image-only PDF: its text must come from a
  person's validated extraction (docs/EXTRACTION_REVIEW.md), never from the empty text layer or unchecked OCR.
- **Split-word warning** (the file is still ingested): 15 or more split-word samples, the artefact seen in Collection
  Maintenance (SRC-08). The text is usable but a curator should look at it in the citation viewer.

Calibration (2026-11-01, every PDF the team holds): the scanned Conflict of Interest file has 90% thin pages and a
median of 0 characters; every text PDF has at most 14% thin pages and a median of at least 647; split-word samples
are 33 for SRC-08 and at most 5 elsewhere.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path

from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.ingest.reader_compare import THIN_PAGE_CHARS, read_with

THIN_SHARE_LIMIT = 0.5
MEDIAN_CHARS_MIN = 200
SPLIT_WORDS_WARN = 15


@dataclass(frozen=True)
class QualityReport:
    pages: int
    thin_pages: int
    median_chars: float
    split_words: int

    @property
    def unreadable(self) -> bool:
        return self.reason != ""

    @property
    def reason(self) -> str:
        if self.pages == 0:
            return "no pages with text"
        if self.thin_pages / self.pages >= THIN_SHARE_LIMIT:
            return f"{self.thin_pages} of {self.pages} pages are thin (under {THIN_PAGE_CHARS} characters)"
        if self.median_chars < MEDIAN_CHARS_MIN:
            return f"median page has {self.median_chars:.0f} characters (under {MEDIAN_CHARS_MIN})"
        return ""

    @property
    def split_warning(self) -> bool:
        return self.split_words >= SPLIT_WORDS_WARN


def assess_pdf(path: Path, reader: str | None = None) -> QualityReport:
    result = read_with(path, reader or get_settings().pdf_reader)
    lengths = [len(p) for p in result.pages]
    return QualityReport(
        pages=len(lengths),
        thin_pages=result.thin_pages,
        median_chars=statistics.median(lengths) if lengths else 0.0,
        split_words=len(result.split_samples()),
    )
