"""Persist PII detector labels on Question (TRD telemetry / blocker QA).

Revision ID: 003_question_pii_categories
Revises: 002_selvon_approved
"""

from alembic import op
import sqlalchemy as sa

revision = "003_question_pii_categories"
down_revision = "002_selvon_approved"


def upgrade() -> None:
    op.add_column("questions", sa.Column("pii_categories", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("questions", "pii_categories")
