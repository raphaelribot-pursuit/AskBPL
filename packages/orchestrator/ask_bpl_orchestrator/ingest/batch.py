"""Batch corpus ingest from a YAML manifest (Selvon curated set)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import yaml

from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.db.models import Eligibility
from ask_bpl_orchestrator.ingest.inventory import load_inventory, normalize_name
from ask_bpl_orchestrator.ingest.service import ingest_file


async def ingest_manifest(manifest_path: Path, inventory_path: Path | None = None) -> list[str]:
    """Ingest every document listed in *manifest_path*. Returns status lines."""
    manifest_path = manifest_path.resolve()
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    corpus_root = (manifest_path.parent / raw.get("corpus_root", ".")).resolve()
    if not corpus_root.is_dir():
        raise FileNotFoundError(f"corpus_root not found: {corpus_root}")

    documents: list[dict[str, Any]] = raw.get("documents") or []
    if not documents:
        raise ValueError("manifest must list at least one document under `documents`")

    # Per-document dispositions. A missing inventory is an error, never a silent skip.
    inv_file = inventory_path
    if inv_file is None:
        configured = Path(get_settings().source_inventory_path)
        options = [configured] if configured.is_absolute() else [
            Path.cwd() / configured,
            manifest_path.parent.parent / configured,
        ]
        inv_file = next((p for p in options if p.is_file()), None)
        if inv_file is None:
            raise FileNotFoundError(f"source inventory not found (looked for {configured}); see SOURCE_INVENTORY_PATH")
    inventory = load_inventory(inv_file)

    lines: list[str] = []
    for entry in documents:
        rel = entry["path"]
        target = (corpus_root / rel).resolve()
        if not str(target).startswith(str(corpus_root)):
            raise ValueError(f"path escapes corpus_root: {rel}")
        if not target.is_file():
            lines.append(f"failed:{rel}:file_missing")
            continue
        inv_row = inventory.get(normalize_name(rel))
        if inv_row is not None and inv_row.eligibility in (Eligibility.blocked, Eligibility.excluded):
            lines.append(f"refused:{rel}:{inv_row.eligibility.value}:{inv_row.source_id}")
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
                inventory_row=inv_row,
            )
            lines.append(f"indexed:{rel}")
        except Exception as exc:  # noqa: BLE001 batch must continue
            lines.append(f"failed:{rel}:{exc}")
    return lines


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Ingest Selvon corpus from manifest YAML")
    parser.add_argument("--inventory", default=None, help="Source inventory xlsx (default: SOURCE_INVENTORY_PATH)")
    parser.add_argument(
        "--manifest",
        default="sample_corpus/corpus_manifest_pilot.yaml",
        help="Path to corpus manifest YAML (default: pilot PDFs)",
    )
    args = parser.parse_args()
    lines = asyncio.run(
        ingest_manifest(Path(args.manifest).resolve(), Path(args.inventory).resolve() if args.inventory else None)
    )
    for line in lines:
        print(line)  # noqa: T201
    failed = [ln for ln in lines if ln.startswith("failed:")]
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
