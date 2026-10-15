"""Intent guardrail for prompts that imply legal bypass or prohibited use (TRD-GRD-3)."""

from __future__ import annotations

import re
from typing import List

from ask_bpl_orchestrator.services.refusal import RefusalCause

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


def intent_causes(question: str) -> List[RefusalCause]:
    """Why an intent-guard hit is refused (RTG-6). Same patterns as `flagged_intents`, in priority order.

    Legal-advice wording is reported before a request that a person decide or approve something.
    Only these two causes are detectable from wording alone; the guard has no pattern for named-person
    or disciplinary-history questions yet.
    """
    q = question.lower()
    causes: List[RefusalCause] = []
    if any(re.search(p, q, flags=re.I) for p in _LEGAL_HINTS):
        causes.append(RefusalCause.legal_disciplinary_judgment)
    if any(re.search(p, q, flags=re.I) for p in _BYPASS):
        causes.append(RefusalCause.human_decision_required)
    return causes
