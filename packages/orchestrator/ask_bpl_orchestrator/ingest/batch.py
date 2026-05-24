"""Batch corpus ingest from a YAML manifest (Selvon curated set)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import yaml

from ask_bpl_orchestrator.ingest.service import ingest_file


async def ingest_manifest(manifest_path: Path) -> list[str]:
    """Ingest every document listed in *manifest_path*. Returns status lines."""
    manifest_path = manifest_path.resolve()
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    corpus_root = (manifest_path.parent / raw.get("corpus_root", ".")).resolve()
    if not corpus_root.is_dir():
        raise FileNotFoundError(f"corpus_root not found: {corpus_root}")

    documents: list[dict[str, Any]] = raw.get("documents") or []
    if not documents:
        raise ValueError("manifest must list at least one document under `documents`")

    lines: list[str] = []
    for entry in documents:
        rel = entry["path"]
        target = (corpus_root / rel).resolve()
        if not str(target).startswith(str(corpus_root)):
            raise ValueError(f"path escapes corpus_root: {rel}")
        if not target.is_file():
            lines.append(f"failed:{rel}:file_missing")
            continue
        policy = entry.get("policy") or entry.get("policy_type") or "generic_policy"
        title = entry.get("title") or target.stem.replace("_", " ").title()
        version = entry.get("version") or raw.get("default_version") or "pilot-draft"
        try:
            await ingest_file(
                absolute_path=target,
                corpus_root=corpus_root,
                policy_slug=policy,
                title=title,
                version_label=version,
            )
            lines.append(f"indexed:{rel}")
        except Exception as exc:  # noqa: BLE001 batch must continue
            lines.append(f"failed:{rel}:{exc}")
    return lines


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Ingest Selvon corpus from manifest YAML")
    parser.add_argument(
        "--manifest",
        default="sample_corpus/corpus_manifest.yaml",
        help="Path to corpus_manifest.yaml",
    )
    args = parser.parse_args()
    lines = asyncio.run(ingest_manifest(Path(args.manifest).resolve()))
    for line in lines:
        print(line)  # noqa: T201
    failed = [ln for ln in lines if ln.startswith("failed:")]
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
