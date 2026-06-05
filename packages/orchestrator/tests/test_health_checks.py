"""Health probe helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ask_bpl_orchestrator.config import Settings
from ask_bpl_orchestrator.health_checks import (
    missing_required_env,
    probe_pinecone,
    run_deep_health_checks,
)


def test_missing_required_env_lists_unset_keys() -> None:
    settings = Settings(
        jwt_secret_key="",
        openai_api_key="",
        anthropic_api_key="",
        pinecone_api_key="",
        pinecone_index_name="",
    )

    missing = missing_required_env(settings)

    assert "JWT_SECRET_KEY" in missing
    assert "OPENAI_API_KEY" in missing
    assert "PINECONE_API_KEY" in missing


@pytest.mark.asyncio
async def test_probe_pinecone_reports_empty_index() -> None:
    settings = Settings(
        jwt_secret_key="secret",
        openai_api_key="sk-test",
        anthropic_api_key="sk-ant-test",
        pinecone_api_key="pc-test",
        pinecone_index_name="askbpl-pilot",
    )
    stats = MagicMock()
    stats.total_vector_count = 0

    with patch(
        "ask_bpl_orchestrator.health_checks.get_pinecone_index",
        return_value=MagicMock(describe_index_stats=lambda: stats),
    ):
        result = await probe_pinecone(settings)

    assert result["status"] == "error"
    assert result["vectors"] == 0


@pytest.mark.asyncio
async def test_run_deep_health_checks_marks_degraded_when_openai_fails() -> None:
    settings = Settings(
        jwt_secret_key="secret",
        openai_api_key="sk-test",
        anthropic_api_key="sk-ant-test",
        pinecone_api_key="pc-test",
        pinecone_index_name="askbpl-pilot",
    )

    with (
        patch(
            "ask_bpl_orchestrator.health_checks.probe_pinecone",
            return_value={"status": "ok", "vectors": 77},
        ),
        patch(
            "ask_bpl_orchestrator.health_checks.probe_openai",
            return_value={"status": "error", "detail": "auth"},
        ),
        patch(
            "ask_bpl_orchestrator.health_checks.probe_anthropic",
            return_value={"status": "ok"},
        ),
    ):
        report = await run_deep_health_checks(settings)

    assert report["status"] == "degraded"
    assert report["checks"]["openai"]["status"] == "error"
