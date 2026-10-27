from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TesterGroup(str, enum.Enum):
    SME = "SME"
    non_expert = "non_expert"


class AttributionMode(str, enum.Enum):
    attributed = "attributed"
    anonymous = "anonymous"


class SourceFormat(str, enum.Enum):
    pdf = "pdf"
    docx = "docx"
    md = "md"


class IngestStatus(str, enum.Enum):
    indexed = "indexed"
    pending = "pending"
    failed = "failed"


class Eligibility(str, enum.Enum):
    """Lifecycle disposition of a source document (PRD ING-9).

    Only `eligible` documents are answerable by default. `authority_pending` documents
    are answerable ONLY as members of the marked test index (OD-11) and only while
    ALLOW_TEST_INDEX is on. The other three are never retrieved or cited (GATE-03).
    """

    eligible = "eligible"
    authority_pending = "authority_pending"
    blocked = "blocked"
    excluded = "excluded"
    superseded = "superseded"


class ExtractionStatus:
    """Plain string constants (not a database enum) for Document.extraction_status."""

    standard = "standard"
    review_required = "review_required"
    validated = "validated"


class ResponseType(str, enum.Enum):
    answer = "answer"
    refusal_oo_corpus = "refusal_oo_corpus"
    refusal_citation_invalid = "refusal_citation_invalid"
    error_pii = "error_pii"


class FeedbackRating(str, enum.Enum):
    helpful = "helpful"
    not_helpful = "not_helpful"


class Tester(Base):
    __tablename__ = "testers"

    tester_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    access_code_hash: Mapped[str] = mapped_column(String(255))
    group: Mapped[TesterGroup] = mapped_column(Enum(TesterGroup, name="tester_group", native_enum=True))
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    sessions: Mapped[list["Session"]] = relationship(back_populates="tester")


class Session(Base):
    __tablename__ = "sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tester_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("testers.tester_id", ondelete="SET NULL"), nullable=True, index=True
    )
    attribution_mode: Mapped[AttributionMode] = mapped_column(
        Enum(AttributionMode, name="attribution_mode", native_enum=True)
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    tester: Mapped[Optional[Tester]] = relationship(back_populates="sessions")
    questions: Mapped[list["Question"]] = relationship(back_populates="session")


class PolicyType(Base):
    __tablename__ = "policy_types"

    policy_type: Mapped[str] = mapped_column(String(80), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    documents: Mapped[list["Document"]] = relationship(back_populates="policy_type_row")
    routing_rules: Mapped[list["RoutingRule"]] = relationship(back_populates="policy_type_row")


class OwningTeam(Base):
    __tablename__ = "owning_teams"

    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    contact_hint: Mapped[str] = mapped_column(String(255))

    routing_rules: Mapped[list["RoutingRule"]] = relationship(back_populates="team")
    routing_decisions: Mapped[list["RoutingDecision"]] = relationship(back_populates="team")


class RoutingRule(Base):
    __tablename__ = "routing_rules"
    __table_args__ = (
        UniqueConstraint("policy_type", "team_id", name="uq_routing_rule_policy_team"),
    )

    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_type: Mapped[str] = mapped_column(
        String(80), ForeignKey("policy_types.policy_type", ondelete="CASCADE"), index=True
    )
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("owning_teams.team_id"))
    priority: Mapped[int] = mapped_column(Integer, default=0)
    selvon_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    policy_type_row: Mapped[PolicyType] = relationship(back_populates="routing_rules")
    team: Mapped[OwningTeam] = relationship(back_populates="routing_rules")


class Document(Base):
    __tablename__ = "documents"

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(50))
    policy_type: Mapped[str] = mapped_column(String(80), ForeignKey("policy_types.policy_type"), index=True)
    source_format: Mapped[SourceFormat] = mapped_column(Enum(SourceFormat, name="source_format", native_enum=True))
    ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ingest_status: Mapped[IngestStatus] = mapped_column(
        Enum(IngestStatus, name="ingest_status", native_enum=True), default=IngestStatus.pending
    )
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    source_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    superseded_by_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.document_id", ondelete="SET NULL"), nullable=True
    )

    # --- Eligibility and provenance (patch 0003; PRD R-14, ING-2, ING-9, GATE-03) ---
    source_id: Mapped[Optional[str]] = mapped_column(String(32), unique=True, nullable=True)
    policy_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    revision_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    eligibility: Mapped[Eligibility] = mapped_column(
        Enum(Eligibility, name="document_eligibility", native_enum=True),
        default=Eligibility.authority_pending,
        server_default=Eligibility.authority_pending.value,
        index=True,
    )
    # OD-11: member of the marked test index (answerable while authority is pending).
    test_index_member: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    approval_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # --- Extraction review (patch 0009; PRD ING-3, ING-11, GATE-04) ---
    # 'standard' = normal extraction; 'review_required' = scanned/OCR text a person has not validated yet
    # (never answerable, whatever the eligibility says); 'validated' = indexed from a hash-bound review record.
    extraction_status: Mapped[str] = mapped_column(
        String(16), default=ExtractionStatus.standard, server_default=ExtractionStatus.standard
    )
    extraction_validated_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    extraction_validated_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    extraction_record_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # --- Approval bound to the reviewed file (patch 0023; PRD ING-2, GATE-02, R-14) ---
    # source_sha256: hash of the file's bytes at its last ingest. approved_sha256: the hash the workbook says was
    # reviewed. An `eligible` document answers only while both are set and equal (see services/eligibility.py).
    source_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approved_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    policy_type_row: Mapped[PolicyType] = relationship(back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.document_id", ondelete="CASCADE"), index=True
    )
    section_heading: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Source page range of the chunk (patch 0013). NULL = unknown, e.g. a document ingested before 0013.
    page_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    page_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    document: Mapped[Document] = relationship(back_populates="chunks")
    citations: Mapped[list["Citation"]] = relationship(back_populates="chunk")


