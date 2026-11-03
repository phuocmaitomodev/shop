import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration.database_guard import mark_fresh_migrated_database


MIGRATION_DATABASE_URL = os.getenv("MIGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not MIGRATION_DATABASE_URL,
    reason="MIGRATION_DATABASE_URL is required for PostgreSQL migration tests",
)


async def _database_state(database_url: str) -> tuple[set[str], set[str], set[str]]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            tables = set(
                await connection.scalars(
                    text(
                        "SELECT tablename FROM pg_catalog.pg_tables "
                        "WHERE schemaname = 'public'"
                    )
                )
            )
            extensions = set(
                await connection.scalars(text("SELECT extname FROM pg_extension"))
            )
            revisions = set()
            if "alembic_version" in tables:
                revisions = set(
                    await connection.scalars(text("SELECT version_num FROM alembic_version"))
                )
            return tables, extensions, revisions
    finally:
        await engine.dispose()


async def _commerce_contract_state(
    database_url: str,
) -> tuple[set[str], set[str], set[str]]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            constraints = set(
                await connection.scalars(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conrelid::regclass::text IN "
                        "('carts', 'orders', 'refund_requests')"
                    )
                )
            )
            indexes = set(
                await connection.scalars(
                    text(
                        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                        "AND tablename IN ('refund_requests', 'idempotency_records')"
                    )
                )
            )
            secret_columns = set(
                await connection.scalars(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name IN "
                        "('carts', 'orders', 'payment_attempts', "
                        "'idempotency_records', 'action_confirmations') "
                        "AND (column_name LIKE '%token%' OR "
                        "column_name LIKE '%idempotency_key%')"
                    )
                )
            )
            return constraints, indexes, secret_columns
    finally:
        await engine.dispose()


async def _assert_commerce_constraints(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            async def rejected(statement, parameters) -> None:
                with pytest.raises(IntegrityError):
                    async with connection.begin_nested():
                        await connection.execute(statement, parameters)

            await rejected(
                text(
                    "INSERT INTO carts (id, status, version) "
                    "VALUES (:id, 'active', 1)"
                ),
                {"id": uuid4()},
            )

            owner_hash = "a" * 64
            common_idempotency = {
                "owner_hash": owner_hash,
                "operation": "order_create",
                "resource_key": "cart:test",
                "key_hash": "b" * 64,
                "request_hash": "c" * 64,
            }
            insert_idempotency = text(
                "INSERT INTO idempotency_records "
                "(id, owner_guest_token_hash, operation, resource_key, key_hash, "
                "request_hash, status, expires_at) VALUES "
                "(:id, :owner_hash, :operation, :resource_key, :key_hash, "
                ":request_hash, 'processing', now() + interval '1 hour')"
            )
            await connection.execute(
                insert_idempotency, {"id": uuid4(), **common_idempotency}
            )
            await rejected(
                insert_idempotency, {"id": uuid4(), **common_idempotency}
            )

            user_id = uuid4()
            await connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, email, password_hash, full_name, role, is_active) VALUES "
                    "(:id, :email, 'test-only-hash', 'Commerce Test', "
                    "'customer', true)"
                ),
                {"id": user_id, "email": f"commerce-{user_id}@example.com"},
            )
            invalid_order = {
                "id": uuid4(),
                "order_code": f"INVALID-{uuid4().hex[:16]}",
                "user_id": user_id,
            }
            await rejected(
                text(
                    "INSERT INTO orders "
                    "(id, order_code, user_id, recipient_name, phone, address_line, "
                    "province, status, payment_method, payment_status, subtotal, "
                    "discount_amount, shipping_fee, total) VALUES "
                    "(:id, :order_code, :user_id, 'Khách thử', '0900000000', "
                    "'Địa chỉ thử', 'Hà Nội', 'unknown', 'cod', 'pending', "
                    "100000, 0, 0, 100000)"
                ),
                invalid_order,
            )

            confirmation_parameters = {
                "id": uuid4(),
                "user_id": user_id,
                "payload_hash": "d" * 64,
                "token_hash": "e" * 64,
            }
            await rejected(
                text(
                    "INSERT INTO action_confirmations "
                    "(id, owner_user_id, action, resource_key, payload_hash, "
                    "token_hash, expires_at) VALUES "
                    "(:id, :user_id, 'order_create', 'cart:test', :payload_hash, "
                    ":token_hash, now() + interval '5 minutes')"
                ),
                confirmation_parameters,
            )
            await rejected(
                text(
                    "INSERT INTO action_confirmations "
                    "(id, owner_user_id, session_key, action, resource_key, "
                    "payload_hash, token_hash, expires_at) VALUES "
                    "(:id, :user_id, 'session:test', 'order_create', 'cart:test', "
                    ":payload_hash, :token_hash, now() + interval '301 seconds')"
                ),
                confirmation_parameters,
            )

            order_id = uuid4()
            await connection.execute(
                text(
                    "INSERT INTO orders "
                    "(id, order_code, user_id, recipient_name, phone, address_line, "
                    "province, status, payment_method, payment_status, subtotal, "
                    "discount_amount, shipping_fee, total) VALUES "
                    "(:id, :order_code, :user_id, 'Khách thử', '0900000000', "
                    "'Địa chỉ thử', 'Hà Nội', 'completed', 'online_demo', "
                    "'demo_approved', 100000, 0, 0, 100000)"
                ),
                {
                    "id": order_id,
                    "order_code": f"ORDER-{uuid4().hex[:16]}",
                    "user_id": user_id,
                },
            )
            insert_refund = text(
                "INSERT INTO refund_requests "
                "(id, order_id, requester_user_id, reason_code, amount, status) "
                "VALUES (:id, :order_id, :user_id, 'other', 100000, :status)"
            )
            await rejected(
                text(
                    "INSERT INTO refund_requests "
                    "(id, order_id, requester_user_id, reason_code, amount, status) "
                    "VALUES (:id, :order_id, :user_id, 'invented_reason', "
                    "100000, 'requested')"
                ),
                {"id": uuid4(), "order_id": order_id, "user_id": user_id},
            )
            await connection.execute(
                insert_refund,
                {
                    "id": uuid4(),
                    "order_id": order_id,
                    "user_id": user_id,
                    "status": "requested",
                },
            )
            await rejected(
                insert_refund,
                {
                    "id": uuid4(),
                    "order_id": order_id,
                    "user_id": user_id,
                    "status": "demo_reviewing",
                },
            )
            await connection.execute(
                insert_refund,
                {
                    "id": uuid4(),
                    "order_id": order_id,
                    "user_id": user_id,
                    "status": "demo_rejected",
                },
            )
    finally:
        await engine.dispose()


