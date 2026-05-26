"""Minimal PDF / DOCX / Markdown loaders."""

from __future__ import annotations

from pathlib import Path


def load_bytes(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        from ask_bpl_orchestrator.ingest.ocr_fallback import extract_pdf_text_with_ocr

        return extract_pdf_text_with_ocr(path)

    if suffix == ".docx":
        import docx  # noqa: WPS433

        document = docx.Document(str(path))
        return "\n".join(p.text.strip() for p in document.paragraphs if p.text.strip())

    if suffix in {".md", ".markdown", ".txt"}:
        return path.read_text(encoding="utf-8", errors="ignore")

    raise ValueError(f"Unsupported suffix {suffix} for path {path}")
