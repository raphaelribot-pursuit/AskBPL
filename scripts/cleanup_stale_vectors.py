#!/usr/bin/env python3
"""One-time migration: clear stale standalone-CLI vectors from Pinecone.

The standalone ingest path (askbpl/ingestion/ingest.py) writes content-hash IDs
(e.g. 853d11259a83f5c6). The orchestrator expects UUID chunk IDs hydrated from
Postgres. Run this before re-ingesting via the orchestrator manifest path.

Usage:
  python scripts/cleanup_stale_vectors.py --dry-run
  python scripts/cleanup_stale_vectors.py
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import uuid

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_uuid_vector_id(vector_id: str) -> bool:
    try:
        uuid.UUID(vector_id)
        return bool(UUID_PATTERN.match(vector_id))
    except ValueError:
        return False


def _sample_vector_ids(index, namespace: str, top_k: int = 5) -> list[str]:
    """Fetch a few vector IDs via list + fetch (no query vector required)."""
    try:
        pages = index.list(namespace=namespace, limit=top_k)
        ids: list[str] = []
        for page in pages:
            ids.extend(page)
            if len(ids) >= top_k:
                break
        ids = ids[:top_k]
        if ids:
            return ids
    except Exception:
        pass

    # Fallback: zero vector query (works on most indexes)
    dim = int(os.environ.get("PINECONE_DIMENSIONS", "1536"))
    try:
        result = index.query(
            vector=[0.0] * dim,
            top_k=top_k,
            include_values=False,
            include_metadata=False,
            namespace=namespace or None,
        )
        return [match["id"] for match in result.get("matches", [])]
    except Exception as exc:
        print(f"Warning: could not sample vector IDs: {exc}", file=sys.stderr)
        return []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete stale standalone-CLI vectors from the Ask BPL Pinecone index."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show index stats and sample IDs without deleting.",
    )
    parser.add_argument(
        "--namespace",
        default="",
        help="Pinecone namespace (default: empty string / default namespace).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete even if sample IDs look like orchestrator UUIDs (dangerous).",
    )
    args = parser.parse_args()

    api_key = os.environ.get("PINECONE_API_KEY", "").strip()
    if not api_key:
        print("ERROR: PINECONE_API_KEY is not set.", file=sys.stderr)
        return 1

    index_name = os.environ.get("PINECONE_INDEX_NAME", "askbpl-pilot").strip()
    pinecone_host = os.environ.get("PINECONE_HOST", "").strip()

    from pinecone import Pinecone

    pc = Pinecone(api_key=api_key)
    if pinecone_host:
        index = pc.Index(host=pinecone_host)
        print(f"Connected to index via PINECONE_HOST ({pinecone_host})")
    else:
        index = pc.Index(index_name)
        print(f"Connected to index: {index_name}")

    ns = args.namespace
    ns_label = repr(ns) if ns else "(default namespace)"
    print(f"Namespace: {ns_label}")

    stats = index.describe_index_stats()
    print("\n--- Index stats (before) ---")
    print(stats)

    ns_stats = (stats.get("namespaces") or {}).get(ns, {})
    vector_count = ns_stats.get("vector_count", stats.get("total_vector_count", 0))
    print(f"\nVector count in namespace: {vector_count}")

    sample_ids = _sample_vector_ids(index, ns)
    if sample_ids:
        print("\n--- Sample vector IDs ---")
        for vid in sample_ids:
            kind = "UUID (orchestrator)" if _is_uuid_vector_id(vid) else "hash (standalone CLI)"
            print(f"  {vid}  [{kind}]")

        uuid_samples = [vid for vid in sample_ids if _is_uuid_vector_id(vid)]
        if uuid_samples and not args.force:
            print(
                "\nABORT: Sample IDs look like orchestrator UUID vectors, not stale CLI hashes.",
                file=sys.stderr,
            )
            print(
                "If you are certain these are stale, re-run with --force.",
                file=sys.stderr,
            )
            return 2
    else:
        print("\nNo sample vector IDs returned (index may already be empty).")

    if args.dry_run:
        print("\n[DRY RUN] No vectors deleted.")
        return 0

    if vector_count == 0:
        print("\nIndex namespace is already empty — nothing to delete.")
        return 0

    print("\nDeleting all vectors in namespace...")
    if ns:
        index.delete(delete_all=True, namespace=ns)
    else:
        index.delete(delete_all=True)

    stats_after = index.describe_index_stats()
    print("\n--- Index stats (after) ---")
    print(stats_after)

    ns_stats_after = (stats_after.get("namespaces") or {}).get(ns, {})
    remaining = ns_stats_after.get("vector_count", stats_after.get("total_vector_count", 0))
    print(f"\nRemaining vectors in namespace: {remaining}")

    if remaining:
        print("WARNING: vectors may still remain (eventual consistency). Re-check in a few seconds.")
        return 3

    print("\nDone — namespace cleared.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
