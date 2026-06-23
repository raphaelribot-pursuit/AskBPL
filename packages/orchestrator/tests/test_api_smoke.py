"""API smoke tests (no database required for /healthz)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ask_bpl_orchestrator.main import app

client = TestClient(app)


def test_healthz_ok_and_request_id_header() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "askbpl-orchestrator"}
    assert response.headers.get("X-Request-ID")


def test_health_alias_matches_healthz() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
