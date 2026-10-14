"""Source inventory -> document eligibility (PRD ING-1, ING-2, ING-9, GATE-02).

The inventory workbook (`Source Inventory` sheet) is the team's per-file disposition.
It is NOT BPL approval. This module is deliberately fail-closed:

  * an unrecognised lifecycle value raises, it is never guessed;
  * `Eligible` is only honoured when a reviewer AND review date are recorded,
    otherwise the row is downgraded to `authority_pending` with a warning;
  * a failed parse check always yields `blocked`, whatever else the row says;
  * a parse check that says "Validated ..." is only a CLAIM: it is honoured when the stored document
    carries a verified extraction-review record (patch 0009), otherwise the row stays `blocked`.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from ask_bpl_orchestrator.db.models import Document, Eligibility, ExtractionStatus

SHEET = "Source Inventory"
_REQUIRED = {
    "Source ID", "File name", "Parse check", "In current pilot index",
    "Lifecycle status (ING-9)", "Reviewer / date",
}


def normalize_name(name: str) -> str:
    """Match files across copies: drop folders, extension, case and `(1)`-style copy suffixes."""
    base = Path(name).name
    base = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", base)
    base = re.sub(r"\s*\(\d\)", "", base)  # "(1)" copy markers; "(04.05)" policy numbers stay
    return re.sub(r"\s+", " ", base).strip().lower()


@dataclass
class InventoryRow:
    source_id: str
    file_name: str
    eligibility: Eligibility
    test_index_member: bool
    owner: Optional[str] = None
    policy_number: Optional[str] = None
    reviewer: Optional[str] = None
    reviewed_at: Optional[date] = None
    note: Optional[str] = None
    extraction_validated_claim: bool = False
    warnings: List[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return normalize_name(self.file_name)


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_review(raw: Optional[str]) -> tuple[Optional[str], Optional[date]]:
    """'Name / 2026-10-12' -> (name, date). Either part may be missing."""
    if not raw:
        return None, None
    found = re.search(r"\d{4}-\d{2}-\d{2}", raw)
    when = datetime.strptime(found.group(0), "%Y-%m-%d").date() if found else None
    who = re.sub(r"\d{4}-\d{2}-\d{2}", "", raw).strip(" /,;-") or None
    return who, when


def derive_eligibility(lifecycle: str, parse_check: str, reviewer: Optional[str], reviewed_at: Optional[date]):
    """Return (Eligibility, warnings). Raises ValueError on an unknown lifecycle value."""
    warnings: List[str] = []
    life = (lifecycle or "").strip().lower()
    parse_failed = (parse_check or "").strip().lower().startswith("fail")

    if life.startswith("excluded"):
        return Eligibility.excluded, warnings
    if life.startswith("superseded"):
        return Eligibility.superseded, warnings
    if parse_failed or "extraction blocked" in life or life.startswith("blocked"):
        return Eligibility.blocked, warnings
    if life.startswith("eligible"):
        if reviewer and reviewed_at:
            return Eligibility.eligible, warnings
        warnings.append("marked Eligible without reviewer and date; treated as authority_pending")
        return Eligibility.authority_pending, warnings
    if life.startswith("authority pending"):
        return Eligibility.authority_pending, warnings
    raise ValueError(f"Unrecognised lifecycle status {lifecycle!r}")


def load_inventory(path: Path) -> Dict[str, InventoryRow]:
    """Read the inventory workbook into {normalized file key: InventoryRow}."""
    import openpyxl  # local import: only needed for ingest tooling

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    if SHEET not in wb.sheetnames:
        raise ValueError(f"{path.name}: sheet {SHEET!r} not found")
    rows = list(wb[SHEET].iter_rows(values_only=True))
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    missing = _REQUIRED - set(header)
    if missing:
        raise ValueError(f"{path.name}: missing columns {sorted(missing)}")
    col = {name: i for i, name in enumerate(header)}

    def get(r: tuple, name: str) -> Optional[str]:
        i = col.get(name)
        return _clean(r[i]) if i is not None and i < len(r) else None

    out: Dict[str, InventoryRow] = {}
    for r in rows[1:]:
        source_id = get(r, "Source ID")
        file_name = get(r, "File name")
        if not source_id or not file_name:
            continue
        reviewer, reviewed_at = _parse_review(get(r, "Reviewer / date"))
        elig, warnings = derive_eligibility(
            get(r, "Lifecycle status (ING-9)") or "", get(r, "Parse check") or "", reviewer, reviewed_at
        )
        in_pilot = (get(r, "In current pilot index") or "").lower().startswith("y")
        row = InventoryRow(
            source_id=source_id,
            file_name=file_name,
            eligibility=elig,
            # Test-index membership only has meaning while authority is pending (OD-11).
            test_index_member=in_pilot and elig == Eligibility.authority_pending,
            owner=get(r, "Owner (D-02)"),
            policy_number=get(r, "Policy number / dates (from document, to confirm)"),
            reviewer=reviewer,
            reviewed_at=reviewed_at,
            note=get(r, "Notes (PRD v1.2 s19.3 / 19.4)"),
            extraction_validated_claim=(get(r, "Parse check") or "").strip().lower().startswith("validated"),
            warnings=warnings,
        )
        if row.key in out:
            raise ValueError(f"Duplicate inventory file name after normalisation: {file_name}")
        out[row.key] = row
    return out


def apply_row(doc: Document, row: InventoryRow) -> None:
    """Copy a disposition onto a Document (does not touch chunks or vectors)."""
    doc.source_id = row.source_id
    doc.eligibility = row.eligibility
    doc.test_index_member = row.test_index_member
    doc.owner = row.owner
    doc.policy_number = row.policy_number
    doc.reviewed_by = row.reviewer
    doc.reviewed_at = row.reviewed_at
    doc.status_note = row.note


async def apply_inventory_to_db(
    db, inventory: Dict[str, InventoryRow], *, purge_vectors: bool = False, scope=None
) -> List[str]:
    """Match stored documents to inventory rows by file name and set their disposition.

    `scope` optionally limits the run to those document IDs (used by tests so they never
    touch real documents in a shared database). The CLI always runs unscoped.
    """
    lines: List[str] = []
    query = select(Document)
    if scope is not None:
        query = query.where(Document.document_id.in_(list(scope)))
    docs = (await db.execute(query)).scalars().all()
    lines.append(f"found:{len(docs)}:stored documents")
    if not docs:
        lines.append("error:no stored documents; run askbpl-ingest-batch first (and check DATABASE_URL)")
        return lines
    # Two stored documents that resolve to the same inventory row are the same policy
    # ingested under different paths. Refuse before changing anything.
    by_key: Dict[str, List[Document]] = {}
    for doc in docs:
        key = normalize_name(doc.source_path or doc.title)
        if key in inventory:
            by_key.setdefault(key, []).append(doc)
    dupes = {k: v for k, v in by_key.items() if len(v) > 1}
    if dupes:
        for key, group in dupes.items():
            paths = " | ".join(sorted(d.source_path or d.title for d in group))
            lines.append(f"error:duplicate:{inventory[key].source_id}:{len(group)} stored documents match: {paths}")
        lines.append("error:nothing was changed; remove the duplicate documents (and their vectors) first")
        await db.rollback()
        return lines

    seen: set[str] = set()
    to_purge: List[str] = []
    for doc in docs:
        key = normalize_name(doc.source_path or doc.title)
        row = inventory.get(key)
        if row is None:
            # Default-deny: a stored document with no inventory row is not answerable.
            doc.eligibility = Eligibility.authority_pending
            doc.test_index_member = False
            lines.append(f"unlisted:{doc.source_path}:not answerable until it has an inventory row")
            continue
        seen.add(key)
        if row.extraction_validated_claim and doc.extraction_status != ExtractionStatus.validated:
            # The workbook says the extraction was validated, but this stored document has no verified
            # review record. Fail closed: the workbook alone cannot make scanned text answerable.
            lines.append(
                f"warning:{row.source_id}:inventory says extraction is validated but no verified review record "
                "is stored for this document; kept blocked (ingest it with its validated_extraction record)"
            )
            row = replace(row, eligibility=Eligibility.blocked, test_index_member=False)
        elif doc.extraction_status == ExtractionStatus.review_required:
            lines.append(
                f"warning:{row.source_id}:stored extraction is review_required; not answerable until a person's "
                "validation record is ingested"
            )
        apply_row(doc, row)
        lines.append(
            f"{row.source_id}:{row.eligibility.value}"
            f"{':test_index' if row.test_index_member else ''}:{doc.source_path}"
        )
        for w in row.warnings:
            lines.append(f"warning:{row.source_id}:{w}")
        if row.eligibility in (Eligibility.blocked, Eligibility.excluded, Eligibility.superseded):
            to_purge.append(str(doc.document_id))
    for key, row in inventory.items():
        if key not in seen:
            lines.append(f"not_ingested:{row.source_id}:{row.eligibility.value}:{row.file_name}")
    await db.commit()

    if purge_vectors and to_purge:
        from ask_bpl_orchestrator.db.models import Chunk
        from ask_bpl_orchestrator.ingest.service import pinecone_bulk_delete

        ids = (
            await db.execute(select(Chunk.chunk_id).where(Chunk.document_id.in_(to_purge)))
        ).scalars().all()
        await asyncio.to_thread(pinecone_bulk_delete, [str(i) for i in ids])
        lines.append(f"purged_vectors:{len(ids)}")
    return lines


def main() -> None:
    import argparse

    from ask_bpl_orchestrator.config import get_settings
    from ask_bpl_orchestrator.db.session import async_session_factory

    parser = argparse.ArgumentParser(description="Apply source-inventory dispositions to stored documents")
    parser.add_argument("--inventory", default=get_settings().source_inventory_path)
    parser.add_argument("--dry-run", action="store_true", help="Parse and print the dispositions only")
    parser.add_argument(
        "--purge-vectors",
        action="store_true",
        help="Also delete Pinecone vectors of blocked/excluded/superseded documents",
    )
    args = parser.parse_args()
    inv = load_inventory(Path(args.inventory))
    if args.dry_run:
        for row in inv.values():
            print(f"{row.source_id}:{row.eligibility.value}{':test_index' if row.test_index_member else ''}:{row.file_name}")  # noqa: T201
        return

    async def _run() -> List[str]:
        async with async_session_factory() as db:
            return await apply_inventory_to_db(db, inv, purge_vectors=args.purge_vectors)

    out = asyncio.run(_run())
    for line in out:
        print(line)  # noqa: T201
    if any(line.startswith("error:") for line in out):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
