"""Bind an approval to the file that was reviewed (patch 0023; PRD ING-2, ING-5, GATE-02, R-14).

Revision ID: 007_source_hash
Revises: 006_chunk_pages

Two nullable columns. Existing rows stay NULL, so nothing that answers today changes: documents answer as
marked test-index members, and no document is `eligible` yet. A NULL source hash means "the file was ingested
before this patch; re-ingest it to record its hash".

  source_sha256    SHA-256 of the file's bytes at its last ingest.
  approved_sha256  SHA-256 the workbook's `Approved SHA-256` column says was reviewed (set by apply-inventory).

An `eligible` document answers only while both are present and equal.
"""

from alembic import op
import sqlalchemy as sa

revision = "007_source_hash"
down_revision = "006_chunk_pages"


def upgrade() -> None:
    op.add_column("documents", sa.Column("source_sha256", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column("approved_sha256", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "approved_sha256")
    op.drop_column("documents", "source_sha256")
