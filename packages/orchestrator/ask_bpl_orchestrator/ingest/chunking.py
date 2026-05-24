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


def _split_sections(text: str) -> List[TextSegment]:
    """Split markdown/plain text into sections by ATX headings."""
    stripped = text.strip()
    if not stripped:
        return []

    matches = list(_HEADING.finditer(stripped))
    if not matches:
        return [TextSegment(section_heading=None, text=stripped)]

    segments: List[TextSegment] = []
    preamble = stripped[: matches[0].start()].strip()
    if preamble:
        segments.append(TextSegment(section_heading=None, text=preamble))

    for idx, match in enumerate(matches):
        heading = match.group(2).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(stripped)
        body = stripped[start:end].strip()
        if body:
            segments.append(TextSegment(section_heading=heading, text=body))

    return segments or [TextSegment(section_heading=None, text=stripped)]


def _token_chunks(body: str, *, enc, chunk_size: int, overlap: int) -> List[str]:
    tokens = enc.encode(body.strip())
    if not tokens:
        return []

    slices: List[str] = []
    step = max(1, chunk_size - overlap)
    idx = 0
    length = len(tokens)
    while idx < length:
        end = min(length, idx + chunk_size)
        piece = tokens[idx:end]
        if piece:
            slices.append(enc.decode(piece))
        idx += step
        if end == length:
            break
    return slices if slices else [body.strip()]


def split_text(text: str, *, model_name: str, chunk_size: int, overlap: int) -> List[str]:
    """Legacy flat splitter — prefer ``split_text_with_sections``."""
    return [segment.text for segment in split_text_with_sections(text, model_name=model_name, chunk_size=chunk_size, overlap=overlap)]


def split_text_with_sections(
    text: str,
    *,
    model_name: str,
    chunk_size: int,
    overlap: int,
) -> List[TextSegment]:
    try:
        enc = tiktoken.encoding_for_model(model_name)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")

    output: List[TextSegment] = []
    for section in _split_sections(text):
        for piece in _token_chunks(section.text, enc=enc, chunk_size=chunk_size, overlap=overlap):
            output.append(TextSegment(section_heading=section.section_heading, text=piece))
    return output if output else [TextSegment(section_heading=None, text=text.strip())]
