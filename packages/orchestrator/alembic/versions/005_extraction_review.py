"""Extraction review status for scanned / OCR documents (patch 0009; PRD ING-3, ING-11, GATE-04).

Revision ID: 005_extraction_review
Revises: 004_document_eligibility

Existing rows become 'standard', so nothing that answers today changes. Only a document explicitly
marked 'review_required' is withheld from retrieval and citation until a person's validation record
has been verified at ingest.
"""

from alembic import op
import sqlalchemy as sa

revision = "005_extraction_review"
down_revision = "004_document_eligibility"


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("extraction_status", sa.String(16), nullable=False, server_default="standard"),
    )
    op.add_column("documents", sa.Column("extraction_validated_by", sa.String(255), nullable=True))
    op.add_column("documents", sa.Column("extraction_validated_at", sa.Date(), nullable=True))
    op.add_column("documents", sa.Column("extraction_record_sha256", sa.String(64), nullable=True))


def downgrade() -> None:
    for name in (
        "extraction_record_sha256", "extraction_validated_at", "extraction_validated_by", "extraction_status",
    ):
        op.drop_column("documents", name)
