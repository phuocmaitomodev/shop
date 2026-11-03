"""add cart pricing snapshots and applied coupon

Revision ID: 0007_cart_pricing
Revises: 0006_commerce_foundation
Create Date: 2026-11-03 04:12:00
"""

from typing import Optional, Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_cart_pricing"
down_revision: Optional[str] = "0006_commerce_foundation"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.add_column("carts", sa.Column("coupon_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_carts_coupon_id_coupons"),
        "carts",
        "coupons",
        ["coupon_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("cart_items", sa.Column("unit_price", sa.BigInteger(), nullable=True))
    op.execute(
        """
        UPDATE cart_items AS ci
        SET unit_price = COALESCE(p.sale_price, p.price)
        FROM product_variants AS pv
        JOIN products AS p ON p.id = pv.product_id
        WHERE ci.variant_id = pv.id
        """
    )
    op.alter_column("cart_items", "unit_price", nullable=False)
    op.create_check_constraint(
        op.f("ck_cart_items_unit_price_non_negative"),
        "cart_items",
        "unit_price >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_cart_items_unit_price_non_negative"),
        "cart_items",
        type_="check",
    )
    op.drop_column("cart_items", "unit_price")
    op.drop_constraint(
        op.f("fk_carts_coupon_id_coupons"),
        "carts",
        type_="foreignkey",
    )
    op.drop_column("carts", "coupon_id")
