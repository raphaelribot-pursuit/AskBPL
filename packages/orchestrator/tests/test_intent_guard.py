"""Intent guard regression tests (TRD-GRD-3)."""

from ask_bpl_orchestrator.services.intent_guard import flagged_intents


def test_clean_policy_question_not_flagged():
    assert flagged_intents("What is the gift acceptance threshold?") == []


def test_legal_advice_flagged():
    flags = flagged_intents("Can you give me legal advice on this HR matter?")
    assert flags


def test_bypass_hr_flagged():
    flags = flagged_intents("How can I bypass HR approval for this gift?")
    assert flags


def test_leave_accrual_calculation_not_flagged():
    assert flagged_intents("How much annual leave have I earned so far?") == []


def test_leave_accrual_with_start_date_not_flagged():
    q = "I started working at BPL in January 2024. How much annual leave have I accumulated?"
    assert flagged_intents(q) == []


def test_decision_making_vacation_not_blocked_by_guard():
    # Decision-making is handled by the model prompt, not intent_guard.
    assert flagged_intents("Should I take my vacation next month or save it?") == []


# --------------------------------------------------------------------------------------------- patch 0069: wider legal guard
import pytest as _pytest  # noqa: E402

from ask_bpl_orchestrator.services.intent_guard import intent_causes as _causes  # noqa: E402
from ask_bpl_orchestrator.services.refusal import RefusalCause as _Cause  # noqa: E402


@_pytest.mark.parametrize("q", [
    "What are my legal rights if I'm fired?",
    "Do I have a legal case against my supervisor?",
    "Can I sue the library?",
    "Could I sue my manager for this?",
    "Was I wrongfully terminated?",
    "Is it legal for my manager to read my email?",
    "Should I get a lawyer?",
    "What legal options do I have after a suspension?",
])
def test_asking_for_ones_legal_position_gets_the_legal_refusal(q: str) -> None:
    assert _causes(q)[:1] == [_Cause.legal_disciplinary_judgment], q


@_pytest.mark.parametrize("q", [
    "Who counts as a child's legal guardian?",
    "Is Juneteenth a legal holiday?",
    "Do I use my legal name on the form?",
    "What are my rights under the FMLA policy?",
    "What does the policy say about legal holidays?",
    "Can an employee be fired for being late?",
    "What happens if a parent or legal guardian cannot be reached?",
])
def test_policy_questions_that_mention_legal_words_still_reach_the_search(q: str) -> None:
    assert _cause_free(q), q


def _cause_free(q: str) -> bool:
    return _Cause.legal_disciplinary_judgment not in _causes(q)
