"""Read-only comparison of the two PDF text readers (patch 0015).

    askbpl-reader-compare "path/to/Policy.pdf" [more.pdf ...]

For each PDF it extracts the selectable text with ``pypdf`` (the current reader) and with ``pdfium`` (pypdfium2) and
prints what would change if ``PDF_READER=pdfium`` were used: split-word artefacts, characters present in only one
reader's output, pages with little text (these trigger OCR), and the confident headings each reader yields.

No database, no Pinecone, no embeddings, no API keys, no OCR. Nothing is stored. The split-word figure is an
approximate indicator (isolated lower-case single letters other than "a"), not an exact count: read the samples.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ask_bpl_orchestrator.ingest.ocr_fallback import _direct_page_texts, _merge_pages
from ask_bpl_orchestrator.ingest.provenance import find_headings

READERS = ("pypdf", "pdfium")
# Same default as OCR_MIN_CHARS_PER_PAGE: a page below it would be sent to OCR.
THIN_PAGE_CHARS = 100

# An isolated single lower-case letter that is not the word "a" and not a list marker ("b."), an abbreviation
# ("i.e.", "e.g."), a slash form ("condition/s"), a contraction or a hyphenation.
_SPLIT_LETTER = re.compile(r"(?<![\w'\u2019\-./(\[])[b-z](?![\w'\u2019\-./)\]:])")


@dataclass
class ReaderResult:
    name: str
    pages: list[str]
    text: str
    headings: list[str]

    @property
    def non_space(self) -> Counter:
        # NFKC so the ligatures pypdf keeps ("\ufb01" for "fi") match the letters pdfium writes; what is left is real.
        return Counter(ch for ch in unicodedata.normalize("NFKC", self.text) if not ch.isspace())

    @property
    def thin_pages(self) -> int:
        return sum(1 for p in self.pages if len(p) < THIN_PAGE_CHARS)

    @property
    def odd_chars(self) -> Counter:
        """Control, format, unassigned, private-use and replacement characters (newline and tab are fine)."""
        return Counter(
            f"U+{ord(ch):04X}"
            for ch in self.text
            if ch not in "\n\t"
            and (unicodedata.category(ch) in {"Cc", "Cf", "Cn", "Co", "Cs"} or ch == "\ufffd")
        )

    def split_samples(self) -> list[str]:
        return [
            " ".join(self.text[max(0, m.start() - 10) : m.end() + 10].split())
            for m in _SPLIT_LETTER.finditer(self.text)
        ]


def read_with(path: Path, name: str) -> ReaderResult:
    pages = _direct_page_texts(path, name)
    text = _merge_pages(pages)
    return ReaderResult(name, pages, text, [h.text for h in find_headings(text.strip())])


@dataclass
class Comparison:
    text: str
    split_pypdf: int
    split_pdfium: int
    heading_diff: bool
    thin_diff: bool
    only_pypdf: int
    only_pdfium: int
    name: str = ""
    odd_pdfium: int = 0


def compare(path: Path, *, samples: int = 4) -> Comparison:
    a, b = (read_with(path, n) for n in READERS)
    only_a = sum((a.non_space - b.non_space).values())
    only_b = sum((b.non_space - a.non_space).values())
    sa, sb = a.split_samples(), b.split_samples()
    head_a, head_b = Counter(a.headings), Counter(b.headings)
    lost = sorted((head_a - head_b).elements())
    gained = sorted((head_b - head_a).elements())
    lines = [
        f"=== {path.name}",
        f"  pages: {len(a.pages)} pypdf / {len(b.pages)} pdfium   thin pages (<{THIN_PAGE_CHARS} chars): "
        f"{a.thin_pages} / {b.thin_pages}",
        f"  non-space characters: {sum(a.non_space.values())} pypdf / {sum(b.non_space.values())} pdfium   "
        f"only in pypdf: {only_a}   only in pdfium: {only_b}",
        f"  split-word indicator (approx.): pypdf {len(sa)} / pdfium {len(sb)}",
        f"  headings: pypdf {len(a.headings)} / pdfium {len(b.headings)}",
    ]
    for label, odd in (("pypdf", a.odd_chars), ("pdfium", b.odd_chars)):
        if odd:
            lines.append(
                f"  unusual characters in {label} text: "
                + ", ".join(f"{k} x{v}" for k, v in sorted(odd.items()))
            )
    if lost:
        lines.append("  headings only with pypdf: " + " | ".join(lost))
    if gained:
        lines.append("  headings only with pdfium: " + " | ".join(gained))
    for label, found in (("pypdf", sa), ("pdfium", sb)):
        if found:
            lines.append(f"  {label} samples: " + " ; ".join(found[:samples]))
    return Comparison(
        "\n".join(lines),
        len(sa),
        len(sb),
        bool(lost or gained),
        a.thin_pages != b.thin_pages,
        only_a,
        only_b,
        path.name,
        sum(b.odd_chars.values()),
    )


def summarise(results: list[Comparison]) -> str:
    return "\n".join(
        [
            f"=== SUMMARY over {len(results)} PDFs (selectable text only; nothing stored)",
            f"  split-word indicator: pypdf {sum(r.split_pypdf for r in results)} / "
            f"pdfium {sum(r.split_pdfium for r in results)}",
            f"  PDFs where the confident headings differ: {sum(r.heading_diff for r in results)}",
            f"  PDFs where the number of thin (OCR-bound) pages differs: {sum(r.thin_diff for r in results)}",
            f"  characters only in pypdf output: {sum(r.only_pypdf for r in results)}; "
            f"only in pdfium output: {sum(r.only_pdfium for r in results)} (ligatures normalised)",
            f"  unusual characters in pdfium text (all PDFs): {sum(r.odd_pdfium for r in results)}",
            "  PDFs where either reader has text the other lacks: "
            + (", ".join(r.name for r in results if r.only_pypdf or r.only_pdfium) or "none"),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare pypdf and pdfium text for PDFs (read-only, nothing stored)."
    )
    parser.add_argument("pdfs", nargs="+", type=Path)
    parser.add_argument(
        "--samples", type=int, default=4, help="split-word samples shown per reader"
    )
    args = parser.parse_args(argv)
    results: list[Comparison] = []
    for pdf in args.pdfs:
        if not pdf.is_file():
            print(f"not a file: {pdf}", file=sys.stderr)
            return 2
        result = compare(pdf, samples=args.samples)
        results.append(result)
        print(result.text)
        print()
    if len(results) > 1:
        print(summarise(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
