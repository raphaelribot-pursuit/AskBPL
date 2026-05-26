"""System prompt content for policy calculation behavior."""

from ask_bpl_orchestrator.services.generation import SYSTEM_PROMPT


def test_system_prompt_includes_policy_calculation_section():
    assert "POLICY APPLICATION — CALCULATIONS AND ESTIMATES" in SYSTEM_PROMPT
    assert "official balance, please contact Human Resources" in SYSTEM_PROMPT
    assert "Never present a calculation as the staff member's official balance" in SYSTEM_PROMPT


def test_system_prompt_asks_for_details_before_calculating():
    assert "need more information before calculating" in SYSTEM_PROMPT