def test_upgrade_head_on_fresh_postgresql_with_pgvector() -> None:
    assert MIGRATION_DATABASE_URL is not None
    assert MIGRATION_DATABASE_URL.startswith("postgresql+asyncpg://")

    backend_dir = Path(__file__).resolve().parents[2]
    alembic_config = Config(backend_dir / "alembic.ini")
    alembic_config.set_main_option("script_location", str(backend_dir / "alembic"))
    expected_head = ScriptDirectory.from_config(alembic_config).get_current_head()
    expected_tables = {
        "alembic_version",
        "auth_sessions",
        "action_confirmations",
        "cart_items",
        "carts",
        "categories",
        "colors",
        "coupon_redemptions",
        "coupons",
        "idempotency_records",
        "inventory_movements",
        "labels",
        "order_items",
        "orders",
        "password_reset_tokens",
        "payment_attempts",
        "product_images",
        "product_labels",
        "product_variants",
        "products",
        "knowledge_documents",
        "rag_chunks",
        "rag_documents",
        "rag_index_jobs",
        "refund_requests",
        "sizes",
        "system_settings",
        "users",
    }
    commerce_tables = {
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
    }

    tables_before, extensions_before, revisions_before = asyncio.run(
        _database_state(MIGRATION_DATABASE_URL)
    )
    assert tables_before == set(), "migration database must start without public tables"
    assert "vector" not in extensions_before
    assert revisions_before == set()

    environment = os.environ.copy()
    environment["DATABASE_URL"] = MIGRATION_DATABASE_URL
    def run_alembic(*arguments: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "alembic.ini", *arguments],
            cwd=backend_dir,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    run_alembic("upgrade", "head")

    tables_after, extensions_after, revisions_after = asyncio.run(
        _database_state(MIGRATION_DATABASE_URL)
    )
    assert expected_tables <= tables_after
    assert "vector" in extensions_after
    assert revisions_after == {expected_head}

    constraints, indexes, secret_columns = asyncio.run(
        _commerce_contract_state(MIGRATION_DATABASE_URL)
    )
    assert {
        "ck_carts_owner_mode_valid",
        "ck_orders_owner_mode_valid",
        "ck_orders_status_valid",
        "ck_refund_requests_status_valid",
    } <= constraints
    assert {
        "uq_refund_requests_one_non_terminal",
        "uq_idempotency_guest_scope",
        "uq_idempotency_user_scope",
    } <= indexes
    assert secret_columns == {
        "guest_token_hash",
        "guest_lookup_token_hash",
        "idempotency_key_hash",
        "owner_guest_token_hash",
        "token_hash",
    }
    asyncio.run(_assert_commerce_constraints(MIGRATION_DATABASE_URL))

    run_alembic("check")
    run_alembic("downgrade", "0005_rag_chunks")
    downgraded_tables, _, downgraded_revisions = asyncio.run(
        _database_state(MIGRATION_DATABASE_URL)
    )
    assert commerce_tables.isdisjoint(downgraded_tables)
    assert downgraded_revisions == {"0005_rag_chunks"}

    run_alembic("upgrade", "head")
    run_alembic("check")
    reupgraded_tables, _, reupgraded_revisions = asyncio.run(
        _database_state(MIGRATION_DATABASE_URL)
    )
    assert expected_tables <= reupgraded_tables
    assert reupgraded_revisions == {expected_head}
    asyncio.run(_assert_commerce_constraints(MIGRATION_DATABASE_URL))
    mark_fresh_migrated_database(MIGRATION_DATABASE_URL)
