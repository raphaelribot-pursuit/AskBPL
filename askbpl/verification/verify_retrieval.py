"""Retrieval verification harness entry point (TRD-RET-1)."""

from __future__ import annotations

import logging
import sys
from typing import List

from dotenv import load_dotenv

from ingestion.embedder import Embedder, load_embeddings_config
from ingestion.pinecone_client import PineconeClient, load_pinecone_config
from ingestion.policy_metadata import PROJECT_ROOT
from verification.test_questions import TEST_QUESTIONS

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

TOP_K = 6
TOP_N_CHECK = 3


def _format_hit(metadata: dict, score: float) -> str:
    source = metadata.get("source_document", "unknown")
    section = metadata.get("section") or "—"
    return f"{source} / {section}   score={score:.3f}"


def verify_retrieval() -> tuple[int, int]:
    """Run retrieval checks against pinned embedding model (TRD-RET-1)."""
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT.parent / ".env")
    embed_cfg = load_embeddings_config()
    pine_cfg = load_pinecone_config()
    embedder = Embedder(embed_cfg)
    pine = PineconeClient(pine_cfg)

    passed = 0
    total = len(TEST_QUESTIONS)

    for question, expected_policy in TEST_QUESTIONS:
        query_vector = embedder.embed_query(question)
        response = pine.index.query(vector=query_vector, top_k=TOP_K, include_metadata=True)

        matches = response.get("matches") or []
        top_three_types: List[str] = []
        for match in matches[:TOP_N_CHECK]:
            meta = match.get("metadata") or {}
            policy_type = str(meta.get("policy_type", ""))
            if policy_type:
                top_three_types.append(policy_type)

        ok = expected_policy in top_three_types
        if ok:
            passed += 1

        status = "PASS" if ok else "FAIL"
        top_hit = matches[0] if matches else None
        if top_hit:
            hit_line = _format_hit(top_hit.get("metadata") or {}, float(top_hit.get("score") or 0.0))
        else:
            hit_line = "no matches"

        print(f"[{status}]  {expected_policy:<22} {question}")
        print(f"        top hit: {hit_line}")
        if not ok:
            observed = [str((m.get("metadata") or {}).get("policy_type", "")) for m in matches[:TOP_N_CHECK]]
            print(
                f"        expected policy_type={expected_policy} in top 3, got: {observed}"
            )

    pct = (passed / total * 100) if total else 0.0
    print("─" * 69)
    print(f"Retrieval verification: {passed}/{total} passed ({pct:.1f}%)")
    return passed, total


def main() -> None:
    """CLI entry: python -m verification.verify_retrieval."""
    try:
        passed, total = verify_retrieval()
        if passed < 20:
            sys.exit(1)
    except Exception as exc:
        logger.exception("Verification failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
