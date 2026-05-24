"""Policy filename mapping and routing validation (TRD-IGN-2, TRD-IGN-3)."""

from __future__ import annotations

import fnmatch
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Pattern

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROUTING_PATH = PROJECT_ROOT / "config" / "routing.yaml"


@dataclass(frozen=True)
class PolicyRecord:
    """Resolved policy metadata for one corpus file."""

    policy_type: str
    source_document: str
    document_version: str


# Hardcoded filename patterns (Step 01 source of truth). Underscore fnmatch + normalized stem regex.
_POLICY_PATTERNS: List[tuple[str, PolicyRecord]] = [
    (
        "02_-_Materials_Selection_Policy_*",
        PolicyRecord("materials_selection", "Materials Selection Policy", "2005-04-19"),
    ),
    (
        "02_-_Policy_on_Unattended_Children_*",
        PolicyRecord("unattended_children", "Policy on Unattended Children", "2005-09-20"),
    ),
    (
        "04_-_Annual_Leave_Policy_*",
        PolicyRecord("annual_leave", "Annual Leave Policy", "2006-01"),
    ),
    (
        "06_-_Conflict_of_Interest_*",
        PolicyRecord("conflict_of_interest", "Conflict of Interest Policy", "2014-06"),
    ),
    (
        "06_-_Fundraising_Policy_*",
        PolicyRecord("fundraising", "Fundraising Policy", "2001-12"),
    ),
    (
        "07_-_Volunteer_Manual_*",
        PolicyRecord("volunteer_manual", "Volunteer Manual", "2008-12-16"),
    ),
]

# Match normalized stems: leading prefix + descriptive slug (spaces or underscores in filenames).
_NORMALIZED_STEM_RULES: List[tuple[Pattern[str], PolicyRecord]] = [
    (re.compile(r"^02_.*materials.*selection"), _POLICY_PATTERNS[0][1]),
    (re.compile(r"^02_.*unattended.*children"), _POLICY_PATTERNS[1][1]),
    (re.compile(r"^04_.*annual.*leave"), _POLICY_PATTERNS[2][1]),
    (re.compile(r"^06_.*conflict.*interest"), _POLICY_PATTERNS[3][1]),
    (re.compile(r"^06_.*fundraising"), _POLICY_PATTERNS[4][1]),
    (re.compile(r"^07_.*volunteer"), _POLICY_PATTERNS[5][1]),
]


def _normalize_stem(filename: str) -> str:
    """Normalize filename for prefix + stem matching (case-insensitive)."""
    stem = Path(filename).stem.lower()
    stem = re.sub(r"\s*\(\d+\)\s*", " ", stem)
    stem = re.sub(r"\s*\([\d.]+\)\s*", " ", stem)
    stem = re.sub(r"[\s\-_]+", "_", stem.strip())
    return stem


def load_valid_policy_types(routing_path: Path = ROUTING_PATH) -> set[str]:
    """Load policy_type keys from routing config (TRD-IGN-3)."""
    with routing_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    policy_types: Dict[str, object] = data.get("policy_types") or {}
    return set(policy_types.keys())


def match_policy(filename: str, valid_types: set[str]) -> Optional[PolicyRecord]:
    """Match a corpus filename to policy metadata; None if unknown (TRD-IGN-3)."""
    name = Path(filename).name
    for pattern, record in _POLICY_PATTERNS:
        if fnmatch.fnmatchcase(name, pattern) or fnmatch.fnmatchcase(name.lower(), pattern.lower()):
            if record.policy_type not in valid_types:
                logger.error("policy_type %s not in routing.yaml", record.policy_type)
                return None
            return record

    normalized = _normalize_stem(name)
    for regex, record in _NORMALIZED_STEM_RULES:
        if regex.search(normalized):
            if record.policy_type not in valid_types:
                logger.error("policy_type %s not in routing.yaml", record.policy_type)
                return None
            return record
    return None
