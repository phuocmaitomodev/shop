"""store normalized chat action confirmation payload

Revision ID: 0008_chat_action_payload
Revises: 0007_cart_pricing
Create Date: 2026-11-03 13:10:00
"""
from typing import Optional, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_chat_action_payload"
down_revision: Optional[str] = "0007_cart_pricing"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.add_column(
        "action_confirmations",
        sa.Column("payload_json", sa.JSON(), nullable=True),
    )
    op.execute(
        "UPDATE action_confirmations "
        "SET payload_json = '{}'::json WHERE payload_json IS NULL"
    )
    op.alter_column("action_confirmations", "payload_json", nullable=False)


def downgrade() -> None:
    op.drop_column("action_confirmations", "payload_json")
