"""Intent guardrail for prompts that imply legal bypass or prohibited use (TRD-GRD-3)."""

from __future__ import annotations

import re
from typing import List

_LEGAL_HINTS = [
    r"\blegal advice\b",
    r"\binterpret (?:the )?law\b",
    r"\battorney\b",
    r"\blawsuit\b",
]
_BYPASS = [
    r"\bbypass\b.*\b(HR|IT|Finance|Legal)\b",
    r"\bagree for me\b",
    r"\bmake the decision\b",
    r"\bgive(?: me)? .* approval\b",
    r"\bautomated .* decision\b",
]


def flagged_intents(question: str) -> List[str]:
    q = question.lower()
    out: List[str] = []

    def _hits(patterns: List[str]):
        hits: List[str] = []
        for p in patterns:
            if re.search(p, q, flags=re.I):
                hits.append(p)
        return hits

    out.extend(_hits(_LEGAL_HINTS))
    out.extend(_hits(_BYPASS))
    return list(dict.fromkeys(out))
