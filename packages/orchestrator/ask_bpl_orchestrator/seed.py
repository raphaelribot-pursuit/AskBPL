"""Seed routing YAML + baseline pilot tester credential."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from passlib.hash import bcrypt
from sqlalchemy import select

from ask_bpl_orchestrator.db.models import OwningTeam, PolicyType, RoutingRule, Tester, TesterGroup
from ask_bpl_orchestrator.db.session import async_session_factory

ROUTING_FIXTURE = Path(__file__).resolve().parent.parent / "config" / "routing_seed.yaml"
TEAM_NAMESPACE = uuid.UUID("a3bb189e-8bf9-3888-8f715-d87cdc60bf6")


def deterministic_team_uuid(key: str) -> uuid.UUID:
    label = key.strip().upper()
    return uuid.uuid5(TEAM_NAMESPACE, label)


async def seed_teams(rows: list[dict]) -> None:
    async with async_session_factory() as session:
        for row in rows:
            team_id = deterministic_team_uuid(row["key"])

            owning = OwningTeam(
                team_id=team_id,
                name=row["name"],
                contact_hint=row["contact_hint"],
            )

            existing = (
                (
                    await session.execute(select(OwningTeam).where(OwningTeam.team_id == team_id))
                )
                .scalars()
                .first()
            )

            target = owning if not existing else existing
            await session.merge(target)
        await session.commit()


async def seed_policies(rows: list[dict]) -> None:
    async with async_session_factory() as session:
        for policy in rows:
            record = PolicyType(
                policy_type=policy["slug"],
                display_name=policy["display_name"],
                description=policy["description"],
            )
            existing = (
                (
                    await session.execute(
                        select(PolicyType).where(PolicyType.policy_type == policy["slug"])
                    )
                )
                .scalars()
                .first()
            )
            merged = existing or record

            merged.display_name = policy["display_name"]
            merged.description = policy["description"]

            await session.merge(merged)
        await session.commit()


async def seed_rules(rows: list[dict]) -> None:
    # Default is OFF: routing rules start unapproved and are approved by the designated BPL
    # approver in the admin console (PRD RTG-3, RTG-5, D-04). Unapproved rules are never used,
    # so staff get the neutral supervisor referral (RTG-7). Set SEED_AUTO_APPROVE_ROUTING=1
    # for local development only.
    auto_approve = os.environ.get("SEED_AUTO_APPROVE_ROUTING", "0").strip().lower() in {"1", "true", "yes"}
    async with async_session_factory() as session:
        for rule_payload in rows:
            policy_slug = rule_payload["policy_type_slug"]

            composite = uuid.uuid5(
                TEAM_NAMESPACE,
                f"{policy_slug}:{rule_payload['team_key']}:{rule_payload.get('priority', 0)}",
            )

            team_id_value = deterministic_team_uuid(rule_payload["team_key"])

            rule = RoutingRule(
                rule_id=composite,
                policy_type=policy_slug,
                team_id=team_id_value,
                priority=int(rule_payload.get("priority", 0)),
                selvon_approved=auto_approve,
                approved_at=datetime.now(timezone.utc) if auto_approve else None,
            )

            legacy = (
                (
                    await session.execute(
                        select(RoutingRule).where(
                            RoutingRule.policy_type == policy_slug,
                            RoutingRule.team_id == team_id_value,
                        )
                    )
                )
                .scalars()
                .first()
            )

            merged = legacy or rule

            merged.policy_type = policy_slug
            merged.team_id = team_id_value
            merged.priority = int(rule_payload.get("priority", 0))
            if auto_approve:
                merged.selvon_approved = True
                merged.approved_at = datetime.now(timezone.utc)

            await session.merge(merged)
        await session.commit()


async def seed_demo_tester(email: str, access_code_plain: str) -> None:
    tester_id = uuid.uuid5(TEAM_NAMESPACE, email.lower())

    async with async_session_factory() as session:
        hashed = bcrypt.hash(access_code_plain)
        tester = Tester(
            tester_id=tester_id,
            email=email.lower(),
            access_code_hash=hashed,
            group=TesterGroup.SME,
            department="Pilot",
            issued_at=datetime.now(timezone.utc),
            active=True,
        )

        previous = (
            (
                await session.execute(select(Tester).where(Tester.email == email.lower()))
            )
            .scalars()
            .first()
        )

        merged = previous or tester
        merged.email = email.lower()
        merged.access_code_hash = hashed
        merged.group = TesterGroup.SME

        merged.department = merged.department or "Pilot"

        merged.issued_at = merged.issued_at or datetime.now(timezone.utc)

        merged.active = True

        await session.merge(merged)
        await session.commit()


def load_yaml() -> dict:
    with ROUTING_FIXTURE.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


async def asyncio_main() -> None:
    blob = load_yaml()
    teams = blob.get("teams", [])
    policies = blob.get("policy_types", [])
    rules_blob = blob.get("routing_rules", [])

    await seed_teams(teams)
    await seed_policies(policies)
    await seed_rules(rules_blob)
    demo_email = os.environ.get("PILOT_DEMO_EMAIL", "pilot-demo@bklynlibrary.org")
    demo_code = os.environ.get("PILOT_DEMO_ACCESS_CODE", "DEMO2026")
    await seed_demo_tester(demo_email, demo_code)

    print(f"Seed complete: routing + pilot tester {demo_email} (access code from env)")  # noqa: T201


def main() -> None:
    asyncio.run(asyncio_main())


if __name__ == "__main__":
    main()
