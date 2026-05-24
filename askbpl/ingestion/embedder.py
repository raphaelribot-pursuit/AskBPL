"""OpenAI embedding client (TRD-IGN-2, TRD-RET-1)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

import tiktoken
import yaml
from openai import OpenAI, RateLimitError

from ingestion.policy_metadata import PROJECT_ROOT

logger = logging.getLogger(__name__)

EMBEDDINGS_PATH = PROJECT_ROOT / "config" / "embeddings.yaml"
BATCH_SIZE = 100
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 2.0


@dataclass(frozen=True)
class EmbeddingResult:
    """One embedding vector and its input token count."""

    embedding: List[float]
    token_count: int


def load_embeddings_config(path: Path = EMBEDDINGS_PATH) -> dict:
    """Load pinned embedding model settings (TRD-RET-1)."""
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class Embedder:
    """Batch OpenAI embeddings with retry (TRD-RET-1)."""

    def __init__(self, config: dict | None = None, client: OpenAI | None = None) -> None:
        self.config = config or load_embeddings_config()
        self.model: str = str(self.config["model"])
        self.dimensions: int = int(self.config["dimensions"])
        self._client = client or OpenAI()
        self._enc = tiktoken.get_encoding("cl100k_base")

    def embed_texts(self, texts: Sequence[str]) -> List[EmbeddingResult]:
        """Embed texts in batches; returns vectors and token counts (TRD-RET-1)."""
        results: List[EmbeddingResult] = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = list(texts[start : start + BATCH_SIZE])
            batch_results = self._embed_batch(batch)
            results.extend(batch_results)
            logger.info("Embedded batch %s–%s of %s", start + 1, start + len(batch), len(texts))
        return results

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query string (TRD-RET-1)."""
        return self.embed_texts([text])[0].embedding

    def _embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._client.embeddings.create(
                    model=self.model,
                    input=texts,
                    dimensions=self.dimensions,
                )
                return [
                    EmbeddingResult(
                        embedding=list(item.embedding),
                        token_count=len(self._enc.encode(texts[i])),
                    )
                    for i, item in enumerate(response.data)
                ]
            except RateLimitError:
                if attempt >= MAX_RETRIES:
                    raise
                wait = BASE_BACKOFF_SECONDS * (2**attempt)
                logger.warning("Rate limited; retrying in %.1fs (attempt %s)", wait, attempt + 1)
                time.sleep(wait)
        raise RuntimeError("Unreachable embed retry loop")
