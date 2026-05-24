"""Token-aware recursive chunking (TRD-IGN-2)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import tiktoken
import yaml

from ingestion.policy_metadata import PROJECT_ROOT

logger = logging.getLogger(__name__)

CHUNKING_PATH = PROJECT_ROOT / "config" / "chunking.yaml"

HEADER_PATTERNS = (
    re.compile(r"^[IVX]+\.\s+", re.MULTILINE),
    re.compile(r"^[A-Z]\.\s+", re.MULTILINE),
    re.compile(r"^\d+\.\s+[A-Z]", re.MULTILINE),
    re.compile(r"^Subject:", re.MULTILINE),
    re.compile(r"^Policy #:", re.MULTILINE),
)


@dataclass(frozen=True)
class TextChunk:
    """One chunk ready for embedding."""

    text: str
    section: Optional[str]
    chunk_index: int


def load_chunking_config(path: Path = CHUNKING_PATH) -> dict:
    """Load chunking parameters from YAML."""
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _token_len(text: str, enc: tiktoken.Encoding) -> int:
    return len(enc.encode(text))


def _split_by_separator(text: str, separator: str) -> List[str]:
    if separator == "":
        return list(text)
    if separator == " ":
        return text.split(" ")
    # Preserve delimiter for paragraph/sentence splits where useful
    parts = text.split(separator)
    if len(parts) <= 1:
        return parts
    rebuilt: List[str] = []
    for idx, part in enumerate(parts):
        if idx < len(parts) - 1:
            rebuilt.append(part + separator)
        else:
            if part:
                rebuilt.append(part)
    return [p for p in rebuilt if p]


def _merge_splits(splits: List[str], chunk_size: int, enc: tiktoken.Encoding) -> List[str]:
    merged: List[str] = []
    current: List[str] = []
    current_len = 0
    for piece in splits:
        piece_len = _token_len(piece, enc)
        if piece_len > chunk_size:
            if current:
                merged.append("".join(current))
                current = []
                current_len = 0
            merged.append(piece)
            continue
        if current_len + piece_len <= chunk_size:
            current.append(piece)
            current_len += piece_len
        else:
            merged.append("".join(current))
            current = [piece]
            current_len = piece_len
    if current:
        merged.append("".join(current))
    return merged


def _recursive_split(text: str, separators: List[str], chunk_size: int, enc: tiktoken.Encoding) -> List[str]:
    if _token_len(text, enc) <= chunk_size:
        return [text] if text.strip() else []
    if not separators:
        # Hard split by tokens as last resort
        tokens = enc.encode(text)
        return [enc.decode(tokens[i : i + chunk_size]) for i in range(0, len(tokens), chunk_size)]

    separator = separators[0]
    rest = separators[1:]
    splits = _split_by_separator(text, separator)
    if len(splits) == 1:
        return _recursive_split(text, rest, chunk_size, enc)

    chunks: List[str] = []
    for split in splits:
        if _token_len(split, enc) <= chunk_size:
            chunks.append(split)
        else:
            chunks.extend(_recursive_split(split, rest, chunk_size, enc))
    return _merge_splits(chunks, chunk_size, enc)


def _apply_overlap(chunks: List[str], overlap: int, enc: tiktoken.Encoding) -> List[str]:
    if overlap <= 0 or len(chunks) <= 1:
        return chunks
    overlapped: List[str] = []
    prev_tail = ""
    for idx, chunk in enumerate(chunks):
        if idx == 0:
            overlapped.append(chunk)
            tokens = enc.encode(chunk)
            prev_tail = enc.decode(tokens[-overlap:]) if len(tokens) > overlap else chunk
            continue
        combined = (prev_tail + chunk).strip()
        overlapped.append(combined)
        tokens = enc.encode(combined)
        prev_tail = enc.decode(tokens[-overlap:]) if len(tokens) > overlap else combined
    return overlapped


def _find_section(text: str, chunk_start: int, full_text: str) -> Optional[str]:
    prefix = full_text[:chunk_start]
    lines = prefix.splitlines()
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        for pattern in HEADER_PATTERNS:
            if pattern.match(stripped):
                return stripped[:200]
        if len(stripped) < 120 and stripped.isupper():
            return stripped
    return None


def chunk_document(text: str, config: Optional[dict] = None) -> List[TextChunk]:
    """Split document text into overlapping token-aware chunks (TRD-IGN-2)."""
    cfg = config or load_chunking_config()
    chunk_size: int = int(cfg["chunk_size_tokens"])
    overlap: int = int(cfg["chunk_overlap_tokens"])
    separators: List[str] = list(cfg["separators"])
    encoding_name: str = str(cfg["encoding"])
    enc = tiktoken.get_encoding(encoding_name)

    raw_chunks = _recursive_split(text, separators, chunk_size, enc)
    raw_chunks = [c.strip() for c in raw_chunks if c.strip()]
    raw_chunks = _apply_overlap(raw_chunks, overlap, enc)

    result: List[TextChunk] = []
    cursor = 0
    for idx, chunk_text in enumerate(raw_chunks):
        start = text.find(chunk_text, cursor)
        if start == -1:
            start = cursor
        section = _find_section(chunk_text, start, text)
        result.append(TextChunk(text=chunk_text, section=section, chunk_index=idx))
        cursor = start + len(chunk_text)
    return result
