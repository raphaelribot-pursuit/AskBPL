"""Hybrid PDF text extraction: pypdf first, Tesseract OCR for thin text pages."""

from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader

from ask_bpl_orchestrator.config import get_settings

logger = logging.getLogger(__name__)


def _pypdf_page_text(page) -> str:
    """Match loaders.py normalization for direct text extraction."""
    return ((page.extract_text() or "").replace("\uf0b7", "")).strip()


def _pdfium_page_text(page) -> str:
    """Direct text from one PDFium page, normalised like the pypdf path (patch 0015, opt-in reader)."""
    textpage = page.get_textpage()
    try:
        raw = textpage.get_text_range() or ""
    finally:
        textpage.close()
    # PDFium writes U+FFFE where the page has a hyphen at a line end ("Anti-" / "Harassment"); pypdf writes "-".
    # Keeping U+FFFE would store a non-character inside policy words, so it is mapped to the hyphen pypdf produces.
    cleaned = raw.replace("\ufffe", "-")
    return cleaned.replace("\r\n", "\n").replace("\r", "\n").replace("\uf0b7", "").strip()


def _direct_page_texts(pdf_path: Path, reader_name: str) -> list[str]:
    """Selectable text per page from the configured reader. ``pypdf`` is the default and is unchanged.

    ``pdfium`` (patch 0015) needs the ``pypdfium2`` package. A missing package or an unknown name raises: it never
    falls back to pypdf quietly, because that would store different text from the one the operator asked for.
    """
    if reader_name == "pypdf":
        return [_pypdf_page_text(p) for p in PdfReader(str(pdf_path)).pages]
    if reader_name == "pdfium":
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:  # pragma: no cover - exercised through a patched import in tests
            raise RuntimeError("PDF_READER=pdfium needs the pypdfium2 package (pip install pypdfium2).") from exc
        document = pdfium.PdfDocument(str(pdf_path))
        try:
            return [_pdfium_page_text(document[i]) for i in range(len(document))]
        finally:
            document.close()
    raise ValueError(f"Unknown PDF reader {reader_name!r}; use 'pypdf' or 'pdfium'.")


def _merge_pages(fragments: list[str]) -> str:
    return "\n\n".join(f for f in fragments if f)


def extract_pdf_text_with_ocr(pdf_path: Path) -> str:
    """Extract text from a PDF, using OCR when a page has too little selectable text."""
    return _merge_pages(extract_pdf_pages(pdf_path))


def extract_pdf_pages(pdf_path: Path, *, reader: str | None = None) -> list[str]:
    """One string per source page (empty for a page with no text), so page numbers stay true to the PDF.

    ``extract_pdf_text_with_ocr`` is these pages merged; nothing about extraction itself changed in 0013.
    ``reader`` overrides the ``PDF_READER`` setting for one call (used by the comparison tools; ingest uses the setting).
    """
    cfg = get_settings()
    direct = _direct_page_texts(pdf_path, reader or getattr(cfg, "pdf_reader", "pypdf"))
    total_pages = len(direct)

    if total_pages == 0:
        return []

    if not cfg.ocr_enabled:
        logger.info(
            "OCR disabled via settings: %s — using direct text only (%d pages)",
            pdf_path.name,
            total_pages,
        )
        return list(direct)

    page_texts: list[str | None] = [None] * total_pages
    ocr_pages: list[int] = []
    pypdf_pages: list[int] = []

    for i, text in enumerate(direct):
        if len(text) >= cfg.ocr_min_chars_per_page:
            page_texts[i] = text
            pypdf_pages.append(i + 1)
        else:
            ocr_pages.append(i + 1)

    if not ocr_pages:
        logger.info(
            "All %d pages of %s extracted via pypdf (no OCR needed)",
            total_pages,
            pdf_path.name,
        )
        return [t or "" for t in page_texts]

    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError as e:
        logger.warning(
            "OCR dependencies not available (%s). Scanned pages in %s will lack text. "
            "Install optional extra: pip install -e '.[ocr]' and system packages "
            "tesseract-ocr + poppler-utils.",
            e,
            pdf_path.name,
        )
        for i in range(total_pages):
            if page_texts[i] is None:
                page_texts[i] = ""
        return [t or "" for t in page_texts]

    logger.info(
        "OCR fallback for %s: %d/%d pages need OCR (pages %s)",
        pdf_path.name,
        len(ocr_pages),
        total_pages,
        ocr_pages,
    )

    try:
        for page_num in ocr_pages:
            images = convert_from_path(
                str(pdf_path),
                first_page=page_num,
                last_page=page_num,
                dpi=cfg.ocr_dpi,
            )
            idx = page_num - 1
            if images:
                ocr_raw = pytesseract.image_to_string(images[0]) or ""
                ocr_text = ocr_raw.replace("\uf0b7", "").strip()
                page_texts[idx] = ocr_text
                logger.debug("OCR page %d: %d chars extracted", page_num, len(ocr_text))
            else:
                page_texts[idx] = ""
                logger.warning("OCR page %d: no image produced", page_num)

        logger.info(
            "OCR complete for %s: %d pages via pypdf, %d via OCR",
            pdf_path.name,
            len(pypdf_pages),
            len(ocr_pages),
        )
    except Exception as e:
        logger.error("OCR failed for %s: %s", pdf_path.name, e, exc_info=True)
        for i in range(total_pages):
            if page_texts[i] is None:
                page_texts[i] = ""

    return [t or "" for t in page_texts]
