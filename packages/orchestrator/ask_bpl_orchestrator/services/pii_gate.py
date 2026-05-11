"""PII rejection gate (regex / heuristic ensemble, TRD-GRD-2)."""

from __future__ import annotations

import re
from typing import List

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}\b", re.I)

_PHONE = re.compile(r"(?:\+\d{1,3}[\s-]?)?(?:\(?\d{3}\)?[\s.-]?){2}\d{4}\b")

_SSN_LIKE = re.compile(r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b")

_CC_LIKE = re.compile(r"\b(?:\d[ -]*?){13,16}\d\b")

_FINANCIAL = re.compile(
    r"\b(?:visa|mastercard|amex|american express|discover)\b.*\b\d{4}\b",
    re.I,
)

_STREET = re.compile(r"\b\d+\s+[A-Za-z0-9 .'-]{4,}(?:Street|St\.|Road|Rd\.|Avenue|Ave\.|Lane|Ln\.|Drive|Dr\.)\b")


def scan_pii(text: str) -> List[str]:
    """Return matched category labels if PII suspected."""
    findings: List[str] = []

    if _EMAIL.search(text):
        findings.append("email_address")

    if _PHONE.search(text):
        findings.append("phone_number")

    if _SSN_LIKE.search(text):
        findings.append("government_id_ssn_like")

    if _CC_LIKE.search(text) or _FINANCIAL.search(text):
        findings.append("payment_data")

    if _STREET.search(text):
        findings.append("home_address")

    if _looks_like_full_name_and_identifier(text):
        findings.append("name_with_identifier_pair")

    return findings


def _looks_like_full_name_and_identifier(text: str) -> bool:
    lowered = text.lower()
    markers = ["ssn", "dob ", " dob", "id number", "employee id", "badge", "acct", "driver license"]
    if len(text.split()) < 4:
        return False

    titled = bool(re.search(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b", text))
    return titled and any(m in lowered for m in markers)


def rejects_input(text: str) -> tuple[bool, list[str]]:
    hits = scan_pii(text.strip())
    return bool(hits), hits
