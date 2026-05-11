"""Token-based chunk splitter (TRD-internal defaults)."""

from __future__ import annotations

from typing import List

import tiktoken


def split_text(text: str, *, model_name: str, chunk_size: int, overlap: int) -> List[str]:
    try:
        enc = tiktoken.encoding_for_model(model_name)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")

    tokens = enc.encode(text.strip())
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

    return slices if slices else [text.strip()]
