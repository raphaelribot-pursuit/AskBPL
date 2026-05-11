"""Initial schema aligned to AskBPL_ERD.

Revision ID: 001_initial
Revises:
Create Date: 2026-05-11

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "001_initial"
down_revision: None = None


def upgrade() -> None:
    from ask_bpl_orchestrator.db.models import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from ask_bpl_orchestrator.db.models import Base

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
