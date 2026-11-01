"""Routing configuration audit trail (PRD RTG-5, patch 0056).

Every change to whether a routing rule may be used is written as one JSON log line on the `ask_bpl.routing_audit`
logger: approvals and withdrawals in the admin console, and approvals withdrawn because a re-seed changed an approved
rule. Ids, policy slug, before and after, and the time only. The admin login is shared, so the line cannot say WHO
approved; naming the designated BPL approver is a BPL decision (decision request item 11).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("ask_bpl.routing_audit")


def record(event: str, **fields: Any) -> dict:
    line = {"event": event, "at": datetime.now(timezone.utc).isoformat(), **{k: (str(v) if v is not None and not isinstance(v, (bool, int, float)) else v) for k, v in fields.items()}}
    log.info(json.dumps(line, sort_keys=True))
    return line
