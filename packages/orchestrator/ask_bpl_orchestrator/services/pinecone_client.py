"""Pinecone index handle (pod name or serverless host)."""

from __future__ import annotations

from typing import Any

from ask_bpl_orchestrator.config import get_settings


def get_pinecone_index() -> Any:
    """Return a Pinecone Index; uses PINECONE_HOST when set (typical for serverless)."""
    from pinecone import Pinecone

    cfg = get_settings()
    if not cfg.pinecone_api_key:
        raise RuntimeError("PINECONE_API_KEY is not set")
    pc = Pinecone(api_key=cfg.pinecone_api_key)
    host = (cfg.pinecone_host or "").strip()
    if host:
        return pc.Index(host=host)
    return pc.Index(cfg.pinecone_index_name)
