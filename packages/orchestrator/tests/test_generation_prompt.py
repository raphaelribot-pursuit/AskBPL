"""System prompt content for policy calculation behavior."""

from ask_bpl_orchestrator.services.generation import SYSTEM_PROMPT


def test_system_prompt_includes_policy_calculation_section():
    assert "POLICY APPLICATION — CALCULATIONS AND ESTIMATES" in SYSTEM_PROMPT
    # The prompt requires this exact disclaimer on every calculation, which is what
    # keeps an estimate from being presented as the staff member's official balance.
    # The prompt hard-wraps lines, so compare with whitespace collapsed.
    flat = " ".join(SYSTEM_PROMPT.split())
    assert (
        "Note: This is an estimate based on the policy formula. "
        "For your official balance, please contact Human Resources."
    ) in flat
    assert "End EVERY calculation with this disclaimer" in flat


def test_system_prompt_asks_for_details_before_calculating():
    assert "need more information before calculating" in SYSTEM_PROMPT
