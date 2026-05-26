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


def _merge_pages(fragments: list[str]) -> str:
    return "\n\n".join(f for f in fragments if f)


def extract_pdf_text_with_ocr(pdf_path: Path) -> str:
    """Extract text from a PDF, using OCR when a page has too little selectable text."""
    cfg = get_settings()
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)

    if total_pages == 0:
        return ""

    if not cfg.ocr_enabled:
        fragments = [_pypdf_page_text(p) for p in reader.pages]
        logger.info(
            "OCR disabled via settings: %s — using pypdf only (%d pages)",
            pdf_path.name,
            total_pages,
        )
        return _merge_pages(fragments)

    page_texts: list[str | None] = [None] * total_pages
    ocr_pages: list[int] = []
    pypdf_pages: list[int] = []

    for i, page in enumerate(reader.pages):
        text = _pypdf_page_text(page)
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
        return _merge_pages([t for t in page_texts if t is not None])

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
        return _merge_pages([t for t in page_texts if t is not None])

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

    return _merge_pages([t for t in page_texts if t is not None])
