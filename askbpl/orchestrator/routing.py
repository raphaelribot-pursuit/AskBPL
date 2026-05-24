"""Policy routing from config/routing.yaml (TRD-RTG-2 through TRD-RTG-5)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import yaml

from ingestion.policy_metadata import PROJECT_ROOT

logger = logging.getLogger(__name__)

ROUTING_PATH = PROJECT_ROOT / "config" / "routing.yaml"


def load_routing_config(path: Path = ROUTING_PATH) -> dict:
    """Load routing configuration."""
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def owners_for_policy(policy_type: Optional[str], routing: dict | None = None) -> List[str]:
    """Return owning teams for a policy slug, or fallback owners (TRD-RTG-5)."""
    cfg = routing or load_routing_config()
    if policy_type:
        entry = (cfg.get("policy_types") or {}).get(policy_type) or {}
        owners = entry.get("owners") or []
        if owners:
            return [str(o) for o in owners]
    fallback = cfg.get("fallback") or {}
    return [str(o) for o in (fallback.get("owners") or [])]
