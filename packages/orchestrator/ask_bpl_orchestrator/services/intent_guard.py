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

# Questions about what HAS HAPPENED to other people (who was disciplined, how many were fired).
# That is private personnel history, never policy text (PRD RTG-6, Document 06 s.5 and test SEC-08).
#
# Deliberately narrow. Each pattern needs a PAST-event auxiliary or a history noun, so questions about
# what a policy SAYS stay answerable: "what happens if I violate this?", "can an employee be fired
# for...?", "how many warnings before termination?" and "who can be disciplined?" are not matched.
# Wording-based, so a paraphrase can slip through; it is a floor, not a complete defence.
_PEOPLE = (
    r"(?:employees?|staff(?:\s+members?)?|people|persons?|workers?|librarians?|managers?|supervisors?"
    r"|volunteers?|coworkers?|colleagues?)"
)
_ACTION = (
    r"(?:disciplined|fired|terminated|dismissed|suspended|reprimanded|written\s+up|let\s+go"
    r"|sanctioned|punished)"
)
_PRIVATE_PERSONNEL = [
    # "Has anyone ever been disciplined for ...", "Was any employee fired for ..."
    rf"\b(?:has|have|had|was|were|did)\s+(?:anyone|anybody|someone|somebody|any\s+{_PEOPLE})\b"
    rf"[^?.!]{{0,50}}\b{_ACTION}\b",
    # "How many staff have been fired ..." (past/perfect only; "how many staff can be fired" is a policy question)
    rf"\bhow\s+many\s+{_PEOPLE}\s+(?:have|has|were|had|got|been|ever)\b[^?.!]{{0,30}}\b{_ACTION}\b",
    # "Who was fired for ..." at the start of a question or sentence ("staff who were suspended" is not matched)
    rf"(?:^|[.?!]\s+)who\s+(?:was|were|got|has\s+been|have\s+been)\s+(?:\w+\s+){{0,2}}{_ACTION}\b",
    # "past disciplinary cases", "previous termination records"
    r"\b(?:past|previous|prior|recent)\s+(?:disciplinary|termination)\s+(?:cases?|records?|incidents?|history)\b",
    # "Is my manager being investigated?"
    rf"\b(?:is|was|are|were)\s+(?:my\s+)?(?:coworker|colleague|manager|supervisor|boss|someone|anyone)\b"
    r"[^?.!]{0,30}\b(?:under\s+investigation|being\s+investigated)\b",
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
    out.extend(_hits(_PRIVATE_PERSONNEL))
    out.extend(_hits(_BYPASS))
    return list(dict.fromkeys(out))


def intent_causes(question: str) -> List[RefusalCause]:
    """Why an intent-guard hit is refused (RTG-6). Same patterns as `flagged_intents`, in priority order.

    Order: a request for legal advice, then a question about what happened to other people, then a
    request that a person decide or approve something. The first cause chooses the wording staff see.
    The guard has no pattern for sensitive content or for current-operations questions yet.
    """
    q = question.lower()
    causes: List[RefusalCause] = []
    if any(re.search(p, q, flags=re.I) for p in _LEGAL_HINTS):
        causes.append(RefusalCause.legal_disciplinary_judgment)
    if any(re.search(p, q, flags=re.I) for p in _PRIVATE_PERSONNEL):
        causes.append(RefusalCause.private_employee_details)
    if any(re.search(p, q, flags=re.I) for p in _BYPASS):
        causes.append(RefusalCause.human_decision_required)
    return causes
