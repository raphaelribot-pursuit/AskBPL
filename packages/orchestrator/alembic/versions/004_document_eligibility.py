"""Document eligibility and provenance (PRD R-14, ING-2, ING-9, GATE-03).

Revision ID: 004_document_eligibility
Revises: 003_question_pii_categories

Existing indexed documents are backfilled as `authority_pending` AND test-index
members, which preserves what the pilot answers today (OD-11) without ever marking
anything `eligible`. Rows added after this migration default to `authority_pending`
with test_index_member = false, so a new document is NOT retrievable until a
disposition is applied (default-deny).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004_document_eligibility"
down_revision = "003_question_pii_categories"

_VALUES = ("eligible", "authority_pending", "blocked", "excluded", "superseded")


def upgrade() -> None:
    eligibility = postgresql.ENUM(*_VALUES, name="document_eligibility")
    eligibility.create(op.get_bind(), checkfirst=True)
    col_type = postgresql.ENUM(*_VALUES, name="document_eligibility", create_type=False)

    op.add_column("documents", sa.Column("source_id", sa.String(32), nullable=True))
    op.add_column("documents", sa.Column("policy_number", sa.String(100), nullable=True))
    op.add_column("documents", sa.Column("owner", sa.String(255), nullable=True))
    op.add_column("documents", sa.Column("issue_date", sa.Date(), nullable=True))
    op.add_column("documents", sa.Column("effective_date", sa.Date(), nullable=True))
    op.add_column("documents", sa.Column("revision_date", sa.Date(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("eligibility", col_type, nullable=False, server_default="authority_pending"),
    )
    op.add_column(
        "documents",
        sa.Column("test_index_member", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("documents", sa.Column("approval_evidence", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("reviewed_by", sa.String(255), nullable=True))
    op.add_column("documents", sa.Column("reviewed_at", sa.Date(), nullable=True))
    op.add_column("documents", sa.Column("status_note", sa.Text(), nullable=True))

    op.create_unique_constraint("uq_documents_source_id", "documents", ["source_id"])
    op.create_index("ix_documents_eligibility", "documents", ["eligibility"])

    op.execute(
        "UPDATE documents SET test_index_member = TRUE "
        "WHERE ingest_status = 'indexed' AND superseded_by_document_id IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_documents_eligibility", table_name="documents")
    op.drop_constraint("uq_documents_source_id", "documents", type_="unique")
    for name in (
        "status_note", "reviewed_at", "reviewed_by", "approval_evidence", "test_index_member",
        "eligibility", "revision_date", "effective_date", "issue_date", "owner",
        "policy_number", "source_id",
    ):
        op.drop_column("documents", name)
    postgresql.ENUM(name="document_eligibility").drop(op.get_bind(), checkfirst=True)
