"""Record each document's type: policy, procedure, guidance... (patch 0060; PRD ING-10).

Revision ID: 009_document_type
Revises: 008_question_user_role

One nullable column, filled from the inventory workbook's "Source type" by askbpl-apply-inventory. NULL means "not
recorded yet" (run askbpl-apply-inventory). The answer prompt uses it so a procedure is not presented as a policy.
"""

from alembic import op
import sqlalchemy as sa

revision = "009_document_type"
down_revision = "008_question_user_role"


def upgrade() -> None:
    op.add_column("documents", sa.Column("document_type", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "document_type")
