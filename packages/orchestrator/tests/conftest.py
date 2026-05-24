"""Pytest hooks — integration tests expect Postgres (see CI) and seeded pilot user."""

from __future__ import annotations

import os

# Applied before test modules import `app` / `get_settings`.
os.environ.setdefault("ADMIN_BASIC_PASSWORD", "ci-integration-admin-secret")
os.environ.setdefault("JWT_SECRET_KEY", "ci-test-jwt-secret-key-min-32-chars")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-api03-ci-placeholder-not-used-when-mocked")


def pytest_configure(config) -> None:
    from ask_bpl_orchestrator.config import get_settings

    get_settings.cache_clear()
