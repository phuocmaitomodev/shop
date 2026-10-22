"""Enable the pgvector extension.

Revision ID: 0001_enable_pgvector
Revises:
Create Date: 2026-10-22
"""

from typing import Optional, Sequence, Union

from alembic import op

revision: str = "0001_enable_pgvector"
down_revision: Optional[str] = None
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
