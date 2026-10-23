"""Create knowledge content and durable RAG indexing outbox tables.

Revision ID: 0004_rag_content
Revises: 0003_catalog
Create Date: 2026-10-23
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_rag_content"
down_revision: Optional[str] = "0003_catalog"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("locale", sa.String(length=10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "document_type IN ('faq', 'size_guide', 'shipping_policy', "
            "'return_policy', 'promotion', 'guide')",
            name="ck_knowledge_documents_document_type_valid",
        ),
        sa.CheckConstraint(
            "version > 0", name="ck_knowledge_documents_version_positive"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_documents"),
    )
    op.create_index(
        "ix_knowledge_documents_type_active",
        "knowledge_documents",
        ["document_type", "is_active"],
    )

    op.create_table(
        "rag_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("content_for_embedding", sa.Text(), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("index_status", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "source_type IN ('product', 'knowledge')",
            name="ck_rag_documents_source_type_valid",
        ),
        sa.CheckConstraint(
            "source_version > 0", name="ck_rag_documents_source_version_positive"
        ),
        sa.CheckConstraint(
            "index_status IN ('pending', 'indexed', 'failed')",
            name="ck_rag_documents_index_status_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rag_documents"),
        sa.UniqueConstraint(
            "source_type", "source_id", name="uq_rag_document_source"
        ),
    )
    op.create_index(
        "ix_rag_documents_status_active",
        "rag_documents",
        ["index_status", "is_active"],
    )

    op.create_table(
        "rag_index_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("payload_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "source_type IN ('product', 'knowledge')",
            name="ck_rag_index_jobs_source_type_valid",
        ),
        sa.CheckConstraint(
            "source_version > 0", name="ck_rag_index_jobs_source_version_positive"
        ),
        sa.CheckConstraint(
            "event_type IN ('upsert', 'delete')",
            name="ck_rag_index_jobs_event_type_valid",
        ),
        sa.CheckConstraint(
            "payload_version > 0",
            name="ck_rag_index_jobs_payload_version_positive",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'succeeded', 'failed')",
            name="ck_rag_index_jobs_status_valid",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_rag_index_jobs_attempt_count_non_negative",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rag_index_jobs"),
        sa.UniqueConstraint(
            "source_type",
            "source_id",
            "source_version",
            name="uq_rag_index_job_source_version",
        ),
    )
    op.create_index(
        "ix_rag_index_jobs_claim",
        "rag_index_jobs",
        ["status", "available_at", "created_at"],
    )
    op.create_index(
        "ix_rag_index_jobs_recovery",
        "rag_index_jobs",
        ["status", "locked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_rag_index_jobs_recovery", table_name="rag_index_jobs")
    op.drop_index("ix_rag_index_jobs_claim", table_name="rag_index_jobs")
    op.drop_table("rag_index_jobs")
    op.drop_index("ix_rag_documents_status_active", table_name="rag_documents")
    op.drop_table("rag_documents")
    op.drop_index(
        "ix_knowledge_documents_type_active", table_name="knowledge_documents"
    )
    op.drop_table("knowledge_documents")
