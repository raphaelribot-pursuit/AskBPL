"""Chunk splitter (TRD-IGN-2): sentence-aware by default, fixed token windows as the legacy strategy.

``strategy="sentence"`` (patch 0014, default) cuts at sentence ends and at every confident heading, so a chunk
starts where a sentence starts and carries one heading label for its whole length. ``strategy="token"`` is the
pre-0014 fixed-window behaviour, kept unchanged for rollback and before/after comparison.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Sequence

import tiktoken

_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class TextSegment:
    section_heading: str | None
    text: str
    # Where this piece sits in ``text.strip()`` (patch 0013). Labels only: they never change ``text``.
    # None when unknown, so callers and test doubles that build a TextSegment without them still work.
    start_char: int | None = None
    end_char: int | None = None


@dataclass(frozen=True)
class _Section:
    section_heading: str | None
    text: str
    offset: int  # where ``text`` starts in the stripped document


def _split_sections(text: str) -> List[_Section]:
    """Split markdown/plain text into sections by ATX headings."""
    stripped = text.strip()
    if not stripped:
        return []

    matches = list(_HEADING.finditer(stripped))
    if not matches:
        return [_Section(section_heading=None, text=stripped, offset=0)]

    def _body(start: int, end: int) -> tuple[int, str] | None:
        raw = stripped[start:end]
        body = raw.strip()
        return (start + (len(raw) - len(raw.lstrip())), body) if body else None

    segments: List[_Section] = []
    preamble = _body(0, matches[0].start())
    if preamble:
        segments.append(_Section(section_heading=None, text=preamble[1], offset=preamble[0]))

    for idx, match in enumerate(matches):
        heading = match.group(2).strip()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(stripped)
        body = _body(match.end(), end)
        if body:
            segments.append(_Section(section_heading=heading, text=body[1], offset=body[0]))

    return segments or [_Section(section_heading=None, text=stripped, offset=0)]


def _token_chunks(body: str, *, enc, chunk_size: int, overlap: int) -> List[tuple[str, int, int]]:
    """Fixed-size token windows over ``body``: (text, start_char, end_char) in ``body.strip()``.

    The window text is exactly what it was before 0013 (``enc.decode`` of the slice). The offsets come
    from decoding the whole body once with offsets, and are only used to label the window.
    """
    body = body.strip()
    tokens = enc.encode(body)
    if not tokens:
        return []

    try:
        _, token_offsets = enc.decode_with_offsets(tokens)
    except Exception:  # noqa: BLE001 offsets are a label; never let them break chunking
        token_offsets = None

    slices: List[tuple[str, int, int]] = []
    step = max(1, chunk_size - overlap)
    idx = 0
    length = len(tokens)
    while idx < length:
        end = min(length, idx + chunk_size)
        piece = tokens[idx:end]
        if piece:
            if token_offsets is not None and len(token_offsets) == length:
                start_char = token_offsets[idx]
                end_char = token_offsets[end] if end < length else len(body)
            else:
                start_char = end_char = -1
            slices.append((enc.decode(piece), start_char, end_char))
        idx += step
        if end == length:
            break
    return slices if slices else [(body, 0, len(body))]


# ----------------------------------------------------------------------------- sentence-aware strategy (0014)
MIN_SECTION_FRACTION = 10  # a section under 1/10 of a chunk (a heading with almost nothing under it) joins the next one

# A period after one of these does not end a sentence. Deliberately conservative: not splitting only makes a
# unit longer, while a false split would start a chunk mid-sentence, which is the thing this strategy removes.
_ABBREVIATIONS = frozenset(
    {
        "e.g", "i.e", "etc", "vs", "mr", "mrs", "ms", "dr", "st", "no", "nos", "inc", "co", "corp", "ltd", "jr", "sr",
        "dept", "approx", "est", "fig", "sec", "u.s", "a.m", "p.m", "ave", "blvd", "mt", "ext", "ref", "cf",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    }
)
_SENTENCE_GAP = re.compile(r"([.!?][\"'\u201d\u2019)\]]*)([ \t]*\n[ \t]*|[ \t]+)(?=[\"'\u201c\u2018(\[]*[A-Z0-9\u2022])")
_LIST_ITEM_START = re.compile(r"\n[ \t]*(?=(?:[\u2022\u25cf\u25aa*\-\u2013]|\(?\d{1,2}[.)]|\(?[A-Za-z][.)])[ \t]+\S)")
_WORD_BEFORE = re.compile(r"([A-Za-z][A-Za-z.]*|\d+)$")


def _is_real_sentence_end(text: str, gap_start: int) -> bool:
    """``text[gap_start]`` is a . ! or ? that a capital letter follows. Is it the end of a sentence?"""
    if text[gap_start] != ".":
        return True
    before = text[max(0, gap_start - 12) : gap_start]
    match = _WORD_BEFORE.search(before)
    if match is None:
        return True
    word = match.group(1)
    if word.lower() in _ABBREVIATIONS:
        return False
    if len(word) == 1 and word.isalpha():
        return False  # an initial ("J. Smith") or a list marker ("a. Staff")
    if word.isdigit():
        line_start = text.rfind("\n", 0, gap_start) + 1
        if text[line_start:gap_start].strip() == word:
            return False  # "1. Introduction": a list number, not the end of a sentence
    return True


_INLINE_BULLET = re.compile(r"[ \t]+(?=[\u2022\u25cf\u25aa])")
_LINE_START = re.compile(r"\n[ \t]*(?=\S)")
_WORD_START = re.compile(r"\s+(?=\S)")


def _unit_starts(block: str, level: int = 0) -> List[int]:
    """Offsets in ``block`` where a unit starts. Always begins with 0.

    level 0: sentences, list items and inline bullets. level 1: every line (for a run with no sentence ends, such
    as a flattened table). level 2: every word. Each level is used only for a unit the level above left too long.
    """
    starts = {0}
    if level == 0:
        for match in _SENTENCE_GAP.finditer(block):
            if _is_real_sentence_end(block, match.start(1)):
                starts.add(match.end())
        for pattern in (_LIST_ITEM_START, _INLINE_BULLET):
            starts.update(m.end() for m in pattern.finditer(block))
    else:
        starts.update(m.end() for m in (_LINE_START if level == 1 else _WORD_START).finditer(block))
    return sorted(starts)


def _count(enc, text: str) -> int:
    return len(enc.encode(text))


def _pack_block(
    block: str, base: int, *, enc, chunk_size: int, overlap: int, level: int = 0
) -> List[tuple[str, int, int]]:
    """Pack the sentences of one block into chunks of at most ``chunk_size`` tokens: (text, start, end).

    ``block`` is already stripped and ``base`` is where it starts in the document. Chunk text is the exact
    slice of the document. Overlap is whole trailing sentences, at most ``overlap`` tokens, inside this block only.
    """
    if not block:
        return []
    starts = _unit_starts(block, level)
    # unit i covers block[starts[i]:ends[i]] with trailing whitespace removed
    ends = [len(block[: (starts[i + 1] if i + 1 < len(starts) else len(block))].rstrip()) for i in range(len(starts))]
    n = len(starts)

    def span(i: int, j: int) -> str:  # sentences i..j inclusive
        return block[starts[i] : ends[j]]

    out: List[tuple[str, int, int]] = []
    i = 0  # first sentence of the chunk being built
    while i < n:
        if _count(enc, span(i, i)) > chunk_size:
            # One unit longer than a whole chunk (a flattened table, a run-on list): split it at the next finer
            # level (lines, then words). Only a single word longer than a chunk falls back to fixed windows.
            if level < 2:
                out.extend(
                    _pack_block(span(i, i), base + starts[i], enc=enc, chunk_size=chunk_size, overlap=overlap, level=level + 1)
                )
            else:
                for text, s, e in _token_chunks(span(i, i), enc=enc, chunk_size=chunk_size, overlap=overlap):
                    known = s >= 0
                    out.append((text, base + starts[i] + s if known else -1, base + starts[i] + e if known else -1))
            i += 1
            continue
        j = i
        while j + 1 < n and _count(enc, span(i, j + 1)) <= chunk_size:
            j += 1
        out.append((span(i, j), base + starts[i], base + ends[j]))
        if j + 1 >= n:
            break
        # Next chunk repeats the longest run of whole trailing sentences that fits in ``overlap`` tokens (never the
        # whole chunk, so it always moves forward), then shrinks that run if it would not leave room for the next one.
        nxt = j + 1
        start_next = next((m for m in range(i + 1, j + 1) if _count(enc, span(m, j)) <= overlap), nxt)
        while start_next < nxt and _count(enc, span(start_next, nxt)) > chunk_size:
            start_next += 1
        i = start_next
    return out


def _merge_tiny_sections(blocks: List[tuple[int, int]], text: str, enc, minimum: int) -> List[tuple[int, int]]:
    """Join a section with almost nothing in it to the one after it (a heading directly above another heading)."""
    merged: List[tuple[int, int]] = []
    carry_start: int | None = None
    for idx, (start, end) in enumerate(blocks):
        if carry_start is not None:
            start = carry_start
            carry_start = None
        is_last = idx + 1 == len(blocks)
        if not is_last and _count(enc, text[start:end]) < minimum:
            carry_start = start
            continue
        merged.append((start, end))
    return merged


def _sentence_segments(text: str, *, enc, chunk_size: int, overlap: int, boundaries: Sequence[int]) -> List[TextSegment]:
    stripped = text.strip()
    output: List[TextSegment] = []
    for section in _split_sections(text):
        lo, hi = section.offset, section.offset + len(section.text)
        cuts = sorted({b for b in boundaries if lo < b < hi})
        edges = [lo, *cuts, hi]
        pieces = [(a, b) for a, b in zip(edges, edges[1:]) if stripped[a:b].strip()]
        pieces = _merge_tiny_sections(pieces, stripped, enc, max(1, chunk_size // MIN_SECTION_FRACTION))
        for a, b in pieces:
            raw = stripped[a:b]
            body = raw.strip()
            lead = len(raw) - len(raw.lstrip())
            # Only the first piece of a markdown section carries that section's heading; later pieces (cut at a
            # confident heading) take their label from that heading at ingest time.
            heading = section.section_heading if a == lo else None
            for piece, s, e in _pack_block(body, a + lead, enc=enc, chunk_size=chunk_size, overlap=overlap):
                known = s >= 0
                output.append(
                    TextSegment(
                        section_heading=heading,
                        text=piece,
                        start_char=s if known else None,
                        end_char=e if known else None,
                    )
                )
    return output if output else [TextSegment(section_heading=None, text=stripped)]


def split_text(text: str, *, model_name: str, chunk_size: int, overlap: int) -> List[str]:
    """Legacy flat splitter — prefer ``split_text_with_sections``."""
    return [segment.text for segment in split_text_with_sections(text, model_name=model_name, chunk_size=chunk_size, overlap=overlap)]


def split_text_with_sections(
    text: str,
    *,
    model_name: str,
    chunk_size: int,
    overlap: int,
    encoder=None,
    strategy: str = "sentence",
    boundaries: Sequence[int] = (),
) -> List[TextSegment]:
    """``encoder`` is for tests only: any object with encode / decode / decode_with_offsets.

    ``strategy``: "sentence" (default) or "token" (the pre-0014 fixed windows). ``boundaries`` are offsets in
    ``text.strip()`` where a chunk must start (the confident headings); only the sentence strategy uses them.
    """
    if strategy not in ("sentence", "token"):
        raise ValueError(f"Unknown chunking strategy {strategy!r}; use 'sentence' or 'token'.")
    if encoder is not None:
        enc = encoder
    else:
        try:
            enc = tiktoken.encoding_for_model(model_name)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")

    if strategy == "sentence":
        return _sentence_segments(text, enc=enc, chunk_size=chunk_size, overlap=overlap, boundaries=boundaries)

    output: List[TextSegment] = []
    for section in _split_sections(text):
        for piece, start, end in _token_chunks(section.text, enc=enc, chunk_size=chunk_size, overlap=overlap):
            known = start >= 0
            output.append(
                TextSegment(
                    section_heading=section.section_heading,
                    text=piece,
                    start_char=section.offset + start if known else None,
                    end_char=section.offset + end if known else None,
                )
            )
    return output if output else [TextSegment(section_heading=None, text=text.strip())]
