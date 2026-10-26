"""Single definition of "may this document be retrieved or cited?" (R-14, GATE-03).

Every path that exposes document content (vector retrieval, citation emission, the
citation viewer) must use this module so the rule cannot drift between call sites.

Rule:
  * `eligible`                      -> answerable ONLY while the file that was approved is the file that is stored:
                                       `approved_sha256` and `source_sha256` are both set and equal (patch 0023).
                                       A changed file that is re-ingested stops answering until it is approved again.
  * `authority_pending`             -> answerable ONLY if the document is a marked
                                       test-index member (OD-11) AND ALLOW_TEST_INDEX is on.
  * `blocked`/`excluded`/`superseded` -> never answerable, regardless of any flag.
  * Documents that are superseded by another row, or not `indexed`, are never answerable.
  * A document whose extraction is `review_required` (scanned/OCR text no person has validated)
    is never answerable, whatever its eligibility says (GATE-04, patch 0009).
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

from ask_bpl_orchestrator.config import Settings, get_settings
from ask_bpl_orchestrator.db.models import Document, Eligibility, ExtractionStatus, IngestStatus

TEST_INDEX_LABEL = "Test index: sources not yet confirmed current by BPL"


def retrievable_clause(settings: Optional[Settings] = None) -> ColumnElement[bool]:
    """SQL predicate over `Document` for use in WHERE clauses."""
    cfg = settings or get_settings()
    answerable = and_(
        Document.eligibility == Eligibility.eligible,
        Document.approved_sha256.is_not(None),
        Document.source_sha256.is_not(None),
        Document.approved_sha256 == Document.source_sha256,
    )
    if cfg.allow_test_index:
        answerable = or_(
            answerable,
            and_(
                Document.eligibility == Eligibility.authority_pending,
                Document.test_index_member.is_(True),
            ),
        )
    return and_(
        answerable,
        Document.ingest_status == IngestStatus.indexed,
        Document.superseded_by_document_id.is_(None),
        Document.extraction_status != ExtractionStatus.review_required,
    )


def is_retrievable(doc: Any, settings: Optional[Settings] = None) -> bool:
    """Python mirror of `retrievable_clause` for already-loaded rows (defence in depth)."""
    cfg = settings or get_settings()
    if doc is None:
        return False
    if doc.ingest_status != IngestStatus.indexed or doc.superseded_by_document_id is not None:
        return False
    # getattr default only for non-ORM stand-ins; a real Document row always carries the column.
    if getattr(doc, "extraction_status", ExtractionStatus.standard) == ExtractionStatus.review_required:
        return False
    if doc.eligibility == Eligibility.eligible:
        approved = getattr(doc, "approved_sha256", None)  # a stand-in without the column is never approved
        return bool(approved) and approved == getattr(doc, "source_sha256", None)
    return bool(
        cfg.allow_test_index
        and doc.eligibility == Eligibility.authority_pending
        and doc.test_index_member
    )


def is_test_index_source(doc: Any) -> bool:
    """True when answering from this document must carry the test-index label."""
    return doc is not None and doc.eligibility != Eligibility.eligible
