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
