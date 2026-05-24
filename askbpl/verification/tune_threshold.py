"""Grounding threshold calibration harness (TRD-RET-3)."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import List

from dotenv import load_dotenv

from ingestion.policy_metadata import PROJECT_ROOT
from retrieval.retriever import Retriever, infer_policy_type, load_retrieval_config, max_score
from verification.negative_questions import NEGATIVE_QUESTIONS
from verification.test_questions import TEST_QUESTIONS

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

STATE_PATH = PROJECT_ROOT / "state" / "threshold_tuning.json"
TOP_N_POLICY_CHECK = 3


def _in_scope_pass(chunks, expected_policy: str, threshold: float) -> bool:
    if max_score(chunks) < threshold:
        return False
    top_types = [c.policy_type for c in chunks[:TOP_N_POLICY_CHECK] if c.policy_type]
    return expected_policy in top_types


def tune_threshold() -> dict:
    """Sweep candidate thresholds; recommend best balance (TRD-RET-3)."""
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT.parent / ".env")

    cfg = load_retrieval_config()
    candidates: List[float] = [float(v) for v in cfg.get("threshold_candidates") or []]
    if not candidates:
        candidates = [float(cfg["grounding_threshold"])]

    retriever = Retriever(cfg)

    in_scope_cache = []
    for question, expected in TEST_QUESTIONS:
        chunks = retriever.query(question)
        in_scope_cache.append((question, expected, chunks))

    negative_cache = []
    for question in NEGATIVE_QUESTIONS:
        negative_cache.append((question, retriever.query(question)))

    rows = []
    best_pick = candidates[0]

    print(f"{'threshold':>10}  {'in-scope':>10}  {'OOC refuse':>10}  {'combined':>10}")
    print("-" * 46)

    for threshold in sorted(candidates):
        in_pass = sum(
            1 for _, expected, chunks in in_scope_cache if _in_scope_pass(chunks, expected, threshold)
        )
        ooc_refuse = sum(1 for _, chunks in negative_cache if max_score(chunks) < threshold)
        combined = in_pass + ooc_refuse
        print(f"{threshold:10.2f}  {in_pass:>3}/{len(TEST_QUESTIONS):<6}  {ooc_refuse:>3}/{len(NEGATIVE_QUESTIONS):<6}  {combined:>10}")

        # Prefer max in-scope pass; tie-break with OOC refusal count
        rank = (in_pass, ooc_refuse)
        best_rank = (
            sum(1 for _, expected, chunks in in_scope_cache if _in_scope_pass(chunks, expected, best_pick)),
            sum(1 for _, chunks in negative_cache if max_score(chunks) < best_pick),
        )
        if rank > best_rank:
            best_pick = threshold

        rows.append(
            {
                "threshold": threshold,
                "in_scope_pass": in_pass,
                "in_scope_total": len(TEST_QUESTIONS),
                "out_of_corpus_refuse": ooc_refuse,
                "out_of_corpus_total": len(NEGATIVE_QUESTIONS),
            }
        )

    recommended = best_pick
    current = float(cfg["grounding_threshold"])

    result = {
        "recommended_threshold": recommended,
        "current_config_threshold": current,
        "candidates": rows,
        "acceptance": {
            "in_scope_min_pass": 20,
            "in_scope_at_recommended": next(
                r["in_scope_pass"] for r in rows if r["threshold"] == recommended
            ),
        },
    }

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print("─" * 46)
    print(f"Recommended threshold: {recommended:.2f} (current config: {current:.2f})")
    print(f"Wrote {STATE_PATH.relative_to(PROJECT_ROOT)}")
    if recommended != current:
        print(f"Update config/retrieval.yaml grounding_threshold to {recommended:.2f}")

    return result


def main() -> None:
    try:
        result = tune_threshold()
        if result["acceptance"]["in_scope_at_recommended"] < result["acceptance"]["in_scope_min_pass"]:
            sys.exit(1)
    except Exception as exc:
        logger.exception("Threshold tuning failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
