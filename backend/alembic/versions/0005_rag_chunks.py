"""Create versioned RAG chunks and PostgreSQL retrieval indexes.

Revision ID: 0005_rag_chunks
Revises: 0004_rag_content
Create Date: 2026-10-26
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import UserDefinedType

revision: str = "0005_rag_chunks"
down_revision: Optional[str] = "0004_rag_content"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


class VectorType(UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_kwargs) -> str:
        return f"VECTOR({self.dimensions})"


def upgrade() -> None:
    op.create_table(
        "rag_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rag_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("embedding", VectorType(768), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint(
            "chunk_index >= 0", name="ck_rag_chunks_chunk_index_non_negative"
        ),
        sa.CheckConstraint(
            "source_version > 0", name="ck_rag_chunks_source_version_positive"
        ),
        sa.ForeignKeyConstraint(
            ["rag_document_id"],
            ["rag_documents.id"],
            name="fk_rag_chunks_rag_document_id_rag_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rag_chunks"),
        sa.UniqueConstraint(
            "rag_document_id",
            "source_version",
            "chunk_index",
            name="uq_rag_chunk_document_version_index",
        ),
    )
    op.create_index(
        "ix_rag_chunks_document_active",
        "rag_chunks",
        ["rag_document_id", "is_active"],
    )
    op.execute(
        "CREATE INDEX ix_rag_chunks_embedding_hnsw ON rag_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX ix_rag_chunks_content_fts ON rag_chunks "
        "USING gin (to_tsvector('simple', content))"
    )


def downgrade() -> None:
    op.drop_index("ix_rag_chunks_content_fts", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_embedding_hnsw", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_document_active", table_name="rag_chunks")
    op.drop_table("rag_chunks")