class Question(Base):
    __tablename__ = "questions"

    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.session_id"), index=True)
    tester_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("testers.tester_id", ondelete="SET NULL"), nullable=True, index=True
    )
    question_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    question_hash: Mapped[str] = mapped_column(String(64), index=True)
    # Role lens the asker chose (patch 0024, ROLE-8). Self-selected, not personal information, not a security boundary.
    # NULL on rows logged before the patch.
    user_role: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    pii_rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    pii_categories: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    session: Mapped["Session"] = relationship(back_populates="questions")
    response: Mapped[Optional["Response"]] = relationship(back_populates="question", uselist=False)
    feedback: Mapped[Optional["Feedback"]] = relationship(back_populates="question", uselist=False)


class Response(Base):
    __tablename__ = "responses"

    response_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.request_id", ondelete="CASCADE"), unique=True
    )
    response_type: Mapped[ResponseType] = mapped_column(
        Enum(ResponseType, name="response_type", native_enum=True)
    )
    answer_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refusal_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    inferred_policy_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    question: Mapped[Question] = relationship(back_populates="response")
    citations: Mapped[list["Citation"]] = relationship(back_populates="response", cascade="all, delete-orphan")
    routing_decisions: Mapped[list["RoutingDecision"]] = relationship(
        back_populates="response", cascade="all, delete-orphan"
    )


class Citation(Base):
    __tablename__ = "citations"

    citation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    response_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("responses.response_id", ondelete="CASCADE"))
    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chunks.chunk_id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)

    response: Mapped[Response] = relationship(back_populates="citations")
    chunk: Mapped[Chunk] = relationship(back_populates="citations")


class RoutingDecision(Base):
    __tablename__ = "routing_decisions"

    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    response_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("responses.response_id", ondelete="CASCADE"))
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("owning_teams.team_id"))
    ordinal: Mapped[int] = mapped_column(Integer, default=0)

    response: Mapped[Response] = relationship(back_populates="routing_decisions")
    team: Mapped[OwningTeam] = relationship(back_populates="routing_decisions")


class Feedback(Base):
    __tablename__ = "feedback"

    feedback_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.request_id", ondelete="CASCADE"), unique=True
    )
    rating: Mapped[FeedbackRating] = mapped_column(Enum(FeedbackRating, name="feedback_rating", native_enum=True))
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    question: Mapped["Question"] = relationship(back_populates="feedback")
