"""Patch 0015: opt-in pypdfium2 text reader, the PDF_READER setting and the reader comparison tool.

The default reader stays pypdf; nothing here changes what is stored unless PDF_READER=pdfium is set and a document is
re-ingested. The handmade PDFs below are tiny but real, so both readers are exercised on actual files.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ask_bpl_orchestrator.config import Settings
from ask_bpl_orchestrator.ingest import loaders, ocr_fallback, provenance_report, reader_compare
from ask_bpl_orchestrator.ingest.provenance import find_headings


def _make_pdf(path: Path, pages: list[list[str]]) -> Path:
    """Write a minimal valid PDF: one Helvetica text line per list entry, one list per page."""
    objects: list[bytes] = []

    def add(body: str) -> int:
        objects.append(body.encode("latin-1"))
        return len(objects)

    font = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []
    pages_id = len(objects) + 1 + 2 * len(pages)  # reserved: the /Pages object is added last
    for lines in pages:
        stream = "BT /F1 12 Tf 14 TL 50 740 Td " + " T* ".join(f"({ln}) Tj" for ln in lines) + " ET"
        content = add(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        page_ids.append(
            add(
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 792] /Contents {content} 0 R "
                f"/Resources << /Font << /F1 {font} 0 R >> >> >>"
            )
        )
    kids = " ".join(f"{i} 0 R" for i in page_ids)
    assert add(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>") == pages_id
    catalog = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))
    return path


SAMPLE_PAGES = [
    ["I. Policy Statement", "Staff may borrow equipment for official work.", "II. Guidelines"],
    ["Return items within two weeks.", "Ask the supervisor if unsure."],
]


@pytest.fixture()
def sample_pdf(tmp_path: Path) -> Path:
    return _make_pdf(tmp_path / "sample.pdf", SAMPLE_PAGES)


def _cfg(**over):
    base = dict(pdf_reader="pypdf", ocr_enabled=False, ocr_min_chars_per_page=100, ocr_dpi=300)
    base.update(over)
    return SimpleNamespace(**base)


# ----------------------------------------------------------------------------- setting and defaults
def test_default_reader_is_pypdf() -> None:
    assert Settings.model_fields["pdf_reader"].default == "pypdf"


def test_pypdf_default_path_reads_a_real_pdf(sample_pdf: Path) -> None:
    with patch.object(ocr_fallback, "get_settings", return_value=_cfg()):
        pages = ocr_fallback.extract_pdf_pages(sample_pdf)
    assert len(pages) == 2
    assert "Staff may borrow equipment" in pages[0] and "Return items within two weeks." in pages[1]


def test_pdfium_reads_the_same_real_pdf(sample_pdf: Path) -> None:
    with patch.object(ocr_fallback, "get_settings", return_value=_cfg(pdf_reader="pdfium")):
        pages = ocr_fallback.extract_pdf_pages(sample_pdf)
    assert len(pages) == 2
    assert pages[0].splitlines()[0] == "I. Policy Statement"
    assert "\r" not in pages[0] and "Return items within two weeks." in pages[1]


def test_setting_chooses_the_reader_and_the_argument_overrides_it(sample_pdf: Path) -> None:
    seen: list[str] = []

    def spy(path, name):
        seen.append(name)
        return ["x" * 200]

    with patch.object(ocr_fallback, "_direct_page_texts", side_effect=spy):
        with patch.object(ocr_fallback, "get_settings", return_value=_cfg(pdf_reader="pdfium")):
            ocr_fallback.extract_pdf_pages(sample_pdf)
            ocr_fallback.extract_pdf_pages(sample_pdf, reader="pypdf")
        with patch.object(
            ocr_fallback, "get_settings", return_value=SimpleNamespace(ocr_enabled=False)
        ):
            ocr_fallback.extract_pdf_pages(
                sample_pdf
            )  # a settings object without the field means pypdf
    assert seen == ["pdfium", "pypdf", "pypdf"]


def test_load_bytes_passes_the_reader_through(sample_pdf: Path) -> None:
    with (
        patch.object(loaders, "build_page_spans", return_value=[]),
        patch(
            "ask_bpl_orchestrator.ingest.ocr_fallback.extract_pdf_pages",
            return_value=["Some text."],
        ) as extract,
    ):
        loaders.load_bytes(sample_pdf, pdf_reader="pdfium")
        loaders.load_bytes(sample_pdf)
    assert extract.call_args_list[0].kwargs == {"reader": "pdfium"}
    assert extract.call_args_list[1].kwargs == {"reader": None}


# ----------------------------------------------------------------------------- fail loudly, never fall back
def test_unknown_reader_name_raises(sample_pdf: Path) -> None:
    with pytest.raises(ValueError, match="Unknown PDF reader"):
        ocr_fallback._direct_page_texts(sample_pdf, "pdfminer")
    with (
        patch.object(ocr_fallback, "get_settings", return_value=_cfg(pdf_reader="Pdfium")),
        pytest.raises(ValueError),
    ):
        ocr_fallback.extract_pdf_pages(sample_pdf)  # names are exact; no silent default


def test_missing_pypdfium2_raises_and_does_not_fall_back(
    sample_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        sys.modules, "pypdfium2", None
    )  # makes "import pypdfium2" raise ImportError
    with pytest.raises(RuntimeError, match="pypdfium2"):
        ocr_fallback._direct_page_texts(sample_pdf, "pdfium")


# ----------------------------------------------------------------------------- pdfium text normalisation
class _FakeTextPage:
    def __init__(self, raw: str) -> None:
        self.raw, self.closed = raw, False

    def get_text_range(self) -> str:
        return self.raw

    def close(self) -> None:
        self.closed = True


def _fake_page(raw: str):
    tp = _FakeTextPage(raw)
    return SimpleNamespace(get_textpage=lambda: tp), tp


def test_pdfium_hyphen_marker_becomes_a_hyphen_not_a_noncharacter() -> None:
    page, _ = _fake_page("The Anti\ufffeHarassment Policy and day\ufffeto\ufffeday work")
    text = ocr_fallback._pdfium_page_text(page)
    assert text == "The Anti-Harassment Policy and day-to-day work"
    assert "\ufffe" not in text


def test_pdfium_text_matches_pypdf_normalisation_and_closes_the_text_page() -> None:
    page, tp = _fake_page("  Line one\r\nLine two\rLine three \uf0b7 \n")
    assert ocr_fallback._pdfium_page_text(page) == "Line one\nLine two\nLine three"
    assert tp.closed is True


# ----------------------------------------------------------------------------- OCR routing still works with pdfium
def test_thin_pdfium_page_goes_to_ocr_and_thick_page_does_not(
    sample_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    thick = "Policy sentence. " * 20
    ocr_calls: list[int] = []

    def fake_convert(path, first_page, last_page, dpi):
        ocr_calls.append(first_page)
        return ["image"]

    monkeypatch.setitem(sys.modules, "pdf2image", SimpleNamespace(convert_from_path=fake_convert))
    monkeypatch.setitem(
        sys.modules,
        "pytesseract",
        SimpleNamespace(image_to_string=lambda img: "  OCR TEXT \uf0b7 "),
    )
    cfg = _cfg(pdf_reader="pdfium", ocr_enabled=True)
    with (
        patch.object(ocr_fallback, "_direct_page_texts", return_value=[thick.strip(), "tiny"]),
        patch.object(ocr_fallback, "get_settings", return_value=cfg),
    ):
        pages = ocr_fallback.extract_pdf_pages(sample_pdf)
    assert ocr_calls == [2]
    assert pages == [thick.strip(), "OCR TEXT"]


def test_no_pages_returns_empty_list(sample_pdf: Path) -> None:
    with (
        patch.object(ocr_fallback, "_direct_page_texts", return_value=[]),
        patch.object(ocr_fallback, "get_settings", return_value=_cfg(ocr_enabled=True)),
    ):
        assert ocr_fallback.extract_pdf_pages(sample_pdf) == []


# ----------------------------------------------------------------------------- comparison tool
@pytest.mark.parametrize(
    "text, expected",
    [
        ("the fina l version", 1),
        ("wh o can o n", 3),
        ("Though the overal l responsibility", 1),
        (
            "a book, I read; b. The draft c. next",
            0,
        ),  # "a", capital I and list markers are not splits
        ("i.e. filters, e.g. Internet, condition/s", 0),  # abbreviations and slash forms
        ("don't can’t well-s", 0),  # contractions and hyphen forms
        (
            "T o p r o m o t e",
            8,
        ),  # letter-spaced run: every lower-case letter after the capital counts
    ],
)
def test_split_word_indicator(text: str, expected: int) -> None:
    result = reader_compare.ReaderResult("x", [text], text, [])
    assert len(result.split_samples()) == expected


def test_unusual_characters_are_counted_but_newlines_and_tabs_are_not() -> None:
    result = reader_compare.ReaderResult(
        "x", [], "ok\n\tfine \ufffe bad \ufffd and \uf0a7 bullet", []
    )
    assert result.odd_chars == Counter({"U+FFFE": 1, "U+FFFD": 1, "U+F0A7": 1})


def test_ligatures_do_not_count_as_different_content() -> None:
    a = reader_compare.ReaderResult("pypdf", [], "the \ufb01nal o\ufb00er", [])
    b = reader_compare.ReaderResult("pdfium", [], "the final offer", [])
    assert a.non_space == b.non_space


def test_thin_pages_use_the_ocr_threshold() -> None:
    result = reader_compare.ReaderResult("x", ["a" * 99, "a" * 100, ""], "", [])
    assert result.thin_pages == 2


def test_compare_on_a_real_pdf_finds_no_difference_between_readers(sample_pdf: Path) -> None:
    result = reader_compare.compare(sample_pdf)
    assert (result.only_pypdf, result.only_pdfium) == (0, 0)
    assert not result.heading_diff and not result.thin_diff
    assert "headings: pypdf" in result.text and "unusual characters" not in result.text


def test_compare_reports_content_lost_by_one_reader(sample_pdf: Path) -> None:
    def fake_read(path, name):
        text = "Policy and Procedure\nBorrow items." if name == "pypdf" else "\u00a0\nBorrow items."
        return reader_compare.ReaderResult(
            name, [text], text, [h.text for h in find_headings(text)]
        )

    with patch.object(reader_compare, "read_with", side_effect=fake_read):
        result = reader_compare.compare(sample_pdf)
    assert result.only_pypdf == len("PolicyandProcedure") and result.only_pdfium == 0
    assert "only in pypdf: 18" in result.text


def test_compare_reports_a_heading_one_reader_misses(sample_pdf: Path) -> None:
    def fake_read(path, name):
        text = (
            "Intro line.\n\nRelated Policies/Documents:\nSee the list."
            if name == "pypdf"
            else "Intro line."
        )
        heads = ["Related Policies/Documents"] if name == "pypdf" else []
        return reader_compare.ReaderResult(name, [text], text, heads)

    with patch.object(reader_compare, "read_with", side_effect=fake_read):
        result = reader_compare.compare(sample_pdf)
    assert (
        result.heading_diff is True
        and "headings only with pypdf: Related Policies/Documents" in result.text
    )


def test_summary_counts_and_names_the_pdfs_with_differences() -> None:
    ok = reader_compare.Comparison("t", 3, 1, False, False, 0, 0, "ok.pdf", 0)
    bad = reader_compare.Comparison("t", 5, 0, True, True, 18, 2, "bad.pdf", 4)
    summary = reader_compare.summarise([ok, bad])
    assert "pypdf 8 / pdfium 1" in summary
    assert "headings differ: 1" in summary and "thin (OCR-bound) pages differs: 1" in summary
    assert "only in pypdf output: 18; only in pdfium output: 2" in summary
    assert "unusual characters in pdfium text (all PDFs): 4" in summary
    assert summary.rstrip().endswith("bad.pdf")


def test_compare_cli_prints_a_summary_for_several_pdfs_and_rejects_a_missing_file(
    sample_pdf: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    second = _make_pdf(tmp_path / "second.pdf", [["Only one page here with enough words."]])
    assert reader_compare.main([str(sample_pdf), str(second)]) == 0
    out = capsys.readouterr().out
    assert "=== sample.pdf" in out and "=== second.pdf" in out and "SUMMARY over 2 PDFs" in out
    assert reader_compare.main([str(tmp_path / "missing.pdf")]) == 2


# ----------------------------------------------------------------------------- provenance report --reader
def test_provenance_report_passes_the_reader_to_the_loader(sample_pdf: Path) -> None:
    seen: list[dict] = []

    def fake_load(path, **kwargs):
        seen.append(kwargs)
        return "Short text without headings."

    cfg = SimpleNamespace(
        openai_embedding_model="text-embedding-3-small",
        chunk_size_tokens=400,
        chunk_overlap_tokens=100,
        chunk_strategy="sentence",
    )
    with (
        patch.object(provenance_report, "load_bytes", side_effect=fake_load),
        patch.object(provenance_report, "get_settings", return_value=cfg),
    ):
        provenance_report.report(sample_pdf, stand_in=True, reader="pdfium")
        provenance_report.report(sample_pdf, stand_in=True)
    assert seen == [{"pdf_reader": "pdfium"}, {}]


# ----------------------------------------------------------------------------- gaps found by the mutation check
def _fake_pdfium(pages: list[str], *, fail_on: int | None = None):
    state = {"document_closed": False}

    class Doc:
        def __init__(self, path: str) -> None:
            pass

        def __len__(self) -> int:
            return len(pages)

        def __getitem__(self, i: int):
            if fail_on == i:
                raise OSError("unreadable page")
            return _fake_page(pages[i])[0]

        def close(self) -> None:
            state["document_closed"] = True

    return SimpleNamespace(PdfDocument=Doc), state


def test_pdfium_document_is_closed_after_reading_and_after_a_failure(
    sample_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, state = _fake_pdfium(["one", "two"])
    monkeypatch.setitem(sys.modules, "pypdfium2", fake)
    assert ocr_fallback._direct_page_texts(sample_pdf, "pdfium") == ["one", "two"]
    assert state["document_closed"] is True

    fake, state = _fake_pdfium(["one", "two"], fail_on=1)
    monkeypatch.setitem(sys.modules, "pypdfium2", fake)
    with pytest.raises(OSError):
        ocr_fallback._direct_page_texts(sample_pdf, "pdfium")
    assert state["document_closed"] is True


def test_report_cli_passes_the_chosen_reader_to_the_report(sample_pdf: Path) -> None:
    with (
        patch.object(provenance_report, "report", return_value="ok") as report,
        patch.object(
            provenance_report,
            "get_settings",
            return_value=SimpleNamespace(chunk_strategy="sentence"),
        ),
    ):
        assert provenance_report.main(["--reader", "pdfium", str(sample_pdf)]) == 0
        assert provenance_report.main([str(sample_pdf)]) == 0
    assert report.call_args_list[0].kwargs["reader"] == "pdfium"
    assert report.call_args_list[1].kwargs["reader"] is None


def test_compare_reports_a_heading_only_pdfium_finds(sample_pdf: Path) -> None:
    def fake_read(path, name):
        text = "I. Policy Overview\nText."
        return reader_compare.ReaderResult(
            name, [text], text, ["I. Policy Overview"] if name == "pdfium" else []
        )

    with patch.object(reader_compare, "read_with", side_effect=fake_read):
        result = reader_compare.compare(sample_pdf)
    assert (
        result.heading_diff is True
        and "headings only with pdfium: I. Policy Overview" in result.text
    )


def test_compare_flags_a_page_that_only_one_reader_sees_as_thin(sample_pdf: Path) -> None:
    def fake_read(path, name):
        pages = ["x" * 102] if name == "pypdf" else ["x" * 99]  # pdfium's page would be sent to OCR
        return reader_compare.ReaderResult(name, pages, pages[0], [])

    with patch.object(reader_compare, "read_with", side_effect=fake_read):
        result = reader_compare.compare(sample_pdf)
    assert result.thin_diff is True and "thin pages (<100 chars): 0 / 1" in result.text
