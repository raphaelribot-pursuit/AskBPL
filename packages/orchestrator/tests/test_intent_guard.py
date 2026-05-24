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
