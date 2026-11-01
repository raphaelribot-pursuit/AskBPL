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


def test_system_prompt_gives_staff_the_employee_rule_not_a_customer_rule():
    """Patch 0047 (ROB-CF-01; team decision 2026-11-01, option B): a staff asker gets the staff rule.

    The public Technology Use Policy says BPL "will release library records only as required by law" for customers;
    the staff Technology Usage Policy says employees have no expectation of privacy. Answers blended the two.
    """
    flat = " ".join(SYSTEM_PROMPT.split())
    assert "WHO THE RULE IS FOR" in SYSTEM_PROMPT
    assert "The person asking is a BPL staff member." in flat
    assert (
        "Never present a protection, right or duty written for customers or the public as if it applied to the "
        "staff member."
    ) in flat
    assert "give the employee rule" in flat


def test_system_prompt_asks_for_the_group_exception_the_excerpts_state():
    """Patch 0048 (PRD 19.4; ROB-UI-03): general discipline answers left out that union employees follow the Collective
    Bargaining Agreement, although that sentence is in the same passage as the four steps."""
    flat = " ".join(SYSTEM_PROMPT.split())
    assert "GROUPS THE EXCERPTS TREAT DIFFERENTLY" in SYSTEM_PROMPT
    assert "add one short sentence saying so, in the excerpts' own terms" in flat
    assert "Do not add groups or rules the excerpts do not state." in flat
