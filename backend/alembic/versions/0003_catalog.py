"""Create catalog tables.

Revision ID: 0003_catalog
Revises: 0002_identity_auth
Create Date: 2026-10-22
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_catalog"
down_revision: Optional[str] = "0002_identity_auth"
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
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=140), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "sort_order >= 0", name="ck_categories_sort_order_non_negative"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_categories"),
        sa.UniqueConstraint("slug", name="uq_categories_slug"),
    )

    op.create_table(
        "colors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("hex_code", sa.String(length=7), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_colors"),
        sa.UniqueConstraint("slug", name="uq_colors_slug"),
    )

    op.create_table(
        "sizes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("sort_order >= 0", name="ck_sizes_sort_order_non_negative"),
        sa.PrimaryKeyConstraint("id", name="pk_sizes"),
        sa.UniqueConstraint("code", name="uq_sizes_code"),
    )

    op.create_table(
        "labels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "code IN ('new', 'best_seller', 'sale')", name="ck_labels_code_valid"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_labels"),
        sa.UniqueConstraint("code", name="uq_labels_code"),
    )

    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.BigInteger(), nullable=False),
        sa.Column("sale_price", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("price >= 0", name="ck_products_price_non_negative"),
        sa.CheckConstraint(
            "sale_price IS NULL OR (sale_price > 0 AND sale_price < price)",
            name="ck_products_sale_price_valid",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_products_category_id_categories",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.UniqueConstraint("sku", name="uq_products_sku"),
        sa.UniqueConstraint("slug", name="uq_products_slug"),
    )
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.create_index(
        "ix_products_category_id_is_active", "products", ["category_id", "is_active"]
    )

    op.create_table(
        "product_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("alt_text", sa.String(length=255), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "sort_order >= 0", name="ck_product_images_sort_order_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_product_images_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_images"),
    )
    op.create_index(
        "ix_product_images_product_id_sort_order",
        "product_images",
        ["product_id", "sort_order"],
    )
    op.create_index(
        "uq_product_images_one_primary",
        "product_images",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )

    op.create_table(
        "product_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("color_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("size_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_sku", sa.String(length=100), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "stock_quantity >= 0", name="ck_product_variants_stock_non_negative"
        ),
        sa.CheckConstraint("version > 0", name="ck_product_variants_version_positive"),
        sa.ForeignKeyConstraint(
            ["color_id"],
            ["colors.id"],
            name="fk_product_variants_color_id_colors",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_product_variants_product_id_products",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["size_id"],
            ["sizes.id"],
            name="fk_product_variants_size_id_sizes",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_variants"),
        sa.UniqueConstraint("variant_sku", name="uq_product_variants_variant_sku"),
        sa.UniqueConstraint(
            "product_id",
            "color_id",
            "size_id",
            name="uq_variant_product_color_size",
        ),
    )
    op.create_index(
        "ix_product_variants_product_id_is_active",
        "product_variants",
        ["product_id", "is_active"],
    )
    op.create_index(
        "ix_product_variants_color_size_stock",
        "product_variants",
        ["color_id", "size_id", "stock_quantity"],
    )

    op.create_table(
        "product_labels",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["label_id"],
            ["labels.id"],
            name="fk_product_labels_label_id_labels",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_product_labels_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "product_id", "label_id", name="pk_product_labels"
        ),
    )


def downgrade() -> None:
    op.drop_table("product_labels")
    op.drop_index(
        "ix_product_variants_color_size_stock", table_name="product_variants"
    )
    op.drop_index(
        "ix_product_variants_product_id_is_active", table_name="product_variants"
    )
    op.drop_table("product_variants")
    op.drop_index("uq_product_images_one_primary", table_name="product_images")
    op.drop_index(
        "ix_product_images_product_id_sort_order", table_name="product_images"
    )
    op.drop_table("product_images")
    op.drop_index("ix_products_category_id_is_active", table_name="products")
    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_table("products")
    op.drop_table("labels")
    op.drop_table("sizes")
    op.drop_table("colors")
    op.drop_table("categories")
