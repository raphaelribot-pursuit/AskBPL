"""Single definition of "may this document be retrieved or cited?" (R-14, GATE-03).

Every path that exposes document content (vector retrieval, citation emission, the
citation viewer) must use this module so the rule cannot drift between call sites.

Rule:
  * `eligible`                      -> answerable.
  * `authority_pending`             -> answerable ONLY if the document is a marked
                                       test-index member (OD-11) AND ALLOW_TEST_INDEX is on.
  * `blocked`/`excluded`/`superseded` -> never answerable, regardless of any flag.
  * Documents that are superseded by another row, or not `indexed`, are never answerable.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

from ask_bpl_orchestrator.config import Settings, get_settings
from ask_bpl_orchestrator.db.models import Document, Eligibility, IngestStatus

TEST_INDEX_LABEL = "Test index: sources not yet confirmed current by BPL"


def retrievable_clause(settings: Optional[Settings] = None) -> ColumnElement[bool]:
    """SQL predicate over `Document` for use in WHERE clauses."""
    cfg = settings or get_settings()
    answerable = Document.eligibility == Eligibility.eligible
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
    )


def is_retrievable(doc: Any, settings: Optional[Settings] = None) -> bool:
    """Python mirror of `retrievable_clause` for already-loaded rows (defence in depth)."""
    cfg = settings or get_settings()
    if doc is None:
        return False
    if doc.ingest_status != IngestStatus.indexed or doc.superseded_by_document_id is not None:
        return False
    if doc.eligibility == Eligibility.eligible:
        return True
    return bool(
        cfg.allow_test_index
        and doc.eligibility == Eligibility.authority_pending
        and doc.test_index_member
    )


def is_test_index_source(doc: Any) -> bool:
    """True when answering from this document must carry the test-index label."""
    return doc is not None and doc.eligibility != Eligibility.eligible
