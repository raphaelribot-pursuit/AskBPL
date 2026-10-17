"""Minimal PDF / DOCX / Markdown loaders."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from ask_bpl_orchestrator.ingest.provenance import PageSpan, build_page_spans


class LoadedText(str):
    """Extracted text that also remembers which source page each part came from (patch 0013).

    It IS the text (a ``str``), so every existing caller and test double that returns a plain string keeps
    working. ``pages`` is None when the format has no pages (docx, markdown) or the caller supplied plain text.
    Spans are offsets into ``self.strip()``, the string the chunker sees.
    """

    pages: Optional[Sequence[PageSpan]] = None

    def __new__(cls, text: str, pages: Optional[Sequence[PageSpan]] = None):
        obj = super().__new__(cls, text)
        obj.pages = pages
        return obj


def load_bytes(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        from ask_bpl_orchestrator.ingest.ocr_fallback import _merge_pages, extract_pdf_pages

        fragments = extract_pdf_pages(path)
        merged = _merge_pages(fragments)
        lead = len(merged) - len(merged.lstrip())
        return LoadedText(merged, build_page_spans(fragments, lead=lead))

    if suffix == ".docx":
        import docx  # noqa: WPS433

        document = docx.Document(str(path))
        return "\n".join(p.text.strip() for p in document.paragraphs if p.text.strip())

    if suffix in {".md", ".markdown", ".txt"}:
        return path.read_text(encoding="utf-8", errors="ignore")

    raise ValueError(f"Unsupported suffix {suffix} for path {path}")
