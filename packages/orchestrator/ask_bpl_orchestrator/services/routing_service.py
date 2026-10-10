"""Routing configuration from database (TRD-RTG)."""

from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ask_bpl_orchestrator.db.models import OwningTeam, PolicyType, RoutingRule


NEUTRAL_CONTACT_HINT = "Your supervisor can point you to the right contact."

# Words that mark internal placeholder text. Staff must never see these (PRD RTG-7).
_PLACEHOLDER_MARKERS = ("tbd", "pending", "todo", "selvon", "placeholder")


def public_contact_hint(hint: Optional[str]) -> str:
    """Return a contact hint that is safe to show staff.

    Placeholder or internal-process wording (for example "TBD pending Selvon approval")
    is replaced by a neutral supervisor referral. The system never invents a contact
    (RTG-4, RTG-7).
    """
    text = (hint or "").strip()
    lowered = text.lower()
    if not text or any(m in lowered for m in _PLACEHOLDER_MARKERS):
        return NEUTRAL_CONTACT_HINT
    return text


async def teams_for_policy(session: AsyncSession, policy_type: str) -> List[OwningTeam]:
    q = await session.execute(
        select(RoutingRule)
        .where(RoutingRule.policy_type == policy_type)
        .where(RoutingRule.selvon_approved.is_(True))
        .options(selectinload(RoutingRule.team))
        .order_by(RoutingRule.priority.asc())
    )
    rules = q.scalars().all()
    seen: set[uuid.UUID] = set()
    teams: List[OwningTeam] = []
    for r in rules:
        if r.team.team_id in seen:
            continue
        seen.add(r.team.team_id)
        teams.append(r.team)
    return teams


async def general_supervisor_team(session: AsyncSession) -> Optional[OwningTeam]:
    q = await session.execute(select(OwningTeam).where(OwningTeam.name == "Supervisor / General"))
    return q.scalars().first()


async def infer_policy_from_chunks(session: AsyncSession, policy_slugs: List[str]) -> Optional[str]:
    """Choose first policy slug that exists in policy_types; otherwise None."""
    if not policy_slugs:
        return None
    seen: set[str] = set()
    for slug in policy_slugs:
        if not slug or slug in seen:
            continue
        seen.add(slug)
        q = await session.execute(select(PolicyType).where(PolicyType.policy_type == slug))
        if q.scalars().first():
            return slug
    return None
