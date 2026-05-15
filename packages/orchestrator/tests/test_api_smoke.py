"""API smoke tests (no database required for /healthz)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from ask_bpl_orchestrator.main import app

client = TestClient(app)


def test_healthz_ok_and_request_id_header() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers.get("X-Request-ID")


def test_feedback_requires_bearer_token() -> None:
    response = client.post(
        "/feedback/",
        json={"request_id": str(uuid.uuid4()), "rating": "helpful"},
    )
    assert response.status_code == 401
