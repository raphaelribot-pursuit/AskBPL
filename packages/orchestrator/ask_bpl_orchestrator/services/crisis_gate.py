"""Crisis detection gate — immediate resource response for suicidal ideation/self-harm.

SAFETY: This gate runs BEFORE retrieval to bypass the RAG pipeline entirely.
On match, returns a warm crisis resource response instead of policy routing.

Detection is conservative and focused on first-person expressions of suicidal
ideation or intent to self-harm. A false positive (showing resources unnecessarily)
is far less harmful than a miss.

Does NOT trigger on third-person or policy-context phrasing (e.g., a policy
question about patron safety or training about suicide prevention).

NEVER logs message content that could contain PII.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ask_bpl_orchestrator.config import get_settings


@dataclass(frozen=True)
class CrisisResource:
    """A single crisis resource line."""

    name: str
    contact: str
    description: str


@dataclass(frozen=True)
class CrisisConfig:
    """Crisis response configuration — centralized, config-driven.

    TODO: Final wording pending Selvon's protocol review.
    """

    opening_message: str
    resources: tuple[CrisisResource, ...]
    closing_message: str


# Default interim configuration (pending Selvon's final protocol/wording)
DEFAULT_CRISIS_CONFIG = CrisisConfig(
    opening_message=(
        "I'm concerned about what you've shared. Your wellbeing matters, "
        "and there are people ready to help right now."
    ),
    resources=(
        CrisisResource(
            name="988 Suicide & Crisis Lifeline",
            contact="Call or text 988",
            description="Free, confidential support available 24/7",
        ),
        CrisisResource(
            name="BPL Staff Employee Assistance Program",
            contact="[Contact HR for EAP details]",
            description="TODO: Selvon to provide BPL-specific resource",
        ),
    ),
    closing_message=(
        "Please reach out to one of these resources. "
        "I'm here for policy questions, but they can provide the support you need."
    ),
)


# First-person suicidal ideation / self-harm patterns
# Conservative: prioritize catching clear cases over avoiding false positives
_CRISIS_PATTERNS = [
    # Direct expressions of suicidal ideation
    re.compile(r"\b(i('?m| am)|i('?ve| have))\b.{0,30}\b(thinking (about|of)|considering|planning|going to)\b.{0,30}\b(end(ing)? (my|it|everything)|kill(ing)? (myself|me)|suicide|taking my (own )?life|dying)\b", re.I),
    re.compile(r"\bi\b.{0,15}\bwant(s)? to\b.{0,20}\b(die|end it( all)?|kill myself|not (be here|exist|live))\b", re.I),
    re.compile(r"\bi\b.{0,15}\bdon('?t| not)\b.{0,20}\bwant to\b.{0,20}\b(live|be (here|alive)|exist)\b", re.I),
    re.compile(r"\bi('?m| am)\b.{0,20}\b(suicidal|going to (kill myself|end it|commit suicide))\b", re.I),

    # Self-harm intent
    re.compile(r"\bi('?m| am)\b.{0,30}\b(going to|planning to|thinking (about|of))\b.{0,20}\b(hurt(ing)? myself|cut(ting)? myself|harm(ing)? myself)\b", re.I),
    re.compile(r"\bi\b.{0,15}\bwant(s)? to\b.{0,20}\b(hurt|cut|harm)\b.{0,10}\bmyself\b", re.I),

    # Direct questions seeking method/how
    re.compile(r"\bhow (do|can|should) i\b.{0,20}\b(kill myself|end (my life|it all)|commit suicide)\b", re.I),

    # Hopelessness + no reason to live
    re.compile(r"\bi\b.{0,20}\b(have|see)\b.{0,10}\bno (reason|point)\b.{0,15}\b(to live|living|in living)\b", re.I),
    re.compile(r"\b(no one|nobody)\b.{0,20}\b(would (miss|care|notice)|cares if)\b.{0,20}\b(i|me)\b.{0,15}\b(was gone|died|wasn't here)\b", re.I),
]


# Negative patterns — do NOT trigger on these (policy/training/third-person context)
_SAFE_CONTEXT_PATTERNS = [
    # Policy/procedure questions
    re.compile(r"\b(policy|procedure|protocol|guideline|training)\b.{0,30}\b(suicide|crisis|self[- ]?harm)\b", re.I),
    re.compile(r"\b(suicide|crisis|self[- ]?harm)\b.{0,30}\b(policy|procedure|protocol|guideline|training)\b", re.I),

    # Third-person / patron context
    re.compile(r"\b(patron|customer|visitor|someone|a person|they|he|she|the user)\b.{0,40}\b(suicide|suicidal|self[- ]?harm|crisis)\b", re.I),
    re.compile(r"\bif\b.{0,20}\b(patron|someone|a person)\b.{0,30}\b(mentions|expresses|shows signs)\b", re.I),

    # How to help someone else
    re.compile(r"\bhow (do|can|should) (we|i|staff)\b.{0,20}\b(help|support|respond|handle)\b.{0,30}\b(patron|someone|person)\b", re.I),

    # Training / awareness
    re.compile(r"\b(suicide (prevention|awareness)|mental health (training|awareness))\b", re.I),
    re.compile(r"\bwhat (should|do) (staff|we|employees)\b.{0,30}\b(do|say)\b.{0,30}\b(if|when)\b", re.I),
]


def _matches_crisis_pattern(text: str) -> bool:
    """Check if text matches first-person crisis patterns."""
    for pattern in _CRISIS_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _is_safe_context(text: str) -> bool:
    """Check if text is in a safe policy/training/third-person context."""
    for pattern in _SAFE_CONTEXT_PATTERNS:
        if pattern.search(text):
            return True
    return False


def detect_crisis(text: str) -> bool:
    """Detect if the input expresses first-person suicidal ideation or self-harm intent.

    Returns True when a first-person crisis pattern matches, even if the same message
    also mentions a policy, procedure or training (for example "I want to die. Where is
    the suicide prevention policy?"). Safe-context phrasing only decides messages that
    have NO first-person crisis pattern, so it can never suppress a real expression of
    intent. SAF-3 / AC-6; found fail-open on 2026-10-10.

    SAFETY: False positive (showing resources unnecessarily) is far less harmful
    than a miss.
    """
    if not text or not text.strip():
        return False

    normalized = " ".join(text.split())  # collapse whitespace
    return _matches_crisis_pattern(normalized)


def get_crisis_config() -> CrisisConfig:
    """Get the crisis response configuration.

    Currently returns default config. In production, could read from
    env vars, config file, or database for Selvon to update without deploy.
    """
    # Future: settings = get_settings() and read from env/config
    return DEFAULT_CRISIS_CONFIG


def format_crisis_response(config: Optional[CrisisConfig] = None) -> dict:
    """Format the crisis resource response payload.

    Returns a response dict with type='crisis_resource' that bypasses
    retrieval, generation, and policy routing entirely.
    """
    if config is None:
        config = get_crisis_config()

    resources_formatted = [
        {
            "name": r.name,
            "contact": r.contact,
            "description": r.description,
        }
        for r in config.resources
    ]

    return {
        "type": "crisis_resource",
        "message": config.opening_message,
        "resources": resources_formatted,
        "closing": config.closing_message,
    }
