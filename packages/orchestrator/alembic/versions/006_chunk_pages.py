"""Page range on chunks (patch 0013; PRD ING-11, GRD-4).

Revision ID: 006_chunk_pages
Revises: 005_extraction_review

Two nullable columns. Existing rows stay NULL ("page unknown") until their document is re-ingested,
so nothing that answers today changes and nothing is shown that was not recorded.
"""

from alembic import op
import sqlalchemy as sa

revision = "006_chunk_pages"
down_revision = "005_extraction_review"


def upgrade() -> None:
    op.add_column("chunks", sa.Column("page_start", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("page_end", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "page_end")
    op.drop_column("chunks", "page_start")
