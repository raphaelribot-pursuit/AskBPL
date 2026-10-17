"""Token-based chunk splitter with markdown section headings (TRD-IGN-2)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

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
) -> List[TextSegment]:
    """``encoder`` is for tests only: any object with encode / decode / decode_with_offsets."""
    if encoder is not None:
        enc = encoder
    else:
        try:
            enc = tiktoken.encoding_for_model(model_name)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")

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
