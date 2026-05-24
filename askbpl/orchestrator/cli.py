"""CLI entry: python -m orchestrator.cli \"your question\""""

from __future__ import annotations

import argparse
import logging
import sys

from orchestrator.ask import ask_question, format_response

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask BPL — closed-corpus policy Q&A")
    parser.add_argument("question", nargs="+", help="Question text")
    args = parser.parse_args()
    question = " ".join(args.question).strip()
    if not question:
        print("Question cannot be empty.", file=sys.stderr)
        sys.exit(1)
    try:
        resp = ask_question(question)
        print(format_response(resp))
        if resp.response_type != "answer":
            sys.exit(2)
    except Exception as exc:
        logging.getLogger(__name__).exception("Ask failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
