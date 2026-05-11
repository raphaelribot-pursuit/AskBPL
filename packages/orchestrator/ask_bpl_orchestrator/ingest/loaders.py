"""Minimal PDF / DOCX / Markdown loaders."""

from __future__ import annotations

from pathlib import Path


def load_bytes(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        fragments = []
        for page in reader.pages:
            fragments.append(((page.extract_text() or "").replace("\uf0b7", "")).strip())
        merged = "\n\n".join(f for f in fragments if f)
        return merged

    if suffix == ".docx":
        import docx  # noqa: WPS433

        document = docx.Document(str(path))
        return "\n".join(p.text.strip() for p in document.paragraphs if p.text.strip())

    if suffix in {".md", ".markdown", ".txt"}:
        return path.read_text(encoding="utf-8", errors="ignore")

    raise ValueError(f"Unsupported suffix {suffix} for path {path}")
