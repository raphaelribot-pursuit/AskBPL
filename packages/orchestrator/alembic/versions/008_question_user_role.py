"""Log the role lens on each question (patch 0024; PRD ROLE-8).

Revision ID: 008_question_user_role
Revises: 007_source_hash

One nullable column. Existing rows stay NULL ("asked before role lenses existed"). A role is self-selected and is not
personal information (ROLE-8); it is stored so analytics can see which lens was used.
"""

from alembic import op
import sqlalchemy as sa

revision = "008_question_user_role"
down_revision = "007_source_hash"


def upgrade() -> None:
    op.add_column("questions", sa.Column("user_role", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("questions", "user_role")
