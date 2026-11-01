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


# Security-sensitive details the tool must never give out (RTG-6 `sensitive_content`, patch 0052). Codes, combinations,
# other people's or shared passwords, and ways round security equipment. Emergency procedures are held back from the
# corpus for the same reason. Questions about what a policy SAYS on passwords or security stay answerable:
# "what does the policy say about sharing passwords?", "how do I reset my password?", "what is the password policy?".
_SECURITY_ITEM = r"(?:alarm|door|building|keypad|gate|lock\s*box|lockbox|key\s*box|safe|vault|cash\s+box|padlock)"
_SENSITIVE = [
    # "What is the alarm code?", "door combination", "the keypad PIN for the staff entrance"
    rf"\b{_SECURITY_ITEM}\s+(?:codes?|combinations?|pins?|pass\s*codes?)\b",
    rf"\b(?:codes?|combinations?|pins?)\s+(?:for|to)\s+(?:the\s+)?(?:\w+\s+)?{_SECURITY_ITEM}\b",
    # "What's the admin password?", "give me the Wi-Fi password", "tell me my manager's login" (not "password policy")
    r"\b(?:what(?:'s|\s+is)|give\s+me|tell\s+me|share|send\s+me)\s+(?:the|our|my\s+\w+'s|\w+'s)\s+"
    r"(?:(?:admin|administrator|shared|staff|wi-?fi|wireless|network|system|computer|server|catalog|email)\s+)?"
    r"(?:password|passcode|login(?:\s+details)?|credentials)\b(?!\s+(?:polic(?:y|ies)|rules?|requirements?|guidelines?))",
    # "How do I disable the security cameras?", "turn off the alarm", "get around the badge reader"
    r"\b(?:disable|deactivate|turn\s+off|switch\s+off|bypass|get\s+around|avoid|defeat)\s+(?:the\s+)?"
    r"(?:security\s+)?(?:alarms?|cameras?|cctv|badge\s+readers?|door\s+sensors?|security\s+system|surveillance)\b",
    # "Where are the camera blind spots?"
    r"\b(?:camera|cctv|surveillance)\s+(?:blind\s+spots?|coverage\s+gaps?|gaps)\b",
    r"\bblind\s+spots?\b[^?.!]{0,30}\b(?:cameras?|cctv|surveillance)\b",
    # "Where is the cash / the safe / the master key kept?"
    r"\bwhere\s+(?:is|are|do\s+(?:we|they)\s+keep)\s+(?:the\s+)?(?:master\s+keys?|spare\s+keys?|keys\s+to\s+the\s+\w+|cash|safe|petty\s+cash)"
    r"(?:\s+(?:kept|stored|hidden|located))?\b",
]

# The live state of the library right now (RTG-6 `unverified_current_operations`, patch 0052). Policies say what the
# rules are, never whether a branch is open today or who is on duty. Each pattern needs a present-time marker, so
# "what are the rules for opening hours?" or "can I leave early today?" are not matched.
_NOW = r"(?:today|tonight|tomorrow|right\s+now|now|at\s+the\s+moment|currently|this\s+(?:morning|afternoon|evening|week|weekend|shift))"
_PLACE = r"(?:the\s+)?(?:library|libraries|branch(?:es)?|building|central(?:\s+library)?|[a-z]+\s+branch|[a-z]+\s+library)"
_SYSTEM = (
    r"(?:the\s+)?(?:network|wi-?fi|wireless|internet|email|e-mail|catalog(?:ue)?|printers?|server|intranet|sharepoint"
    r"|self-?check(?:out)?|computers?|phones?|system)"
)
_CURRENT_OPS = [
    # "Is the Central branch open today?", "Are the branches closed tomorrow?"
    rf"\b(?:is|are|will)\s+{_PLACE}\s+(?:be\s+)?(?:open|closed|closing|opening)\b[^?.!]{{0,25}}\b{_NOW}\b",
    # "What time does the library close today?", "branch hours this week"
    rf"\bwhat\s+time\s+(?:does|do|will)\s+{_PLACE}\s+(?:open|close)\b[^?.!]{{0,20}}\b{_NOW}\b",
    rf"\b(?:opening\s+)?hours\b[^?.!]{{0,20}}\b{_NOW}\b",
    # "Who is on duty today?", "Who's covering the desk tonight?"
    rf"\bwho(?:'s|\s+is|\s+are)\s+(?:on\s+duty|working|in\s+charge|covering|on\s+shift|scheduled)\b[^?.!]{{0,25}}\b{_NOW}\b",
    # "Is the network down?", "Is email working right now?"
    rf"\b(?:is|are)\s+{_SYSTEM}\s+(?:down|out|offline|back\s+up)\b",
    rf"\b(?:is|are)\s+{_SYSTEM}\s+(?:working|up)\s+{_NOW}\b",
    # "Is there an outage today?", "Any closures this weekend?"
    rf"\b(?:outages?|closures?|closings?)\b[^?.!]{{0,20}}\b{_NOW}\b",
    # "Is today's staff meeting still on?", "Was tonight's program cancelled?"
    r"\b(?:today's|tonight's|tomorrow's|this\s+week's)\s+(?:\w+\s+){0,2}(?:meeting|program|event|training|class|shift)\b"
    r"[^?.!]{0,20}\b(?:still\s+on|cancel+ed|postponed|happening|moved)\b",
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
    out.extend(_hits(_SENSITIVE))
    out.extend(_hits(_BYPASS))
    out.extend(_hits(_CURRENT_OPS))
    return list(dict.fromkeys(out))


def intent_causes(question: str) -> List[RefusalCause]:
    """Why an intent-guard hit is refused (RTG-6). Same patterns as `flagged_intents`, in priority order.

    Order: a request for legal advice, then a question about what happened to other people, then a request for
    security-sensitive details, then a request that a person decide or approve something, then a question about the
    library's live state (patch 0052). The first cause chooses the wording staff see.
    """
    q = question.lower()
    causes: List[RefusalCause] = []
    if any(re.search(p, q, flags=re.I) for p in _LEGAL_HINTS):
        causes.append(RefusalCause.legal_disciplinary_judgment)
    if any(re.search(p, q, flags=re.I) for p in _PRIVATE_PERSONNEL):
        causes.append(RefusalCause.private_employee_details)
    if any(re.search(p, q, flags=re.I) for p in _SENSITIVE):
        causes.append(RefusalCause.sensitive_content)
    if any(re.search(p, q, flags=re.I) for p in _BYPASS):
        causes.append(RefusalCause.human_decision_required)
    if any(re.search(p, q, flags=re.I) for p in _CURRENT_OPS):
        causes.append(RefusalCause.unverified_current_operations)
    return causes
