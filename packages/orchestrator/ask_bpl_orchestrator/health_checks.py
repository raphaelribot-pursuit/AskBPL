"""Lightweight and deep health probes for Render / ops."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ask_bpl_orchestrator.config import Settings, get_settings
from ask_bpl_orchestrator.services.pinecone_client import get_pinecone_index

logger = logging.getLogger(__name__)

EXTERNAL_PROBE_TIMEOUT_SECONDS = 30.0


def missing_required_env(settings: Settings | None = None) -> list[str]:
    """Env vars required for the /ask RAG pipeline (not login-only paths)."""
    cfg = settings or get_settings()
    required = {
        "JWT_SECRET_KEY": cfg.jwt_secret_key,
        "OPENAI_API_KEY": cfg.openai_api_key,
        "ANTHROPIC_API_KEY": cfg.anthropic_api_key,
        "PINECONE_API_KEY": cfg.pinecone_api_key,
        "PINECONE_INDEX_NAME": cfg.pinecone_index_name,
    }
    return [name for name, value in required.items() if not str(value).strip()]


async def probe_pinecone(settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    if not cfg.pinecone_api_key.strip():
        return {"status": "error", "detail": "PINECONE_API_KEY not set"}
    try:
        index = get_pinecone_index()

        def _stats() -> Any:
            return index.describe_index_stats()

        stats = await asyncio.wait_for(
            asyncio.to_thread(_stats),
            timeout=EXTERNAL_PROBE_TIMEOUT_SECONDS,
        )
        total = getattr(stats, "total_vector_count", None)
        if total is None and isinstance(stats, dict):
            total = stats.get("total_vector_count")
        count = int(total or 0)
        if count == 0:
            return {
                "status": "error",
                "detail": "index_empty",
                "vectors": 0,
            }
        return {"status": "ok", "vectors": count}
    except Exception as exc:  # noqa: BLE001 — health probe must not raise
        logger.warning("pinecone_health_failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


async def probe_openai(settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    if not cfg.openai_api_key.strip():
        return {"status": "error", "detail": "OPENAI_API_KEY not set"}
    try:
        from openai import OpenAI

        client = OpenAI(api_key=cfg.openai_api_key)

        def _embed() -> Any:
            return client.embeddings.create(
                model=cfg.openai_embedding_model,
                input="health check",
            )

        await asyncio.wait_for(
            asyncio.to_thread(_embed),
            timeout=EXTERNAL_PROBE_TIMEOUT_SECONDS,
        )
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("openai_health_failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


async def probe_anthropic(settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    if not cfg.anthropic_api_key.strip():
        return {"status": "error", "detail": "ANTHROPIC_API_KEY not set"}
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)

        def _ping() -> Any:
            return client.messages.create(
                model=cfg.anthropic_model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )

        await asyncio.wait_for(
            asyncio.to_thread(_ping),
            timeout=EXTERNAL_PROBE_TIMEOUT_SECONDS,
        )
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("anthropic_health_failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


async def run_deep_health_checks(settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    missing = missing_required_env(cfg)
    checks: dict[str, Any] = {}
    if missing:
        checks["environment"] = {"status": "error", "detail": f"missing: {', '.join(missing)}"}
    else:
        checks["environment"] = {"status": "ok"}

    pinecone, openai, anthropic_result = await asyncio.gather(
        probe_pinecone(cfg),
        probe_openai(cfg),
        probe_anthropic(cfg),
    )
    checks["pinecone"] = pinecone
    checks["openai"] = openai
    checks["anthropic"] = anthropic_result

    all_ok = all(item.get("status") == "ok" for item in checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "service": "askbpl-orchestrator",
        "checks": checks,
    }
