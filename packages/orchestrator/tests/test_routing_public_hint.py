"""Staff must never see placeholder routing text (PRD RTG-7, RTG-4)."""

from __future__ import annotations

import pytest

from ask_bpl_orchestrator.services.routing_service import NEUTRAL_CONTACT_HINT, public_contact_hint


@pytest.mark.parametrize(
    "hint",
    [
        "Contact Audit Committee via General Counsel intake — TBD pending Selvon approval.",
        "TBD",
        "Contact the Materials Review Committee (pending approval)",
        "TODO: Selvon to provide BPL-specific resource",
        "",
        None,
        "   ",
    ],
)
def test_placeholder_hints_become_neutral_referral(hint) -> None:
    assert public_contact_hint(hint) == NEUTRAL_CONTACT_HINT


def test_confirmed_hint_passes_through_unchanged() -> None:
    assert public_contact_hint("Contact the IT Help Desk.") == "Contact the IT Help Desk."


def test_neutral_hint_has_no_internal_wording() -> None:
    lowered = NEUTRAL_CONTACT_HINT.lower()
    assert not any(w in lowered for w in ("tbd", "pending", "todo", "selvon"))
