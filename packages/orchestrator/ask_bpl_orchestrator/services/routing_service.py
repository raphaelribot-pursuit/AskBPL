"""Routing configuration from database (TRD-RTG)."""

from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ask_bpl_orchestrator.db.models import OwningTeam, PolicyType, RoutingRule


async def teams_for_policy(session: AsyncSession, policy_type: str) -> List[OwningTeam]:
    q = await session.execute(
        select(RoutingRule)
        .where(RoutingRule.policy_type == policy_type)
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
