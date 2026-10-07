"""Initial schema aligned to AskBPL_ERD (frozen snapshot).

Revision ID: 001_initial
Revises:
Create Date: 2026-05-11

This revision is a FROZEN snapshot of the schema as it existed before
002_selvon_approved and 003_question_pii_categories. It deliberately does NOT
call ``Base.metadata.create_all``: doing so builds tables from the *current*
models, which already contain the columns that 002 and 003 add, so a fresh
database failed at revision 002 ("column already exists").

Rule for contributors: never edit this file to track model changes. Add a new
revision instead, so that ``alembic upgrade head`` works on an empty database
and on every previously deployed one.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

revision: str = "001_initial"
down_revision: None = None
branch_labels = None
depends_on = None

_ENUMS = {
    "tester_group": ("SME", "non_expert"),
    "attribution_mode": ("attributed", "anonymous"),
    "source_format": ("pdf", "docx", "md"),
    "ingest_status": ("indexed", "pending", "failed"),
    "response_type": ("answer", "refusal_oo_corpus", "refusal_citation_invalid", "error_pii"),
    "feedback_rating": ("helpful", "not_helpful"),
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*_ENUMS[name], name=name)


def _tz() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "testers",
        sa.Column("tester_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("access_code_hash", sa.String(255), nullable=False),
        sa.Column("group", _enum("tester_group"), nullable=False),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("issued_at", _tz(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_testers_email", "testers", ["email"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("session_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tester_id",
            UUID(as_uuid=True),
            sa.ForeignKey("testers.tester_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("attribution_mode", _enum("attribution_mode"), nullable=False),
        sa.Column("started_at", _tz(), nullable=False),
        sa.Column("expires_at", _tz(), nullable=False),
        sa.Column("user_agent", sa.String(255), nullable=True),
    )
    op.create_index("ix_sessions_tester_id", "sessions", ["tester_id"])

    op.create_table(
        "policy_types",
        sa.Column("policy_type", sa.String(80), primary_key=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
    )

    op.create_table(
        "owning_teams",
        sa.Column("team_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("contact_hint", sa.String(255), nullable=False),
    )

    # selvon_approved is added by revision 002.
    op.create_table(
        "routing_rules",
        sa.Column("rule_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "policy_type",
            sa.String(80),
            sa.ForeignKey("policy_types.policy_type", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("owning_teams.team_id"), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("approved_at", _tz(), nullable=True),
        sa.UniqueConstraint("policy_type", "team_id", name="uq_routing_rule_policy_team"),
    )
    op.create_index("ix_routing_rules_policy_type", "routing_rules", ["policy_type"])

    op.create_table(
        "documents",
        sa.Column("document_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("policy_type", sa.String(80), sa.ForeignKey("policy_types.policy_type"), nullable=False),
        sa.Column("source_format", _enum("source_format"), nullable=False),
        sa.Column("ingested_at", _tz(), nullable=True),
        sa.Column("ingest_status", _enum("ingest_status"), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("source_path", sa.String(512), nullable=True),
        sa.Column(
            "superseded_by_document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.document_id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_documents_policy_type", "documents", ["policy_type"])

    op.create_table(
        "chunks",
        sa.Column("chunk_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section_heading", sa.String(255), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_content_hash", "chunks", ["content_hash"])

    # pii_categories is added by revision 003.
    op.create_table(
        "questions",
        sa.Column("request_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.session_id"), nullable=False),
        sa.Column(
            "tester_id",
            UUID(as_uuid=True),
            sa.ForeignKey("testers.tester_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("question_text", sa.Text(), nullable=True),
        sa.Column("question_hash", sa.String(64), nullable=False),
        sa.Column("pii_rejected", sa.Boolean(), nullable=False),
        sa.Column("submitted_at", _tz(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
    )
    op.create_index("ix_questions_session_id", "questions", ["session_id"])
    op.create_index("ix_questions_tester_id", "questions", ["tester_id"])
    op.create_index("ix_questions_question_hash", "questions", ["question_hash"])

    op.create_table(
        "responses",
        sa.Column("response_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "request_id",
            UUID(as_uuid=True),
            sa.ForeignKey("questions.request_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("response_type", _enum("response_type"), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("refusal_explanation", sa.Text(), nullable=True),
        sa.Column("inferred_policy_type", sa.String(80), nullable=True),
        sa.Column("created_at", _tz(), nullable=False),
        sa.UniqueConstraint("request_id"),
    )

    op.create_table(
        "citations",
        sa.Column("citation_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "response_id",
            UUID(as_uuid=True),
            sa.ForeignKey("responses.response_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_id", UUID(as_uuid=True), sa.ForeignKey("chunks.chunk_id"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
    )
    op.create_index("ix_citations_chunk_id", "citations", ["chunk_id"])

    op.create_table(
        "routing_decisions",
        sa.Column("decision_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "response_id",
            UUID(as_uuid=True),
            sa.ForeignKey("responses.response_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("owning_teams.team_id"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
    )

    op.create_table(
        "feedback",
        sa.Column("feedback_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "request_id",
            UUID(as_uuid=True),
            sa.ForeignKey("questions.request_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", _enum("feedback_rating"), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("anonymous", sa.Boolean(), nullable=False),
        sa.Column("submitted_at", _tz(), nullable=False),
        sa.UniqueConstraint("request_id"),
    )


def downgrade() -> None:
    for table in (
        "feedback",
        "routing_decisions",
        "citations",
        "responses",
        "questions",
        "chunks",
        "documents",
        "routing_rules",
        "owning_teams",
        "policy_types",
        "sessions",
        "testers",
    ):
        op.drop_table(table)
    bind = op.get_bind()
    for name in _ENUMS:
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
