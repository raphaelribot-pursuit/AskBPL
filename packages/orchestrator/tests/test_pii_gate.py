"""PII rejection gate regression tests (TRD-GRD-2)."""

from ask_bpl_orchestrator.services.pii_gate import rejects_input, scan_pii


def test_clean_policy_question_allowed():
    blocked, cats = rejects_input(
        "What is the fundraising policy timeline for approving donor gifts?",
    )
    assert not blocked
    assert cats == []


def test_ssn_blocked():
    text = "My id is Jane Doe employee id badge 8842 please check 123-45-6789"
    blocked, cats = rejects_input(text)
    assert blocked
    assert any("government_id" in c for c in cats)


def test_email_blocked():
    blocked, cats = rejects_input(
        "email me copies at legal.lead+case@bklynlibrary.org about gifts",
    )
    assert blocked
    assert "email_address" in cats


def test_scan_pii_phone():
    cats = scan_pii("Reach me anytime at +1 (718) 555-0199 about this policy.")
    assert "phone_number" in cats
