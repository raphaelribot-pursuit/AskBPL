"""Routing configuration from database (TRD-RTG)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ask_bpl_orchestrator.db.models import OwningTeam, PolicyType, RoutingRule


NEUTRAL_CONTACT_HINT = "Your supervisor can point you to the right contact."

# Most policy areas the model is shown owning teams for in one question. Keeps the prompt short.
MAX_ROUTING_POLICIES = 6
FALLBACK_POLICY_LABEL = "Any other or unclear policy area"


@dataclass(frozen=True)
class RoutingChoice:
    """One line of the routing list the model may draw team names from."""

    policy_label: str
    team_names: tuple[str, ...]

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


async def routing_choices(
    session: AsyncSession,
    policy_slugs: Sequence[Optional[str]],
    *,
    limit: int = MAX_ROUTING_POLICIES,
) -> List[RoutingChoice]:
    """Owning teams the model may name for this question (RTG-2, RTG-4, RTG-7).

    Only teams reached through a Selvon-approved routing rule are returned, for the policy areas
    of the excerpts actually retrieved, so the model is never shown (and cannot repeat) a team the
    approved configuration does not give. The final line is the same Supervisor / General fallback
    the refusal card already uses; if that team does not exist, the model is told there is no team.
    """
    seen: List[str] = []
    for slug in policy_slugs:
        if slug and slug not in seen:
            seen.append(slug)

    choices: List[RoutingChoice] = []
    for slug in seen[:limit]:
        teams = await teams_for_policy(session, slug)
        if not teams:
            continue
        policy = await session.get(PolicyType, slug)
        choices.append(
            RoutingChoice(
                policy_label=(policy.display_name if policy else slug),
                team_names=tuple(t.name for t in teams),
            )
        )

    fallback = await general_supervisor_team(session)
    if fallback is not None:
        choices.append(RoutingChoice(policy_label=FALLBACK_POLICY_LABEL, team_names=(fallback.name,)))
    return choices
