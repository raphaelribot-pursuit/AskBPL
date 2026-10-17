"""Where a chunk came from: page range and a conservative section heading (patch 0013; ING-11, GRD-4).

Two rules shape everything here.

1. A wrong location shown as a verified location is worse than none. The heading rule is strict and
   returns nothing when it is not confident; a chunk with no confident heading simply has no heading.
2. This module never changes chunk text or chunk boundaries. It only labels them, so retrieval is
   unaffected until the labelled documents are re-ingested, and even then only the labels differ.

Everything is offsets into ONE string: the text handed to the chunker, after ``.strip()``.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

MAX_HEADING_CHARS = 120  # the column is String(255); anything this long is not a heading anyway
MAX_COLON_HEADING_WORDS = 6
MAX_CAPS_HEADING_WORDS = 10

# Words allowed to be lower case inside a Title Case heading ("Carry-over of Annual Leave").
_SMALL_WORDS = frozenset(
    {"a", "an", "and", "or", "of", "the", "to", "for", "in", "on", "at", "by", "with", "vs", "&", "/", "-", "as"}
)
# A line starting with one of these is a continuation of the line above, never a heading of its own
# ("... DOCUMENTS AND POLICIES" wrapped onto "OR FORMS").
_CONTINUATION_STARTERS = frozenset({"or", "and", "of", "to", "for", "with", "&"})  # not "the"/"in": "THE COMMUNITY" is a heading

# Document-metadata labels. They end in a colon and look like headings but are not locations.
_METADATA_LABELS = frozenset(
    {
        "revision date", "revised", "effective date", "date issued", "issuing agency", "issued by",
        "supersedes", "supersedes policy", "supersedes policies", "supercedes policy", "supercedes policy #",
        "supersedes policy #", "related policy", "related policies", "related document", "related documents",
        "related public documents", "see also", "subject", "application", "policy #", "policy number",
        "policy name", "approved by", "approval",
    }
)

_ROMAN = r"(?:I{1,3}|IV|V|VI{0,3}|IX|X{1,3}|XI{0,3}|XIV|XV)"
_ROMAN_HEADING = re.compile(rf"^{_ROMAN}\.\s+\S")
_LIST_PREFIX = re.compile(r"^(?:[A-Za-z]|\d{1,2}|" + _ROMAN + r")[.)]\s+")
_PAGE_HEADING = re.compile(r"^Page (\d+)$")


@dataclass(frozen=True)
class Heading:
    offset: int  # start of the heading line in the chunked text
    text: str


@dataclass(frozen=True)
class PageSpan:
    number: int  # 1-based page number in the source PDF
    start: int   # char offset where this page's text starts
    end: int     # char offset where it ends (exclusive)


def _normalise(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _words(line: str) -> List[str]:
    return [w for w in re.split(r"\s+", line) if w]


def _strip_list_prefix(line: str) -> str:
    return _LIST_PREFIX.sub("", line, count=1)


def _is_all_caps(line: str) -> bool:
    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 4 and all(c.isupper() for c in letters)


def _is_title_case(words: Sequence[str]) -> bool:
    """Every word is capitalised (or an allowed small word, or starts with a non-letter)."""
    for i, word in enumerate(words):
        core = word.strip("()\"'“”‘’,;")
        if not core:
            continue
        if core.lower() in _SMALL_WORDS and i > 0:
            continue
        first = next((c for c in core if c.isalpha()), None)
        if first is None:  # "#", "&", numbers
            continue
        if not first.isupper():
            return False
    return True


def _is_colon_heading(line: str) -> bool:
    """Short, capitalised line ending in a colon: "Eligibility Requirements:", "A. PRIVATE FUNDRAISING:"."""
    if not line.endswith(":"):
        return False
    body = _strip_list_prefix(line[:-1].strip())
    if not body or not body[0].isalpha():
        return False  # (lower-case fragments such as "in circumstances such as the following:" fail Title Case below)
    words = _words(body)
    if not words or len(words) > MAX_COLON_HEADING_WORDS:
        return False  # long lines ending in a colon introduce a list
    if not _is_title_case(words):
        return False  # "Customers may NOT:" is a list lead-in, not a section
    return True


def _is_caps_heading(line: str) -> bool:
    body = _strip_list_prefix(line.rstrip(":").strip())
    words = _words(body)
    if not _is_all_caps(body) or not words or len(words) > MAX_CAPS_HEADING_WORDS:
        return False
    if words[0].lower() in _CONTINUATION_STARTERS:
        return False
    return True


def _is_roman_heading(line: str) -> bool:
    """"I. Policy Statement", "IV. Responsibilities:" - a numeral, then a short Title Case phrase."""
    if not _ROMAN_HEADING.match(line):
        return False
    body = line.split(".", 1)[1].strip().rstrip(":").strip()
    words = _words(body)
    return 0 < len(words) <= MAX_COLON_HEADING_WORDS and _is_title_case(words)


def _is_metadata_label(line: str) -> bool:
    return _normalise(line).rstrip(":").strip().lower() in _METADATA_LABELS


def _is_heading_line(line: str) -> bool:
    if not line or len(line) > MAX_HEADING_CHARS:
        return False
    if _is_metadata_label(line):
        return False
    return _is_roman_heading(line) or _is_colon_heading(line) or _is_caps_heading(line)


def find_headings(text: str) -> List[Heading]:
    """Headings the strict rule is confident about, with the offset of each in ``text``.

    Returns an empty list for a document with none. Never guesses: bold or large type (which is how
    some policies mark headings) is invisible in extracted text and is deliberately not inferred.
    """
    found: List[Heading] = []
    offset = 0
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = _normalise(raw)
        if _is_heading_line(line):
            heading = line
            consumed = 1
            # A heading that wrapped onto a second ALL-CAPS line beginning with a conjunction.
            if _is_all_caps(line.rstrip(":")) and i + 1 < len(lines):
                nxt = _normalise(lines[i + 1])
                if nxt and _is_all_caps(nxt) and _words(nxt)[0].lower() in _CONTINUATION_STARTERS:
                    heading = f"{line} {nxt}"
                    consumed = 2
            heading = heading.rstrip(":").strip()
            if heading and len(heading) <= MAX_HEADING_CHARS:
                found.append(Heading(offset=offset + (len(raw) - len(raw.lstrip())), text=heading))
            for k in range(consumed):
                offset += len(lines[i + k]) + 1
            i += consumed
            continue
        offset += len(raw) + 1
        i += 1
    return found


def heading_at(headings: Sequence[Heading], position: int) -> Optional[str]:
    """The nearest confident heading at or before ``position``; None before the first one."""
    if not headings:
        return None
    idx = bisect_right([h.offset for h in headings], position) - 1
    return headings[idx].text if idx >= 0 else None


def build_page_spans(fragments: Sequence[str], *, separator: str = "\n\n", lead: int = 0) -> List[PageSpan]:
    """Page spans for text built as ``separator.join(non-empty fragments)``, minus ``lead`` stripped chars.

    ``fragments`` has one entry per source page (empty string for a page with no text), so page numbers
    stay true to the PDF even when a page is blank.
    """
    spans: List[PageSpan] = []
    pos = 0
    first = True
    for number, frag in enumerate(fragments, start=1):
        if not frag:
            continue
        if not first:
            pos += len(separator)
        spans.append(PageSpan(number=number, start=pos - lead, end=pos + len(frag) - lead))
        pos += len(frag)
        first = False
    return spans


def page_at(spans: Sequence[PageSpan], position: int) -> Optional[int]:
    """Page holding the character at ``position`` (a position in a page break belongs to the next page)."""
    for span in spans:
        if position < span.end:
            return span.number
    return spans[-1].number if spans else None


def page_range(spans: Sequence[PageSpan], start: int, end: int) -> Tuple[Optional[int], Optional[int]]:
    """(first page, last page) a chunk covering [start, end) touches; (None, None) without page data."""
    if not spans or start is None or end is None:
        return None, None
    last_char = max(start, end - 1)
    return page_at(spans, start), page_at(spans, last_char)


def page_from_heading(heading: Optional[str]) -> Optional[int]:
    """A "Page 3" marker written by a validated scan review (patch 0009) is a page, not a section."""
    match = _PAGE_HEADING.match(heading or "")
    return int(match.group(1)) if match else None


def format_pages(page_start: Optional[int], page_end: Optional[int]) -> Optional[str]:
    """"p. 2" or "pp. 2-3" for display; None when unknown."""
    if page_start is None:
        return None
    if page_end is None or page_end == page_start:
        return f"p. {page_start}"
    return f"pp. {page_start}\u2013{page_end}"
