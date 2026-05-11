"""CLI entry-point for corpus ingestion."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from ask_bpl_orchestrator.ingest.service import ingest_file


SUPPORTED_SUFFIXES = {".pdf", ".docx", ".md", ".markdown", ".txt"}


def _gather_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    files: list[Path] = []
    for candidate in sorted(target.rglob("*")):
        if candidate.suffix.lower() in SUPPORTED_SUFFIXES and candidate.is_file():
            files.append(candidate)
    return files


async def _run(args: argparse.Namespace) -> None:
    corpus_root = Path(args.corpus_root).resolve()
    target = Path(args.path).resolve()

    if not str(target).startswith(str(corpus_root)):
        raise SystemExit("Corpus root must be parent of target path for relative keys")

    collected = _gather_files(target)
    if not collected:
        raise SystemExit("No ingestable files matched")

    title_default = args.title
    version = args.version

    for file_path in collected:
        rel_title = title_default or file_path.stem.replace("_", " ").title()
        await ingest_file(
            absolute_path=file_path,
            corpus_root=corpus_root,
            policy_slug=args.policy,
            title=rel_title,
            version_label=version,
        )
        print(f"ingested:{file_path}")  # noqa: T201 intentional CLI output


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask BPL corpus ingest")
    parser.add_argument("--path", required=True, help="File or folder to ingest")
    parser.add_argument("--corpus-root", default=".", help="Root folder for stable relative paths")
    parser.add_argument("--policy", default="generic_policy", help="Policy slug (must exist in DB)")
    parser.add_argument("--title", default=None, help="Override document title display string")
    parser.add_argument("--version", default="pilot-draft", help="Document version tag")

    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
