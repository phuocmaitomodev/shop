from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.db.base import metadata


EXPECTED_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def test_metadata_uses_stable_constraint_naming_convention() -> None:
    assert metadata.naming_convention == EXPECTED_NAMING_CONVENTION


def test_identity_metadata_defines_auth_tables() -> None:
    assert {"users", "auth_sessions", "password_reset_tokens"} <= set(metadata.tables)


def test_catalog_metadata_defines_required_tables() -> None:
    assert {
        "categories",
        "products",
        "product_images",
        "colors",
        "sizes",
        "product_variants",
        "labels",
        "product_labels",
    } <= set(metadata.tables)


def test_catalog_business_tables_have_timestamps() -> None:
    for table_name in {
        "categories",
        "products",
        "product_images",
        "colors",
        "sizes",
        "product_variants",
        "labels",
    }:
        assert {"created_at", "updated_at"} <= set(
            metadata.tables[table_name].columns.keys()
        )


def test_rag_content_metadata_defines_required_tables() -> None:
    assert {
        "knowledge_documents",
        "rag_chunks",
        "rag_documents",
        "rag_index_jobs",
    } <= set(metadata.tables)
    for table_name in {
        "knowledge_documents",
        "rag_chunks",
        "rag_documents",
        "rag_index_jobs",
    }:
        assert {"created_at", "updated_at"} <= set(
            metadata.tables[table_name].columns.keys()
        )


def test_commerce_metadata_defines_required_tables() -> None:
    assert {
        "action_confirmations",
        "cart_items",
        "carts",
        "coupon_redemptions",
        "coupons",
        "idempotency_records",
        "inventory_movements",
        "order_items",
        "orders",
        "payment_attempts",
        "refund_requests",
        "system_settings",
    } <= set(metadata.tables)

    assert metadata.tables["carts"].c.coupon_id.nullable is True
    assert metadata.tables["cart_items"].c.unit_price.nullable is False


def test_confirmation_and_refund_metadata_enforce_locked_security_contract() -> None:
    confirmation = metadata.tables["action_confirmations"]
    confirmation_checks = {
        str(constraint.sqltext)
        for constraint in confirmation.constraints
        if hasattr(constraint, "sqltext")
    }
    refund = metadata.tables["refund_requests"]
    refund_checks = {
        str(constraint.sqltext)
        for constraint in refund.constraints
        if hasattr(constraint, "sqltext")
    }

    assert confirmation.c.session_key.nullable is False
    assert any(
        "expires_at <= created_at + interval '5 minutes'" in check
        for check in confirmation_checks
    )
    assert any(
        "reason_code IN ('manufacturer_fault', 'transit_damage', "
        "'wrong_item', 'other')" in check
        for check in refund_checks
    )


def test_alembic_has_single_loadable_commerce_head_that_enables_pgvector(
    monkeypatch,
) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(backend_dir / "alembic.ini")
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    scripts = ScriptDirectory.from_config(config)

    heads = scripts.get_heads()
    assert heads == ["0008_chat_action_payload"]

    chat_revision = scripts.get_revision(heads[0])
    assert chat_revision.down_revision == "0007_cart_pricing"
    cart_revision = scripts.get_revision("0007_cart_pricing")
    assert cart_revision.down_revision == "0006_commerce_foundation"

    revision = scripts.get_revision("0001_enable_pgvector")
    executed_sql = []
    monkeypatch.setattr(revision.module.op, "execute", executed_sql.append)

    revision.module.upgrade()

    assert executed_sql == ["CREATE EXTENSION IF NOT EXISTS vector"]
