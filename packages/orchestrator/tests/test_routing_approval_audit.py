"""RTG-5, patch 0056: routing configuration changes are logged and need approval.

Approvals and withdrawals in the admin console, and an approved rule changed by a re-seed, each leave one JSON line on
the `ask_bpl.routing_audit` logger. A re-seed that changes an approved rule withdraws its approval. Real Postgres; each
test makes its own policy type, team and rule and removes them.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from ask_bpl_orchestrator import seed
from ask_bpl_orchestrator.db.models import OwningTeam, PolicyType, RoutingRule
from ask_bpl_orchestrator.db.session import async_session_factory
from ask_bpl_orchestrator.main import app

client = TestClient(app)
AUDIT = "ask_bpl.routing_audit"


def _admin() -> tuple[str, str]:
    return os.environ.get("ADMIN_BASIC_USER", "vizion_build"), os.environ["ADMIN_BASIC_PASSWORD"]


def _events(caplog) -> list[dict]:
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == AUDIT]


async def _fixture(tag: str, *, approved: bool, priority: int = 1, team_key: str | None = None):
    slug = f"rtg5_{tag}"
    team_id = seed.deterministic_team_uuid(team_key) if team_key else uuid.uuid4()
    async with async_session_factory() as s:
        s.add(PolicyType(policy_type=slug, display_name=f"RTG-5 test {tag}"))
        s.add(OwningTeam(team_id=team_id, name=f"RTG-5 team {tag}", contact_hint="Contact the test team."))
        await s.flush()
        rule = RoutingRule(policy_type=slug, team_id=team_id, priority=priority, selvon_approved=approved,
                           approved_at=datetime.now(timezone.utc) if approved else None)
        s.add(rule)
        await s.commit()
        return slug, team_id, rule.rule_id


async def _drop(slug: str, team_id: uuid.UUID) -> None:
    async with async_session_factory() as s:
        await s.execute(delete(RoutingRule).where(RoutingRule.policy_type == slug))
        await s.execute(delete(OwningTeam).where(OwningTeam.team_id == team_id))
        await s.execute(delete(PolicyType).where(PolicyType.policy_type == slug))
        await s.commit()


async def _rule(slug: str) -> RoutingRule:
    async with async_session_factory() as s:
        return (await s.execute(select(RoutingRule).where(RoutingRule.policy_type == slug))).scalars().one()


def test_the_approval_endpoint_needs_the_admin_credential() -> None:
    r = client.patch(f"/v1/internal/routing/{uuid.uuid4()}/approval", json={"selvon_approved": True})
    assert r.status_code == 401
    r = client.patch(f"/v1/internal/routing/{uuid.uuid4()}/approval", json={"selvon_approved": True}, auth=("x", "y"))
    assert r.status_code == 401


def test_unknown_and_malformed_rule_ids_are_refused() -> None:
    assert client.patch(f"/v1/internal/routing/{uuid.uuid4()}/approval", json={}, auth=_admin()).status_code == 404
    assert client.patch("/v1/internal/routing/not-a-uuid/approval", json={}, auth=_admin()).status_code == 400


@pytest.mark.asyncio
async def test_approving_and_withdrawing_are_each_logged_with_the_time_they_replace(caplog) -> None:
    tag = uuid.uuid4().hex[:8]
    slug, team_id, rule_id = await _fixture(tag, approved=False)
    caplog.set_level(logging.INFO, logger=AUDIT)
    try:
        r = client.patch(f"/v1/internal/routing/{rule_id}/approval", json={"selvon_approved": True}, auth=_admin())
        assert r.status_code == 200 and r.json()["selvon_approved"] is True
        r = client.patch(f"/v1/internal/routing/{rule_id}/approval", json={"selvon_approved": False}, auth=_admin())
        assert r.status_code == 200 and r.json()["selvon_approved"] is False

        approve, withdraw = [e for e in _events(caplog) if e["rule_id"] == str(rule_id)]
        assert approve["event"] == withdraw["event"] == "routing_approval_changed"
        assert approve["source"] == "admin_console" and approve["policy_type"] == slug
        assert (approve["approved_before"], approve["approved_after"]) == (False, True)
        assert approve["previous_approved_at"] is None
        assert (withdraw["approved_before"], withdraw["approved_after"]) == (True, False)
        assert withdraw["previous_approved_at"]  # the approval being withdrawn is not lost
        assert (await _rule(slug)).approved_at is None
    finally:
        await _drop(slug, team_id)


@pytest.mark.asyncio
async def test_a_reseed_that_changes_an_approved_rule_withdraws_the_approval_and_logs_it(caplog, monkeypatch) -> None:
    tag = uuid.uuid4().hex[:8]
    key = f"rtg5_team_{tag}"
    slug, team_id, rule_id = await _fixture(tag, approved=True, priority=1, team_key=key)
    monkeypatch.delenv("SEED_AUTO_APPROVE_ROUTING", raising=False)
    caplog.set_level(logging.INFO, logger=AUDIT)
    try:
        await seed.seed_rules([{"policy_type_slug": slug, "team_key": key, "priority": 1}])  # unchanged
        assert (await _rule(slug)).selvon_approved is True
        assert not [e for e in _events(caplog) if e.get("rule_id") == str(rule_id)]

        await seed.seed_rules([{"policy_type_slug": slug, "team_key": key, "priority": 2}])  # changed
        rule = await _rule(slug)
        assert rule.selvon_approved is False and rule.approved_at is None and rule.priority == 2
        (event,) = [e for e in _events(caplog) if e.get("rule_id") == str(rule_id)]
        assert event["source"] == "seed" and event["priority_before"] == 1 and event["priority"] == 2
        assert (event["approved_before"], event["approved_after"]) == (True, False)
        assert "needs approval again" in event["reason"]
    finally:
        await _drop(slug, team_id)


@pytest.mark.asyncio
async def test_a_new_rule_from_the_seed_is_logged_and_starts_unapproved(caplog, monkeypatch) -> None:
    tag = uuid.uuid4().hex[:8]
    key = f"rtg5_team_{tag}"
    slug, team_id = f"rtg5_{tag}", seed.deterministic_team_uuid(key)
    async with async_session_factory() as s:
        s.add(PolicyType(policy_type=slug, display_name=f"RTG-5 test {tag}"))
        s.add(OwningTeam(team_id=team_id, name=f"RTG-5 team {tag}", contact_hint="Contact the test team."))
        await s.commit()
    monkeypatch.delenv("SEED_AUTO_APPROVE_ROUTING", raising=False)
    caplog.set_level(logging.INFO, logger=AUDIT)
    try:
        await seed.seed_rules([{"policy_type_slug": slug, "team_key": key, "priority": 1}])
        assert (await _rule(slug)).selvon_approved is False
        (event,) = [e for e in _events(caplog) if e.get("policy_type") == slug]
        assert event["event"] == "routing_rule_added" and event["approved_after"] is False
    finally:
        await _drop(slug, team_id)
