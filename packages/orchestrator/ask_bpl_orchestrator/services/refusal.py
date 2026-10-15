"""Why a question was not answered (PRD RTG-6).

Two separate concerns live here and must stay separate:

* The CAUSE is internal. It goes to the structured log and nowhere a staff member can see it.
  UX specification: do not surface "why the model refused" with technical detection terms or
  classification labels.
* The MESSAGE is what staff read. Plain language, no labels. Several causes share one wording on
  purpose, so the wording cannot reveal which detector fired.

All user wording below is DRAFT pending BPL wording approval (PRD SAF-7), except the first sentence,
which is the sentence the UX specification gives for the refusal state.

Causes marked "not detected yet" exist so the message table is complete and the next patch only has to
add detection. Nothing in this patch assigns them.
"""

from __future__ import annotations

import enum
from typing import Dict, Optional


class RefusalCause(str, enum.Enum):
    # The eight causes named in RTG-6.
    absent_source = "absent_source"  # nothing relevant was found
    weak_evidence = "weak_evidence"  # something relevant, not enough
    ambiguous_authority = (
        "ambiguous_authority"  # relevant text exists but is not citable as current
    )
    private_employee_details = "private_employee_details"  # not detected yet
    sensitive_content = "sensitive_content"  # not detected yet
    legal_disciplinary_judgment = (
        "legal_disciplinary_judgment"  # asked for legal advice or a case judgment
    )
    unverified_current_operations = "unverified_current_operations"  # not detected yet
    human_decision_required = "human_decision_required"  # asked the system to decide or approve

    # A refusal that is not one of the eight: an answer was drafted but could not be tied to the excerpts.
    citation_unverified = "citation_unverified"

    # Technical failures. These are NOT refusals and are never returned as one.
    retrieval_unavailable = "retrieval_unavailable"
    generation_unavailable = "generation_unavailable"
    model_output_invalid = "model_output_invalid"


TECHNICAL_CAUSES = frozenset(
    {
        RefusalCause.retrieval_unavailable,
        RefusalCause.generation_unavailable,
        RefusalCause.model_output_invalid,
    }
)

# 503: we cannot do the work right now. 502: an upstream component answered with something unusable.
TECHNICAL_HTTP_STATUS: Dict[RefusalCause, int] = {
    RefusalCause.retrieval_unavailable: 503,
    RefusalCause.generation_unavailable: 503,
    RefusalCause.model_output_invalid: 502,
}

NEUTRAL_NEXT_STEP = "Your supervisor can point you to the right person."

# The UX specification's refusal sentence, used unchanged.
NOT_ENOUGH_INFORMATION = "I could not find enough approved policy information to answer reliably."

USER_MESSAGES: Dict[RefusalCause, str] = {
    # Absent source and weak evidence deliberately read the same.
    RefusalCause.absent_source: NOT_ENOUGH_INFORMATION,
    RefusalCause.weak_evidence: NOT_ENOUGH_INFORMATION,
    RefusalCause.ambiguous_authority: (
        "The policy information I have on this topic has not been confirmed as current, "
        "so I cannot answer it reliably. " + NEUTRAL_NEXT_STEP
    ),
    RefusalCause.legal_disciplinary_judgment: (
        "I cannot give legal advice or judge an individual employment or disciplinary situation. "
        + NEUTRAL_NEXT_STEP
    ),
    RefusalCause.human_decision_required: (
        "That is a decision for a person, so I cannot make it or approve it for you. "
        + NEUTRAL_NEXT_STEP
    ),
    RefusalCause.private_employee_details: (
        "I cannot share or discuss information about individual employees. " + NEUTRAL_NEXT_STEP
    ),
    RefusalCause.sensitive_content: "I cannot help with that here. " + NEUTRAL_NEXT_STEP,
    RefusalCause.unverified_current_operations: (
        "I cannot confirm day-to-day operations from policy documents. " + NEUTRAL_NEXT_STEP
    ),
    RefusalCause.citation_unverified: (
        "I could not confirm that an answer would match the approved policy text, so I am not giving one. "
        + NEUTRAL_NEXT_STEP
    ),
    # Technical failures: what happened to the staff member's request, never a policy conclusion.
    RefusalCause.retrieval_unavailable: (
        "Ask BPL cannot search the policies right now. Please try again in a few minutes."
    ),
    RefusalCause.generation_unavailable: (
        "Ask BPL cannot answer questions right now. Please try again in a few minutes."
    ),
    RefusalCause.model_output_invalid: (
        "Ask BPL could not put together a reliable answer this time. Please try asking again."
    ),
}


def user_message(cause: RefusalCause) -> str:
    return USER_MESSAGES[cause]


def is_technical(cause: RefusalCause) -> bool:
    return cause in TECHNICAL_CAUSES


def classify_retrieval_gate_failure(
    *,
    best_score: float,
    floor: float,
    excluded_best_score: float = 0.0,
) -> RefusalCause:
    """The retrieval gate found too little eligible evidence. Say which kind of "too little".

    * A relevant passage exists but may not be cited as current (draft, unconfirmed, superseded):
      ambiguous authority. This is the only case where the question WAS answerable in principle.
    * Nothing eligible reached the similarity floor: absent source.
    * Something reached the floor but the margin rule still failed: weak evidence.
    """
    if excluded_best_score >= floor:
        return RefusalCause.ambiguous_authority
    if best_score < floor:
        return RefusalCause.absent_source
    return RefusalCause.weak_evidence


def classify_generation_failure(
    *,
    output_usable: bool,
    refuse_flag: bool,
    answer: str,
) -> RefusalCause:
    """The model was called and its output did not become an answer. Say why.

    Called only when the citation gate has already said no, so what remains after the first three checks
    (no citations, a citation to something not retrieved, a citation to an ineligible document) is one
    cause: the answer cannot be tied to the excerpts. The order matters: an unusable reply is a
    technical failure, an explicit refusal is the model judging the excerpts insufficient (this is NOT a
    citation failure, which the old message wrongly claimed), and only the rest are citation failures.
    """
    if not output_usable:
        return RefusalCause.model_output_invalid
    if refuse_flag:
        return RefusalCause.weak_evidence
    if not (answer or "").strip():
        return RefusalCause.model_output_invalid
    return RefusalCause.citation_unverified


def stage_for(cause: RefusalCause) -> Optional[str]:
    """Where in the pipeline a generation-stage cause arose (log field only)."""
    if cause == RefusalCause.weak_evidence:
        return "model"
    if cause == RefusalCause.citation_unverified:
        return "citation_check"
    return None
