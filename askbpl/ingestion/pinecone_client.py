"""Pinecone index management and upsert (TRD-IGN-4)."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

import yaml
from pinecone import Pinecone, ServerlessSpec

from ingestion.policy_metadata import PROJECT_ROOT

logger = logging.getLogger(__name__)

PINECONE_PATH = PROJECT_ROOT / "config" / "pinecone.yaml"
UPSERT_BATCH_SIZE = 100


@dataclass(frozen=True)
class VectorRecord:
    """One Pinecone vector with metadata."""

    vector_id: str
    values: List[float]
    metadata: Dict[str, Any]


def load_pinecone_config(path: Path = PINECONE_PATH) -> dict:
    """Load Pinecone index settings."""
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def make_vector_id(source_document: str, chunk_text: str) -> str:
    """Deterministic vector ID for idempotent re-ingest (TRD-IGN-4)."""
    digest = hashlib.sha256(f"{source_document}::{chunk_text}".encode("utf-8")).hexdigest()
    return digest[:16]


class PineconeClient:
    """Create-or-connect index and upsert vectors (TRD-IGN-4)."""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or load_pinecone_config()
        self.index_name: str = str(self.config["index_name"])
        self.metric: str = str(self.config["metric"])
        self.dimensions: int = int(self.config["dimensions"])
        self.cloud: str = str(self.config["cloud"])
        self.region: str = str(self.config["region"])
        self._pc = Pinecone()
        self._index = self._ensure_index()

    def _ensure_index(self):
        """Create serverless index if missing."""
        existing = {item.name for item in self._pc.list_indexes()}
        if self.index_name not in existing:
            logger.info("Creating Pinecone index %s", self.index_name)
            self._pc.create_index(
                name=self.index_name,
                dimension=self.dimensions,
                metric=self.metric,
                spec=ServerlessSpec(cloud=self.cloud, region=self.region),
            )
        return self._pc.Index(self.index_name)

    @property
    def index(self):
        return self._index

    def describe_stats(self) -> dict:
        """Return index statistics for idempotency checks."""
        return self._index.describe_index_stats()

    def upsert_records(self, records: Sequence[VectorRecord]) -> int:
        """Upsert vectors in batches of 100 (TRD-IGN-4)."""
        total = 0
        for start in range(0, len(records), UPSERT_BATCH_SIZE):
            batch = records[start : start + UPSERT_BATCH_SIZE]
            payload = [
                {"id": rec.vector_id, "values": rec.values, "metadata": rec.metadata}
                for rec in batch
            ]
            self._index.upsert(vectors=payload)
            total += len(batch)
            logger.info("Upserted %s vectors (%s total)", len(batch), total)
        return total
