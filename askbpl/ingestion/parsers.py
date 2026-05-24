"""Document parsers for corpus ingestion (TRD-IGN-1)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParseResult:
    """Text extracted from a source document."""

    text: str
    page_count: int
    empty_pages: int


def parse_pdf(path: Path) -> ParseResult:
    """Extract text from a PDF via pypdf (TRD-IGN-1)."""
    reader = PdfReader(str(path))
    parts: list[str] = []
    empty_pages = 0
    for page_num, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        if not page_text:
            empty_pages += 1
            logger.warning("Empty text on page %s of %s", page_num, path.name)
        else:
            parts.append(page_text)
    full_text = "\n\n".join(parts).strip()
    return ParseResult(text=full_text, page_count=len(reader.pages), empty_pages=empty_pages)


def parse_docx(path: Path) -> ParseResult:
    """DOCX parser stub — orchestrator step adds full support (TRD-IGN-1)."""
    raise NotImplementedError(f"DOCX parsing not implemented in Step 01: {path.name}")


def parse_markdown(path: Path) -> ParseResult:
    """Markdown parser stub — orchestrator step adds full support (TRD-IGN-1)."""
    raise NotImplementedError(f"Markdown parsing not implemented in Step 01: {path.name}")


def parse_document(path: Path) -> ParseResult:
    """Dispatch parser by file suffix (TRD-IGN-1)."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(path)
    if suffix == ".docx":
        return parse_docx(path)
    if suffix in {".md", ".markdown"}:
        return parse_markdown(path)
    raise ValueError(f"Unsupported file type: {suffix}")
