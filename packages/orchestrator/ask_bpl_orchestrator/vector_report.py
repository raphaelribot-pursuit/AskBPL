"""askbpl-vector-report: READ-ONLY comparison of the stored passages with the vectors in Pinecone (patch 0022).

    askbpl-vector-report                  # database + Pinecone
    askbpl-vector-report --csv out.csv    # also write the per-document table (the only thing this command writes)
    askbpl-vector-report --strict         # exit 1 on an URGENT or WARN finding, or when either side cannot be read

The corpus report (patch 0020) says what the database holds and "Pinecone was not asked". This command asks Pinecone,
using only reads, and answers: does every stored passage have a vector, and does the index hold vectors that the
database does not know about?

Checks (all read-only):
  A  every stored chunk has a vector                       (fetch by id; no query, no embedding, no OpenAI call)
  B  vectors in the index that no stored chunk accounts for (list ids; serverless indexes only, else a count)
  C  documents that cannot answer but still hold vectors
  D  the vector's recorded document matches the chunk's document
  E  index and namespace summary

It changes nothing. The Pinecone handle is wrapped so that only ``fetch``, ``list`` and ``describe_index_stats`` can be
called at all; the database connection is declared READ ONLY. Error text from either service is never printed, only the
fixed sentences from ``doctor.py``. It does not embed, so it costs no OpenAI request.

What it cannot tell you (the report says so every time):

* that a vector encodes the right text (it confirms ids and recorded metadata only),
* that answers are correct, that a policy is current, or that BPL has approved anything,
* whether a stray vector actually cost a question a retrieval slot (that needs a live query).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from ask_bpl_orchestrator.config import Settings
from ask_bpl_orchestrator.corpus_report import _csv_safe
from ask_bpl_orchestrator.doctor import _ERROR_WORDS, alembic_head, classify_error, describe_database_target

URGENT, WARN, NOTE = "urgent", "warn", "note"
FETCH_BATCH = 100          # ids per fetch call (the id list travels in the request address)
LIST_LIMIT = 50_000        # stop listing here and say so; a policy library is nowhere near this
ORPHAN_DETAIL_LIMIT = 500  # orphan vectors whose metadata is read; the rest are counted only
CALL_TIMEOUT_SECONDS = 30.0

_END = object()
ALLOWED_INDEX_CALLS = frozenset({"fetch", "list", "describe_index_stats"})

CANNOT_TELL = (
    "This confirms that vector ids exist and what document they record. It does not confirm that a vector encodes the right text.",
    "Nothing here shows that answers are right, that a policy is current, or that BPL has approved it.",
    "It cannot say whether a stray vector cost a question a retrieval slot; that needs a live query.",
    "Only the default namespace is read, because it is the only one the application queries.",
)


# ------------------------------------------------------------------------------------------------ the read-only handle
class ReadOnlyIndex:
    """Lets exactly three read calls through. Anything else (upsert, delete, update, query ...) raises."""

    def __init__(self, index: Any) -> None:
        object.__setattr__(self, "_index", index)

    def __getattr__(self, name: str) -> Any:
        if name not in ALLOWED_INDEX_CALLS:
            raise PermissionError(f"vector report is read-only: '{name}' is not allowed")
        return getattr(object.__getattribute__(self, "_index"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        raise PermissionError("vector report is read-only")


def _call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run one blocking Pinecone call with a time limit (the SDK has no common timeout argument)."""
    box: Dict[str, Any] = {}

    def run() -> None:
        try:
            box["value"] = fn(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - re-raised in the caller's thread
            box["error"] = exc

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(CALL_TIMEOUT_SECONDS)
    if t.is_alive():
        raise TimeoutError("pinecone call timed out")
    if "error" in box:
        raise box["error"]
    return box.get("value")


# ------------------------------------------------------------------------------------------------ data
@dataclass
class DbDocument:
    document_id: str
    title: str
    source_id: Optional[str]
    source_path: Optional[str]
    ingest_status: str
    answerable: bool
    chunk_ids: List[str] = field(default_factory=list)


@dataclass
class DbFacts:
    state: str = "skipped"  # skipped | checked | unreachable | not_migrated | out_of_date
    error_kind: str = ""
    target: str = ""
    docs: List[DbDocument] = field(default_factory=list)

    @property
    def checked(self) -> bool:
        return self.state == "checked"

    @property
    def chunk_total(self) -> int:
        return sum(len(d.chunk_ids) for d in self.docs)


@dataclass
class Orphan:
    vector_id: str
    document_id: str = ""
    title: str = ""


@dataclass
class DocCheck:
    doc: DbDocument
    found: int = 0
    missing: List[str] = field(default_factory=list)
    mismatched: List[str] = field(default_factory=list)  # found, but the vector records another document


@dataclass
class PineFacts:
    state: str = "skipped"  # skipped | checked | unreachable | no_key
    error_kind: str = ""
    checks: Dict[str, DocCheck] = field(default_factory=dict)
    default_count: Optional[int] = None
    other_namespaces: Dict[str, int] = field(default_factory=dict)
    list_state: str = "skipped"  # ok | unavailable | truncated | skipped
    listed: int = 0
    orphans: List[Orphan] = field(default_factory=list)  # every orphan id; metadata only for the first ORPHAN_DETAIL_LIMIT
    orphan_detail_read: int = 0

    @property
    def checked(self) -> bool:
        return self.state == "checked"


@dataclass
class Finding:
    code: str
    severity: str
    subject: str
    text: str
    todo: str = ""


@dataclass
class VectorReport:
    db: DbFacts
    pine: PineFacts
    headline: str
    findings: List[Finding]
    rows: List[DocCheck]

    @property
    def needs_attention(self) -> List[Finding]:
        return [f for f in self.findings if f.severity in (URGENT, WARN)]


# ------------------------------------------------------------------------------------------------ response shapes
def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def fetched_vectors(response: Any) -> Dict[str, Dict[str, Any]]:
    """id -> metadata, from a fetch response (SDK object or plain dict)."""
    vectors = _get(response, "vectors") or {}
    out: Dict[str, Dict[str, Any]] = {}
    for vid, vec in dict(vectors).items():
        meta = _get(vec, "metadata") or {}
        out[str(vid)] = dict(meta) if isinstance(meta, dict) else {}
    return out


def listed_ids(page: Any) -> List[str]:
    """Ids from one page of ``index.list()``: older SDKs yield lists of ids, newer ones yield response objects."""
    if isinstance(page, (list, tuple, set)):
        items = page
    else:
        items = _get(page, "vectors") or _get(page, "ids") or []
    ids: List[str] = []
    for item in items:
        ids.append(str(item if isinstance(item, str) else _get(item, "id")))
    return ids


def namespace_counts(stats: Any) -> Tuple[Optional[int], Dict[str, int]]:
    """(default-namespace count, other namespaces) from describe_index_stats. The count is None when it cannot be told."""
    raw = dict(_get(stats, "namespaces") or {})
    if not raw:
        total = _get(stats, "total_vector_count")
        return (int(total) if total is not None else None), {}  # no breakdown: only the default namespace exists
    default = 0
    others: Dict[str, int] = {}
    for name, info in raw.items():
        n = int(_get(info, "vector_count", 0) or 0)
        if name in ("", "__default__"):
            default += n
        else:
            others[str(name)] = n
    return default, others


# ------------------------------------------------------------------------------------------------ gathering
async def gather_db_facts(settings: Settings, head: Optional[str] = None, scope: Optional[Iterable[Any]] = None) -> DbFacts:
    """Read-only look at the stored documents and chunk ids. The transaction is declared READ ONLY."""
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from ask_bpl_orchestrator.db.models import Chunk, Document
    from ask_bpl_orchestrator.services.eligibility import retrievable_clause

    facts = DbFacts(target=describe_database_target(settings.database_url))
    engine = create_async_engine(settings.database_url, poolclass=NullPool, connect_args={"timeout": 5})
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            await conn.execute(text("SELECT 1"))
            try:
                row = (await conn.execute(text("SELECT version_num FROM alembic_version"))).first()
                revision = row[0] if row else None
            except Exception:  # noqa: BLE001 - a missing table means "not migrated"
                await conn.rollback()
                await conn.execute(text("SET TRANSACTION READ ONLY"))
                revision = None
            if revision is None:
                facts.state = "not_migrated"
                await conn.rollback()
                return facts
            if head is not None and revision != head:
                facts.state = "out_of_date"
                await conn.rollback()
                return facts

            ids = None if scope is None else list(scope)
            docs_q = select(
                Document.document_id, Document.title, Document.source_id, Document.source_path, Document.ingest_status
            ).order_by(Document.source_path, Document.title)
            chunks_q = select(Chunk.document_id, Chunk.chunk_id).order_by(Chunk.document_id, Chunk.ordinal)
            answer_q = select(Document.document_id).where(retrievable_clause(settings))
            if ids is not None:
                docs_q = docs_q.where(Document.document_id.in_(ids))
                chunks_q = chunks_q.where(Chunk.document_id.in_(ids))
                answer_q = answer_q.where(Document.document_id.in_(ids))
            answerable = {str(i) for i in (await conn.execute(answer_q)).scalars().all()}
            by_doc: Dict[str, DbDocument] = {}
            for r in (await conn.execute(docs_q)).all():
                d = DbDocument(
                    document_id=str(r[0]), title=r[1] or "", source_id=r[2], source_path=r[3],
                    ingest_status=getattr(r[4], "value", str(r[4])), answerable=str(r[0]) in answerable,
                )
                by_doc[d.document_id] = d
                facts.docs.append(d)
            for did, cid in (await conn.execute(chunks_q)).all():
                if str(did) in by_doc:
                    by_doc[str(did)].chunk_ids.append(str(cid))
            facts.state = "checked"
            await conn.rollback()
    except Exception as exc:  # noqa: BLE001 - classify, never print the error's own text
        facts.state = "unreachable"
        facts.error_kind = classify_error(exc)
        facts.docs = []
    finally:
        await engine.dispose()
    return facts


def gather_pinecone_facts(index: Any, db: DbFacts) -> PineFacts:
    """Ask Pinecone, with reads only. `index` should already be a ReadOnlyIndex (main() guarantees it)."""
    pine = PineFacts()
    try:
        stats = _call(index.describe_index_stats)
        pine.default_count, pine.other_namespaces = namespace_counts(stats)

        owner: Dict[str, str] = {}  # chunk id -> the document that owns it in the database
        for d in db.docs:
            pine.checks[d.document_id] = DocCheck(doc=d)
            for cid in d.chunk_ids:
                owner[cid] = d.document_id

        # A: fetch every stored chunk id
        ordered = list(owner)
        for start in range(0, len(ordered), FETCH_BATCH):
            batch = ordered[start : start + FETCH_BATCH]
            found = fetched_vectors(_call(index.fetch, ids=batch))
            for cid in batch:
                check = pine.checks[owner[cid]]
                if cid not in found:
                    check.missing.append(cid)
                    continue
                check.found += 1
                recorded = str(found[cid].get("document_id", ""))  # D
                if recorded != owner[cid]:
                    check.mismatched.append(cid)
    except Exception as exc:  # noqa: BLE001 - classify, never print the error's own text
        pine.state = "unreachable"
        pine.error_kind = classify_error(exc)
        pine.checks = {}
        return pine

    # B: list the ids in the index (serverless only). A failure here is a degraded result, not a failed report.
    known = set(owner)
    try:
        seen: List[str] = []
        truncated = False
        pages = _call(lambda: iter(index.list()))
        while True:
            page = _call(next, pages, _END)  # every step is a read, and every step has a time limit
            if page is _END:
                break
            seen.extend(listed_ids(page))
            if len(seen) >= LIST_LIMIT:
                truncated = True
                break
        pine.listed = len(seen)
        pine.list_state = "truncated" if truncated else "ok"
        pine.orphans = [Orphan(vector_id=i) for i in seen if i not in known]
    except Exception:  # noqa: BLE001 - listing is unsupported on pod-based indexes; say so, never guess "no orphans"
        pine.list_state = "unavailable"
        pine.orphans = []

    if pine.orphans:
        head = pine.orphans[:ORPHAN_DETAIL_LIMIT]
        try:
            for start in range(0, len(head), FETCH_BATCH):
                batch = head[start : start + FETCH_BATCH]
                meta = fetched_vectors(_call(index.fetch, ids=[o.vector_id for o in batch]))
                for o in batch:
                    m = meta.get(o.vector_id, {})
                    o.document_id = str(m.get("document_id", "") or "")
                    o.title = str(m.get("title", "") or "")
                pine.orphan_detail_read += len(batch)
        except Exception:  # noqa: BLE001 - the ids are still reported; only titles are lost
            pass
    pine.state = "checked"
    return pine


# ------------------------------------------------------------------------------------------------ report
def _label(d: DbDocument) -> str:
    return d.source_id or d.source_path or d.title or d.document_id[:8]


def build_report(db: DbFacts, pine: PineFacts) -> VectorReport:
    findings: List[Finding] = []
    rows: List[DocCheck] = []

    if not db.checked:
        return VectorReport(db, pine, f"The database {_db_words(db)}, so nothing was compared.", findings, rows)
    if not pine.checked:
        why = "no Pinecone key is set" if pine.state == "no_key" else "Pinecone could not be read" if pine.state == "unreachable" else "Pinecone was not asked"
        return VectorReport(db, pine, f"{db.chunk_total} chunks are stored in the database, but {why}, so nothing was compared.", findings, rows)

    rows = [pine.checks[d.document_id] for d in db.docs if d.document_id in pine.checks]
    missing_total = sum(len(r.missing) for r in rows)
    found_total = sum(r.found for r in rows)
    orphan_total = len(pine.orphans)
    db_ids = {d.document_id for d in db.docs}

    # A: missing vectors
    for r in rows:
        if not r.missing:
            continue
        label = _label(r.doc)
        if r.doc.answerable:
            findings.append(Finding(
                "answerable_missing_vectors", URGENT, label,
                f"{len(r.missing)} of {len(r.doc.chunk_ids)} stored passages have no vector in Pinecone, and this document can answer questions today. "
                "Those passages can never be retrieved.",
                "Re-run askbpl-ingest-batch for this document, then run this report again. If it keeps failing, run askbpl-doctor --live.",
            ))
        # a document that cannot answer anyway and is missing vectors is expected: not reported as a finding

    # D: metadata disagreement
    for r in rows:
        if r.mismatched:
            findings.append(Finding(
                "metadata_mismatch", WARN, _label(r.doc),
                f"{len(r.mismatched)} vectors exist under this document's chunk ids but record a different document (or none).",
                "Re-run askbpl-ingest-batch for this document, then run this report again.",
            ))

    # B: orphans
    if pine.list_state in ("ok", "truncated"):
        stale = [o for o in pine.orphans if o.document_id and o.document_id in db_ids]
        foreign = [o for o in pine.orphans if not (o.document_id and o.document_id in db_ids)]
        if stale:
            names = _group_titles(stale)
            findings.append(Finding(
                "stale_vectors_for_stored_document", WARN, f"{len(stale)} vectors",
                f"These vectors belong to a document this database holds, but their chunk ids no longer exist here ({names}). "
                "Each can use up one of the 6 retrieval slots before it is dropped.",
                "Do not delete anything on the strength of this report. Re-run askbpl-ingest-batch for those documents, then run this report again; "
                "a separate, reviewed purge command is planned (not part of this patch).",
            ))
        if foreign:
            names = _group_titles(foreign)
            more = "" if pine.orphan_detail_read >= len(pine.orphans) else f" (titles were read for the first {pine.orphan_detail_read} only)"
            findings.append(Finding(
                "vectors_for_unknown_document", NOTE, f"{len(foreign)} vectors",
                f"The index holds vectors for documents this database does not know ({names}){more}. If several machines share this index "
                "(each with its own database) these are expected: they are another machine's passages. This report cannot tell them from leftovers.",
                "If this is the only database that should use the index, ask the build team before removing anything.",
            ))
        if pine.list_state == "truncated":
            findings.append(Finding(
                "list_truncated", NOTE, "orphan check",
                f"Listing stopped at {LIST_LIMIT} ids, so the orphan check is incomplete.", "Ask the build team.",
            ))
    else:
        surplus = (pine.default_count or 0) - db.chunk_total
        findings.append(Finding(
            "orphan_check_unavailable", NOTE, "orphan check",
            "Pinecone would not list vector ids on this index (listing works on serverless indexes only), so which vectors have no stored chunk cannot be shown.",
            "",
        ))
        if surplus > 0:
            findings.append(Finding(
                "count_surplus", NOTE, "count only",
                f"By count alone the default namespace holds {surplus} more vectors than the database has chunks "
                f"({pine.default_count} versus {db.chunk_total}). This is a count, not a list: it also moves when vectors are missing, "
                "and it is expected if several machines share the index.", "",
            ))

    # C: non-answerable documents holding vectors
    for r in rows:
        if not r.doc.answerable and r.found > 0:
            findings.append(Finding(
                "vectors_on_document_that_cannot_answer", NOTE, _label(r.doc),
                f"This document cannot answer questions today (it is blocked, excluded, superseded, not yet confirmed, or not indexed), "
                f"but {r.found} of its vectors are in Pinecone. They cannot be returned as answers, but they can use retrieval slots.",
                "To remove them, askbpl-apply-inventory --purge-vectors (it affects every blocked, excluded or superseded document).",
            ))

    headline = (
        f"{db.chunk_total} chunks are stored in the database; {found_total} have a vector in Pinecone and {missing_total} do not. "
        + (f"{orphan_total} vectors in the index are not accounted for by this database." if pine.list_state in ("ok", "truncated")
           else "Vectors with no stored chunk could not be listed on this index.")
    )
    return VectorReport(db, pine, headline, findings, rows)


def _group_titles(orphans: Sequence[Orphan]) -> str:
    counts: Dict[str, int] = {}
    for o in orphans:
        key = o.title or (f"document {o.document_id[:8]}" if o.document_id else "no metadata")
        counts[key] = counts.get(key, 0) + 1
    shown = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    text = "; ".join(f"{name}: {n}" for name, n in shown[:8])
    return text + ("; ..." if len(shown) > 8 else "")


def _db_words(db: DbFacts) -> str:
    if db.state == "unreachable":
        return f"could not be reached ({_ERROR_WORDS.get(db.error_kind, _ERROR_WORDS['unknown'])})"
    if db.state == "not_migrated":
        return "has not been set up yet (run alembic upgrade head)"
    if db.state == "out_of_date":
        return "is older than this code (run alembic upgrade head)"
    return "was not read"


SEVERITY_TITLE = {URGENT: "URGENT", WARN: "WARN", NOTE: "NOTES"}


def render(report: VectorReport, *, summary_only: bool = False) -> str:
    out: List[str] = []
    w = out.append
    w("Ask BPL vector report (read-only)")
    w(f"Database: {report.db.target or 'not read'}")
    w("")
    w(report.headline)
    w("")
    if report.pine.checked:
        p = report.pine
        w("INDEX (default namespace is the only one read)")
        w(f"  vectors in the default namespace  {p.default_count if p.default_count is not None else 'unknown'}")
        if p.other_namespaces:
            for name, n in sorted(p.other_namespaces.items()):
                w(f"  other namespace '{name}'  {n} vectors (the application does not query it)")
        else:
            w("  other namespaces                  none")
        w("")
    if report.db.checked and report.pine.state == "unreachable":
        w(f"Pinecone could not be read: {_ERROR_WORDS.get(report.pine.error_kind, _ERROR_WORDS['unknown'])}")
        w("")
    elif report.db.checked and report.pine.state == "no_key":
        w("PINECONE_API_KEY is not set, so Pinecone was not asked.")
        w("")
    for sev in (URGENT, WARN):
        items = [f for f in report.findings if f.severity == sev]
        if items:
            w(f"{SEVERITY_TITLE[sev]} ({len(items)})")
            for f in items:
                w(f"  [{f.code}] {f.subject}: {f.text}")
                if f.todo:
                    w(f"      do: {f.todo}")
            w("")
    if report.db.checked and report.pine.checked and not report.needs_attention:
        w("NOTHING TO FIX (no urgent or warning findings)")
        w("")
    notes = [f for f in report.findings if f.severity == NOTE]
    if notes:
        w(f"NOTES ({len(notes)})")
        for f in notes:
            w(f"  [{f.code}] {f.subject}: {f.text}")
            if f.todo:
                w(f"      do: {f.todo}")
        w("")
    if not summary_only and report.rows:
        w("PER DOCUMENT")
        w(f"  {'document':30} {'answers now':11} {'chunks':>6} {'vectors':>7} {'missing':>7}")
        for r in report.rows:
            w(f"  {_label(r.doc)[:30]:30} {'yes' if r.doc.answerable else 'no':11} {len(r.doc.chunk_ids):>6} {r.found:>7} {len(r.missing):>7}")
        w("")
    w("WHAT THIS REPORT CANNOT TELL YOU")
    for s in CANNOT_TELL:
        w(f"  - {s}")
    return "\n".join(out) + "\n"


def write_csv(report: VectorReport, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["row_type", "label", "document_id", "answers_now", "chunks", "vectors_found", "vectors_missing", "metadata_mismatch", "title_or_note"])
        for r in report.rows:
            d = r.doc
            wr.writerow(["document", _csv_safe(_label(d)), d.document_id, d.answerable, len(d.chunk_ids), r.found, len(r.missing), len(r.mismatched), _csv_safe(d.title)])
        for o in report.pine.orphans:
            wr.writerow(["orphan_vector", _csv_safe(o.vector_id), _csv_safe(o.document_id), "", "", "", "", "", _csv_safe(o.title)])


# ------------------------------------------------------------------------------------------------ command line
def main(argv: Optional[Sequence[str]] = None) -> int:
    from ask_bpl_orchestrator.config import get_settings

    settings = get_settings()
    ap = argparse.ArgumentParser(description="Compare the stored passages with the vectors in Pinecone (read-only)")
    ap.add_argument("--csv", metavar="FILE", help="also write the per-document table and the orphan vectors here (the only file this command writes)")
    ap.add_argument("--summary-only", action="store_true", help="skip the per-document table")
    ap.add_argument("--strict", action="store_true", help="exit 1 on an URGENT or WARN finding, or when the database or Pinecone could not be read")
    args = ap.parse_args(argv)

    db = asyncio.run(gather_db_facts(settings, alembic_head()))
    if not db.checked:
        pine = PineFacts()
    elif not (settings.pinecone_api_key or "").strip():
        pine = PineFacts(state="no_key")
    else:
        try:
            from ask_bpl_orchestrator.services.pinecone_client import get_pinecone_index

            pine = gather_pinecone_facts(ReadOnlyIndex(get_pinecone_index()), db)
        except Exception as exc:  # noqa: BLE001 - classify, never print the error's own text
            pine = PineFacts(state="unreachable", error_kind=classify_error(exc))

    report = build_report(db, pine)
    print(render(report, summary_only=args.summary_only), end="")  # noqa: T201
    if args.csv:
        write_csv(report, Path(args.csv))
        print(f"Wrote {args.csv}")  # noqa: T201
    if args.strict and (report.needs_attention or not db.checked or not pine.checked):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
