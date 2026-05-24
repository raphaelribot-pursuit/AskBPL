"""End-to-end generation verification on in-scope test questions (TRD-GEN-3, TRD-GEN-6)."""

from __future__ import annotations

import logging
import sys

from dotenv import load_dotenv

from ingestion.policy_metadata import PROJECT_ROOT
from orchestrator.ask import ask_question
from verification.test_questions import TEST_QUESTIONS

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

MIN_PASS = 18


def verify_generation() -> tuple[int, int]:
    """Run full ask pipeline on 24 test questions (TRD-GEN-3)."""
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT.parent / ".env")

    passed = 0
    total = len(TEST_QUESTIONS)

    for question, expected_policy in TEST_QUESTIONS:
        resp = ask_question(question)
        ok = (
            resp.response_type == "answer"
            and bool(resp.answer)
            and bool(resp.citations)
            and resp.inferred_policy_type == expected_policy
        )
        if ok:
            passed += 1

        status = "PASS" if ok else "FAIL"
        cite = resp.citations[0].source_document if resp.citations else "—"
        print(f"[{status}]  {expected_policy:<22} {question[:60]}{'…' if len(question) > 60 else ''}")
        if resp.response_type == "answer":
            print(f"        answer: {resp.answer[:120]}{'…' if len(resp.answer or '') > 120 else ''}")
            print(f"        cite: {cite}   score={resp.best_score:.3f}")
        else:
            print(f"        refusal: {resp.refusal_explanation}   score={resp.best_score:.3f}")

    pct = (passed / total * 100) if total else 0.0
    print("─" * 69)
    print(f"Generation verification: {passed}/{total} passed ({pct:.1f}%)")
    return passed, total


def main() -> None:
    try:
        passed, _ = verify_generation()
        if passed < MIN_PASS:
            sys.exit(1)
    except Exception as exc:
        logger.exception("Generation verification failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
