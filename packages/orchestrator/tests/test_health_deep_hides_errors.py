"""Patch 0021: /health/deep never returns raw exception text (unauthenticated route)."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from ask_bpl_orchestrator import health_checks as hc
from ask_bpl_orchestrator.config import Settings

SECRET = "sk-LEAKME-1234567890 host=db.internal.example request_id=req_abc"


@pytest.mark.parametrize("exc, label", [
    (RuntimeError(SECRET), "probe_failed"),
    (asyncio.TimeoutError(SECRET), "timeout"),
    (TimeoutError(SECRET), "timeout"),
    (type("AuthenticationError", (Exception,), {})(SECRET), "authentication_failed"),
    (type("E", (Exception,), {"status_code": 401})(SECRET), "authentication_failed"),
    (type("E", (Exception,), {"status_code": 429})(SECRET), "rate_limited"),
    (type("APIConnectionError", (Exception,), {})(SECRET), "unreachable"),
])
def test_safe_error_detail_is_a_fixed_label_never_the_exception_text(exc: Exception, label: str) -> None:
    out = hc.safe_error_detail(exc)
    assert out == label and "LEAKME" not in out and "internal" not in out


def _settings() -> Settings:
    return Settings(jwt_secret_key="s", openai_api_key="sk-t", anthropic_api_key="sk-ant-t",
                    pinecone_api_key="pc", pinecone_index_name="i")


@pytest.mark.asyncio
async def test_all_three_probes_hide_the_exception_text() -> None:
    boom = RuntimeError(SECRET)
    s = _settings()
    with patch("ask_bpl_orchestrator.health_checks.get_pinecone_index", side_effect=boom):
        pc = await hc.probe_pinecone(s)
    with patch("openai.OpenAI", side_effect=boom):
        oa = await hc.probe_openai(s)
    with patch("anthropic.Anthropic", side_effect=boom):
        an = await hc.probe_anthropic(s)
    for r in (pc, oa, an):
        assert r["status"] == "error" and r["detail"] == "probe_failed"
        assert "LEAKME" not in str(r)


@pytest.mark.asyncio
async def test_deep_report_as_a_whole_contains_no_exception_text() -> None:
    boom = RuntimeError(SECRET)
    s = _settings()
    with patch("ask_bpl_orchestrator.health_checks.get_pinecone_index", side_effect=boom), \
         patch("openai.OpenAI", side_effect=boom), patch("anthropic.Anthropic", side_effect=boom):
        rep = await hc.run_deep_health_checks(s)
    assert rep["status"] == "degraded" and "LEAKME" not in str(rep) and "internal" not in str(rep)


def test_no_probe_returns_str_exc_in_source() -> None:
    src = Path(hc.__file__).read_text()
    assert not re.search(r"\"detail\":\s*str\(exc\)", src)
    assert src.count("safe_error_detail(exc)") == 3


def test_the_failure_is_still_logged_for_the_operator() -> None:
    src = Path(hc.__file__).read_text()
    assert src.count("_health_failed: %s\", exc") == 3
