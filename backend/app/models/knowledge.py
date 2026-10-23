from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.catalog import TimestampMixin


DOCUMENT_TYPES = (
    "faq",
    "size_guide",
    "shipping_policy",
    "return_policy",
    "promotion",
    "guide",
)
SOURCE_TYPES = ("product", "knowledge")
INDEX_STATUSES = ("pending", "indexed", "failed")
JOB_STATUSES = ("pending", "processing", "succeeded", "failed")
INDEX_EVENT_TYPES = ("upsert", "delete")
CURRENT_INDEX_EVENT_PAYLOAD_VERSION = 1


class KnowledgeDocument(TimestampMixin, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('faq', 'size_guide', 'shipping_policy', "
            "'return_policy', 'promotion', 'guide')",
            name="document_type_valid",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        Index(
            "ix_knowledge_documents_type_active",
            "document_type",
            "is_active",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(String(10), default="vi")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    checksum: Mapped[str] = mapped_column(String(64))


class RagDocument(TimestampMixin, Base):
    __tablename__ = "rag_documents"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('product', 'knowledge')", name="source_type_valid"
        ),
        CheckConstraint("source_version > 0", name="source_version_positive"),
        CheckConstraint(
            "index_status IN ('pending', 'indexed', 'failed')",
            name="index_status_valid",
        ),
        UniqueConstraint("source_type", "source_id", name="uq_rag_document_source"),
        Index("ix_rag_documents_status_active", "index_status", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_type: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String(240))
    content_for_embedding: Mapped[str] = mapped_column(Text)
    source_version: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
    index_status: Mapped[str] = mapped_column(String(20), default="pending")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RagIndexJob(TimestampMixin, Base):
    __tablename__ = "rag_index_jobs"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('product', 'knowledge')", name="source_type_valid"
        ),
        CheckConstraint("source_version > 0", name="source_version_positive"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'succeeded', 'failed')",
            name="status_valid",
        ),
        CheckConstraint(
            "event_type IN ('upsert', 'delete')", name="event_type_valid"
        ),
        CheckConstraint("payload_version > 0", name="payload_version_positive"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
        UniqueConstraint(
            "source_type",
            "source_id",
            "source_version",
            name="uq_rag_index_job_source_version",
        ),
        Index(
            "ix_rag_index_jobs_claim",
            "status",
            "available_at",
            "created_at",
        ),
        Index("ix_rag_index_jobs_recovery", "status", "locked_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_type: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[UUID]
    source_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(20), default="upsert")
    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        server_default=text("'{}'"),
    )
    payload_version: Mapped[int] = mapped_column(
        Integer, default=CURRENT_INDEX_EVENT_PAYLOAD_VERSION
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
