"""LangChain OpenAI embeddings adapter (TRD-RET-4 build-time selection)."""

from __future__ import annotations

from functools import lru_cache
from typing import List

from langchain_openai import OpenAIEmbeddings

from ask_bpl_orchestrator.config import Settings, get_settings


@lru_cache
def _embeddings_client(settings_fingerprint: tuple[str, str]) -> OpenAIEmbeddings:
    model, api_key = settings_fingerprint
    return OpenAIEmbeddings(model=model, api_key=api_key or None)


def settings_fingerprint(settings: Settings) -> tuple[str, str]:
    return (settings.openai_embedding_model, settings.openai_api_key)


async def embed_query(text: str, *, settings: Settings | None = None) -> List[float]:
    cfg = settings or get_settings()
    client = _embeddings_client(settings_fingerprint(cfg))
    return await client.aembed_query(text)
