"""ADM-1, patch 0057: the admin capability is protected by its own credential, separate from staff access.

Every route under /admin and /internal (with and without the /v1 prefix) is found by walking the app, not listed by
hand, so a new admin route is covered automatically. Each must refuse: no credential, a wrong one, a valid STAFF sign-in
token, and any login at all when the admin password is left empty. The oversight figures the PRD names (usage volume,
refusal rate, top routing destinations, feedback ratings) must be present for the admin.
"""

from __future__ import annotations

import os
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.main import app

client = TestClient(app)


def _admin() -> tuple[str, str]:
    return os.environ.get("ADMIN_BASIC_USER", "vizion_build"), os.environ["ADMIN_BASIC_PASSWORD"]


def _admin_routes() -> list[tuple[str, str]]:
    """Every admin/internal path and method from the app's OpenAPI schema (no route hides itself: see the last test)."""
    out = []
    for path, ops in app.openapi()["paths"].items():
        if re.match(r"^(/v1)?/(admin|internal)(/|$)", path):
            concrete = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)
            out.extend((m.upper(), concrete) for m in sorted(ops))
    return out


ROUTES = _admin_routes()


def _staff_token() -> str:
    r = client.post(
        "/auth/sign-in",
        json={"email": "pilot-demo@bklynlibrary.org", "access_code": "DEMO2026", "attribution_mode": "anonymous"},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_the_walk_finds_the_whole_admin_surface() -> None:
    paths = {p for _, p in ROUTES}
    for must in ("/admin/summary", "/v1/admin/summary", "/internal/corpus", "/v1/internal/corpus", "/v1/internal/feedback"):
        assert must in paths, must
    assert ("POST", "/v1/internal/ingest") in ROUTES
    assert any(m == "PATCH" and "/routing/" in p for m, p in ROUTES)
    assert len(ROUTES) >= 20


@pytest.mark.parametrize("method,path", ROUTES)
def test_every_admin_route_refuses_without_the_admin_credential(method: str, path: str) -> None:
    assert client.request(method, path).status_code == 401, (method, path)
    assert client.request(method, path, auth=("not-the-admin", "wrong")).status_code == 401, (method, path)
    user, _ = _admin()
    assert client.request(method, path, auth=(user, "wrong-password")).status_code == 401, (method, path)


@pytest.mark.parametrize("method,path", ROUTES)
def test_a_staff_sign_in_never_opens_an_admin_route(method: str, path: str) -> None:
    r = client.request(method, path, headers={"Authorization": f"Bearer {_staff_token()}"})
    assert r.status_code == 401, (method, path, r.status_code)


def test_an_empty_admin_password_locks_the_console_instead_of_opening_it(monkeypatch) -> None:
    user, _ = _admin()
    monkeypatch.setenv("ADMIN_BASIC_PASSWORD", "")
    get_settings.cache_clear()
    try:
        assert client.get("/v1/admin/summary", auth=(user, "")).status_code == 401
        assert client.get("/v1/admin/summary", auth=(user, "anything")).status_code == 401
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_the_admin_sees_the_oversight_figures_the_prd_names() -> None:
    r = client.get("/v1/admin/summary", auth=_admin())
    assert r.status_code == 200
    body = r.json()
    for key in ("questions_total", "responses_non_answer_approx", "routing_team_counts_sample", "feedback_helpful", "feedback_not_helpful"):
        assert key in body, key
    fb = client.get("/v1/internal/feedback", auth=_admin())
    assert fb.status_code == 200 and {"total", "helpful_count", "not_helpful_count"} <= set(fb.json())


def test_no_route_hides_from_the_schema_so_the_walk_above_is_complete() -> None:
    from pathlib import Path

    api = Path(__file__).resolve().parents[1] / "ask_bpl_orchestrator"
    hidden = [str(f) for f in api.rglob("*.py") if "include_in_schema=False" in f.read_text(encoding="utf-8")]
    assert hidden == []
