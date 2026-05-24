"""Add selvon_approved to routing_rules (TRD-RTG-4).

Revision ID: 002_selvon_approved
Revises: 001_initial
"""

from alembic import op
import sqlalchemy as sa

revision = "002_selvon_approved"
down_revision = "001_initial"


def upgrade() -> None:
    op.add_column(
        "routing_rules",
        sa.Column("selvon_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE routing_rules SET selvon_approved = TRUE WHERE approved_at IS NOT NULL")


def downgrade() -> None:
    op.drop_column("routing_rules", "selvon_approved")
