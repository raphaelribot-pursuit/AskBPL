"""PII rejection before retrieval (TRD-GRD-2)."""

from __future__ import annotations

import re
from typing import List

PII_REJECTION_MESSAGE = (
    "Your question appears to contain personal information. Please rephrase your question "
    "without including any personal details (names, contact information, IDs, etc.) and try again.\n\n"
    'For example: "What are the eligibility requirements for annual leave?"'
)

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}\b", re.I)
_PHONE = re.compile(r"(?:\+\d{1,3}[\s-]?)?(?:\(?\d{3}\)?[\s.-]?){2}\d{4}\b")
_SSN_LIKE = re.compile(r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b")


def scan_pii(text: str) -> List[str]:
    """Return matched PII category labels."""
    findings: List[str] = []
    if _EMAIL.search(text):
        findings.append("email_address")
    if _PHONE.search(text):
        findings.append("phone_number")
    if _SSN_LIKE.search(text):
        findings.append("government_id")
    if _name_with_email(text):
        findings.append("name_with_identifier")
    return findings


def _name_with_email(text: str) -> bool:
    """Detect a person's name paired with an email (Example 4 pattern)."""
    has_email = bool(_EMAIL.search(text))
    has_name = bool(re.search(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", text))
    return has_email and has_name


def rejects_input(text: str) -> tuple[bool, List[str]]:
    """True when input should be blocked before retrieval (TRD-GRD-2)."""
    hits = scan_pii(text.strip())
    return bool(hits), hits
