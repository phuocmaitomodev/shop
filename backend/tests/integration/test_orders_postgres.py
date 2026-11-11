import asyncio
import os
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event, Thread
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import hash_token
from app.commerce.chat_actions import DatabaseChatActionAdapter
from app.db.session import get_db_session
from app.main import create_app
from app.models.catalog import Category, Color, Product, ProductVariant, Size
from app.models.commerce import (
    ActionConfirmation,
    Cart,
    CartItem,
    IdempotencyRecord,
    InventoryMovement,
    Order,
    PaymentAttempt,
    RefundRequest,
)
from tests.integration.database_guard import require_fresh_migrated_database

MIGRATION_DATABASE_URL = os.getenv("MIGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not MIGRATION_DATABASE_URL,
    reason="MIGRATION_DATABASE_URL is required for PostgreSQL order integration tests",
)


def test_postgres_concurrent_cancel_restores_stock_once() -> None:
    assert MIGRATION_DATABASE_URL is not None
    require_fresh_migrated_database(MIGRATION_DATABASE_URL)

    async def seed() -> str:
        engine = create_async_engine(MIGRATION_DATABASE_URL)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        suffix = uuid4().hex
        async with session_factory() as session:
            category = Category(name="Đơn hàng PG", slug=f"order-pg-{suffix}")
            color = Color(name="Đen PG", slug=f"order-black-{suffix}")
            size = Size(code=f"OR-{suffix[:8]}", name="Order PG")
            product = Product(
                category=category,
                sku=f"ORDER-PG-{suffix}",
                slug=f"order-pg-product-{suffix}",
                name="Sản phẩm đơn hàng PostgreSQL",
                price=350_000,
            )
            variant = ProductVariant(
                product=product,
                color=color,
                size=size,
                variant_sku=f"ORDER-PG-VARIANT-{suffix}",
                stock_quantity=3,
            )
            session.add_all([category, color, size, product, variant])
            await session.commit()
            variant_id = str(variant.id)
        await engine.dispose()
        return variant_id

    variant_id = asyncio.run(seed())
    application = create_app()
    api_engine = create_async_engine(MIGRATION_DATABASE_URL, poolclass=NullPool)
    api_session_factory = async_sessionmaker(api_engine, expire_on_commit=False)

    async def override_session():
        async with api_session_factory() as session:
            yield session

    application.dependency_overrides[get_db_session] = override_session

    def issue_confirmation(client: TestClient, action: str, resource_key: str, payload: dict) -> str:
        response = client.post(
            "/api/v1/action-confirmations",
            json={"action": action, "resource_key": resource_key, "payload": payload},
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]["confirmation_token"]

    with TestClient(application) as first, TestClient(application) as second:
        cart = first.post(
            "/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 1}
        ).json()["data"]
        checkout_payload = {
            "cart_id": cart["cart_id"],
            "cart_version": cart["version"],
            "recipient_name": "Khách PostgreSQL",
            "phone": "0901234567",
            "address_line": "1 Đường PostgreSQL",
            "province": "TP. Hồ Chí Minh",
            "payment_method": "cod",
        }
        checkout_payload["confirmation_token"] = issue_confirmation(
            first, "order_create", cart["cart_id"], checkout_payload
        )
        created = first.post(
            "/api/v1/orders",
            headers={"Idempotency-Key": "postgres-checkout-cancel"},
            json=checkout_payload,
        )
        assert created.status_code == 201, created.text
        order = created.json()["data"]

        second.cookies.set("shop_guest", first.cookies["shop_guest"])
        cancel_payload = {"reason": "Khách đổi ý"}
        first_token = issue_confirmation(
            first, "order_cancel", order["order_code"], cancel_payload
        )
        second_token = issue_confirmation(
            second, "order_cancel", order["order_code"], cancel_payload
        )

        def cancel(args: tuple[TestClient, str, str]) -> tuple[int, str | None]:
            client, token, key = args
            response = client.post(
                f"/api/v1/orders/{order['order_code']}/cancel",
                headers={"Idempotency-Key": key},
                json={**cancel_payload, "confirmation_token": token},
            )
            return response.status_code, response.json().get("error", {}).get("code")

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(
                executor.map(
                    cancel,
                    (
                        (first, first_token, "postgres-cancel-first"),
                        (second, second_token, "postgres-cancel-second"),
                    ),
                )
            )

    assert sorted(status_code for status_code, _ in outcomes) == [200, 409], outcomes
    assert {code for _, code in outcomes if code} == {"ORDER_STATUS_NOT_CANCELLABLE"}

    async def persisted_state() -> tuple[int, int]:
        async with api_session_factory() as session:
            stock = await session.scalar(
                select(ProductVariant.stock_quantity).where(
                    ProductVariant.id == UUID(variant_id)
                )
            )
            restores = await session.scalar(
                select(func.count()).select_from(InventoryMovement).where(
                    InventoryMovement.order_id == UUID(order["id"]),
                    InventoryMovement.movement_type == "order_cancel_restore",
                )
            )
            return int(stock or 0), int(restores or 0)

    assert asyncio.run(persisted_state()) == (3, 1)
    application.dependency_overrides.clear()
    asyncio.run(api_engine.dispose())


def test_postgres_chat_refund_confirmation_serializes_binding_and_side_effect(
    monkeypatch,
) -> None:
    assert MIGRATION_DATABASE_URL is not None
    require_fresh_migrated_database(MIGRATION_DATABASE_URL)

    async def seed() -> str:
        engine = create_async_engine(MIGRATION_DATABASE_URL)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        suffix = uuid4().hex
        async with session_factory() as session:
            category = Category(name="Hoàn tiền PG", slug=f"refund-pg-{suffix}")
            color = Color(name="Xanh PG", slug=f"refund-blue-{suffix}")
            size = Size(code=f"RF-{suffix[:8]}", name="Refund PG")
            product = Product(
                category=category,
                sku=f"REFUND-PG-{suffix}",
                slug=f"refund-pg-product-{suffix}",
                name="Sản phẩm hoàn tiền PostgreSQL",
                price=420_000,
            )
            variant = ProductVariant(
                product=product,
                color=color,
                size=size,
                variant_sku=f"REFUND-PG-VARIANT-{suffix}",
                stock_quantity=3,
            )
            session.add_all([category, color, size, product, variant])
            await session.commit()
            variant_id = str(variant.id)
        await engine.dispose()
        return variant_id

    variant_id = asyncio.run(seed())
    application = create_app()
    api_engine = create_async_engine(MIGRATION_DATABASE_URL, poolclass=NullPool)
    api_session_factory = async_sessionmaker(api_engine, expire_on_commit=False)

    async def override_session():
        async with api_session_factory() as session:
            yield session

    application.dependency_overrides[get_db_session] = override_session

    def issue_confirmation(client: TestClient, action: str, resource_key: str, payload: dict) -> str:
        response = client.post(
            "/api/v1/action-confirmations",
            json={"action": action, "resource_key": resource_key, "payload": payload},
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]["confirmation_token"]

    with TestClient(application) as first, TestClient(application) as second:
        cart = first.post(
            "/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 1}
        ).json()["data"]
        checkout_payload = {
            "cart_id": cart["cart_id"],
            "cart_version": cart["version"],
            "recipient_name": "Khách hoàn tiền PostgreSQL",
            "phone": "0901234567",
            "address_line": "2 Đường PostgreSQL",
            "province": "TP. Hồ Chí Minh",
            "payment_method": "online_demo",
        }
        checkout_payload["confirmation_token"] = issue_confirmation(
            first, "order_create", cart["cart_id"], checkout_payload
        )
        created = first.post(
            "/api/v1/orders",
            headers={"Idempotency-Key": "postgres-checkout-refund"},
            json=checkout_payload,
        )
        assert created.status_code == 201, created.text
        order = created.json()["data"]

        async def complete_order() -> None:
            async with api_session_factory() as session:
                persisted_order = await session.get(Order, UUID(order["id"]))
                payment = await session.scalar(
                    select(PaymentAttempt).where(
                        PaymentAttempt.order_id == UUID(order["id"])
                    )
                )
                assert persisted_order is not None and payment is not None
                persisted_order.status = "completed"
                persisted_order.payment_status = "demo_approved"
                payment.status = "demo_approved"
                await session.commit()

        asyncio.run(complete_order())
        second.cookies.set("shop_guest", first.cookies["shop_guest"])
        refund_payload = {
            "reason_code": "manufacturer_fault",
            "reason_detail": "Sản phẩm bị lỗi",
        }
        proposal = first.post(
            "/api/v1/chat",
            json={
                "message": "Tạo yêu cầu hoàn tiền",
                "action_context": {
                    "action": "refund_request",
                    "order_id": order["id"],
                    "order_code": order["order_code"],
                    **refund_payload,
                },
            },
        )
        assert proposal.status_code == 200, proposal.text
        token = proposal.json()["data"]["proposed_action"]["confirmation_token"]
        attempt_barrier = Barrier(3)
        original_bind = DatabaseChatActionAdapter._bind_confirmation_attempt

        async def bind_after_barrier(adapter, *args, **kwargs):
            await asyncio.to_thread(attempt_barrier.wait)
            return await original_bind(adapter, *args, **kwargs)

        monkeypatch.setattr(
            DatabaseChatActionAdapter,
            "_bind_confirmation_attempt",
            bind_after_barrier,
        )
        lock_acquired = Event()
        release_lock = Event()

        async def hold_confirmation_lock() -> None:
            async with api_session_factory() as session:
                async with session.begin():
                    locked = await session.scalar(
                        select(ActionConfirmation)
                        .where(ActionConfirmation.token_hash == hash_token(token))
                        .with_for_update()
                    )
                    assert locked is not None
                    lock_acquired.set()
                    await asyncio.to_thread(release_lock.wait)

        lock_thread = Thread(target=lambda: asyncio.run(hold_confirmation_lock()))
        lock_thread.start()
        assert lock_acquired.wait(timeout=5)

        def refund(args: tuple[TestClient, str, str]) -> tuple[str, str, int, str | None]:
            client, message_id, key = args
            response = client.post(
                "/api/v1/chat",
                headers={"Idempotency-Key": key},
                json={
                    "message": "Xác nhận",
                    "confirmation_token": token,
                    "client_message_id": message_id,
                },
            )
            return (
                message_id,
                key,
                response.status_code,
                response.json().get("error", {}).get("code"),
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(refund, attempt)
                for attempt in (
                    (
                        first,
                        "00000000-0000-0000-0000-000000000095",
                        "postgres-chat-refund-first",
                    ),
                    (
                        second,
                        "00000000-0000-0000-0000-000000000096",
                        "postgres-chat-refund-second",
                    ),
                )
            ]
            attempt_barrier.wait(timeout=5)
            assert all(not future.done() for future in futures)
            release_lock.set()
            outcomes = [future.result(timeout=10) for future in futures]
        lock_thread.join(timeout=5)
        assert not lock_thread.is_alive()

    assert sorted(status_code for _, _, status_code, _ in outcomes) == [200, 409], outcomes
    assert {code for _, _, _, code in outcomes if code} == {"IDEMPOTENCY_KEY_REUSED"}
    winning_attempt = next(
        (message_id, key)
        for message_id, key, status_code, _ in outcomes
        if status_code == 200
    )

    async def persisted_state() -> tuple[int, int, int, int, str | None, str | None]:
        async with api_session_factory() as session:
            count = await session.scalar(
                select(func.count()).select_from(RefundRequest).where(
                    RefundRequest.order_id == UUID(order["id"])
                )
            )
            amount = await session.scalar(
                select(RefundRequest.amount).where(
                    RefundRequest.order_id == UUID(order["id"])
                )
            )
            confirmation = await session.scalar(
                select(ActionConfirmation).where(
                    ActionConfirmation.token_hash == hash_token(token)
                )
            )
            assert confirmation is not None
            records = await session.scalar(
                select(func.count()).select_from(IdempotencyRecord).where(
                    IdempotencyRecord.operation == "refund_request",
                    IdempotencyRecord.resource_key == order["order_code"],
                )
            )
            return (
                int(count or 0),
                int(amount or 0),
                int(confirmation.consumed_at is not None),
                int(records or 0),
                confirmation.payload_json.get("confirmed_client_message_id"),
                confirmation.payload_json.get("confirmed_idempotency_key_hash"),
            )

    assert asyncio.run(persisted_state()) == (
        1,
        order["total"],
        1,
        1,
        winning_attempt[0],
        hash_token(winning_attempt[1]),
    )
    application.dependency_overrides.clear()
    asyncio.run(api_engine.dispose())


def test_postgres_order_mutations_fail_closed_at_adversarial_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert MIGRATION_DATABASE_URL is not None
    require_fresh_migrated_database(MIGRATION_DATABASE_URL)

    async def seed() -> str:
        engine = create_async_engine(MIGRATION_DATABASE_URL)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        suffix = uuid4().hex
        async with session_factory() as session:
            category = Category(name="Biên PG", slug=f"boundary-pg-{suffix}")
            color = Color(name="Trắng PG", slug=f"boundary-white-{suffix}")
            size = Size(code=f"BD-{suffix[:8]}", name="Boundary PG")
            product = Product(
                category=category,
                sku=f"BOUNDARY-PG-{suffix}",
                slug=f"boundary-pg-product-{suffix}",
                name="Sản phẩm kiểm tra biên PostgreSQL",
                price=510_000,
            )
            variant = ProductVariant(
                product=product,
                color=color,
                size=size,
                variant_sku=f"BOUNDARY-PG-VARIANT-{suffix}",
                stock_quantity=10,
            )
            session.add_all([category, color, size, product, variant])
            await session.commit()
            variant_id = str(variant.id)
        await engine.dispose()
        return variant_id

    variant_id = asyncio.run(seed())
    application = create_app()
    api_engine = create_async_engine(MIGRATION_DATABASE_URL, poolclass=NullPool)
    api_session_factory = async_sessionmaker(api_engine, expire_on_commit=False)

    async def override_session():
        async with api_session_factory() as session:
            yield session

    application.dependency_overrides[get_db_session] = override_session

    def issue_confirmation(
        client: TestClient, action: str, resource_key: str, payload: dict
    ) -> str:
        response = client.post(
            "/api/v1/action-confirmations",
            json={"action": action, "resource_key": resource_key, "payload": payload},
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]["confirmation_token"]

    def create_order(client: TestClient, key: str) -> dict:
        cart_response = client.post(
            "/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 1}
        )
        assert cart_response.status_code == 201, cart_response.text
        cart = cart_response.json()["data"]
        payload = {
            "cart_id": cart["cart_id"],
            "cart_version": cart["version"],
            "recipient_name": "Khách kiểm tra biên",
            "phone": "0901234567",
            "address_line": "3 Đường PostgreSQL",
            "province": "TP. Hồ Chí Minh",
            "payment_method": "online_demo",
        }
        payload["confirmation_token"] = issue_confirmation(
            client, "order_create", cart["cart_id"], payload
        )
        response = client.post(
            "/api/v1/orders", headers={"Idempotency-Key": key}, json=payload
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]

    async def set_order_state(
        order_id: str, *, order_status: str, payment_status: str
    ) -> None:
        async with api_session_factory() as session:
            order = await session.get(Order, UUID(order_id))
            payment = await session.scalar(
                select(PaymentAttempt).where(PaymentAttempt.order_id == UUID(order_id))
            )
            assert order is not None and payment is not None
            order.status = order_status
            order.payment_status = payment_status
            payment.status = payment_status
            await session.commit()

    refund_payload = {
        "reason_code": "manufacturer_fault",
        "reason_detail": "Sản phẩm bị lỗi",
    }

    with TestClient(application) as owner, TestClient(application) as intruder:
        order = create_order(owner, "postgres-boundary-order-first")
        intruder_order = create_order(intruder, "postgres-boundary-order-intruder")

        wrong_lookup = owner.get(
            "/api/v1/orders/lookup",
            params={"order_code": order["order_code"]},
            headers={"X-Order-Lookup-Token": "wrong-lookup-token-value"},
        )
        wrong_owner = intruder.post(
            "/api/v1/action-confirmations",
            json={
                "action": "order_cancel",
                "resource_key": order["order_code"],
                "payload": {"reason": "Không thuộc chủ sở hữu"},
            },
        )
        assert wrong_lookup.status_code == 404
        assert wrong_owner.status_code == 404

        cancel_payload = {"reason": "Đơn đã chuyển xử lý"}
        cancel_token = issue_confirmation(
            owner, "order_cancel", order["order_code"], cancel_payload
        )
        asyncio.run(
            set_order_state(
                order["id"], order_status="preparing", payment_status="demo_processing"
            )
        )
        invalid_cancel = owner.post(
            f"/api/v1/orders/{order['order_code']}/cancel",
            headers={"Idempotency-Key": "postgres-invalid-cancel-state"},
            json={**cancel_payload, "confirmation_token": cancel_token},
        )
        ineligible_refund = owner.post(
            "/api/v1/action-confirmations",
            json={
                "action": "refund_request",
                "resource_key": order["order_code"],
                "payload": refund_payload,
            },
        )
        assert invalid_cancel.status_code == 409
        assert invalid_cancel.json()["error"]["code"] == "ORDER_STATUS_NOT_CANCELLABLE"
        assert ineligible_refund.status_code == 409
        assert ineligible_refund.json()["error"]["code"] == "REFUND_NOT_ELIGIBLE"

        asyncio.run(
            set_order_state(
                order["id"], order_status="completed", payment_status="demo_declined"
            )
        )
        invalid_payment = owner.post(
            "/api/v1/action-confirmations",
            json={
                "action": "refund_request",
                "resource_key": order["order_code"],
                "payload": refund_payload,
            },
        )
        assert invalid_payment.status_code == 409
        assert invalid_payment.json()["error"]["code"] == "REFUND_NOT_ELIGIBLE"

        asyncio.run(
            set_order_state(
                order["id"], order_status="completed", payment_status="demo_approved"
            )
        )
        refund_token = issue_confirmation(
            owner, "refund_request", order["order_code"], refund_payload
        )
        mismatched_payload = owner.post(
            f"/api/v1/orders/{order['order_code']}/refund-requests",
            headers={"Idempotency-Key": "postgres-refund-confirmation"},
            json={
                **refund_payload,
                "reason_detail": "Nội dung đã thay đổi",
                "confirmation_token": refund_token,
            },
        )
        assert mismatched_payload.status_code == 409
        assert mismatched_payload.json()["error"]["code"] == "CONFIRMATION_INVALID"

        created = owner.post(
            f"/api/v1/orders/{order['order_code']}/refund-requests",
            headers={"Idempotency-Key": "postgres-refund-confirmation"},
            json={**refund_payload, "confirmation_token": refund_token},
        )
        replay = owner.post(
            f"/api/v1/orders/{order['order_code']}/refund-requests",
            headers={"Idempotency-Key": "postgres-refund-confirmation"},
            json={**refund_payload, "confirmation_token": refund_token},
        )
        conflict = owner.post(
            f"/api/v1/orders/{order['order_code']}/refund-requests",
            headers={"Idempotency-Key": "postgres-refund-confirmation"},
            json={
                **refund_payload,
                "reason_detail": "Payload khác cho cùng key",
                "confirmation_token": refund_token,
            },
        )
        assert created.status_code == replay.status_code == 201
        assert created.json()["data"]["id"] == replay.json()["data"]["id"]
        assert created.json()["data"]["amount"] == order["total"]
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

        active_token = issue_confirmation(
            owner, "refund_request", order["order_code"], refund_payload
        )
        active_conflict = owner.post(
            f"/api/v1/orders/{order['order_code']}/refund-requests",
            headers={"Idempotency-Key": "postgres-refund-active-conflict"},
            json={**refund_payload, "confirmation_token": active_token},
        )
        assert active_conflict.status_code == 409
        assert active_conflict.json()["error"]["code"] == "REFUND_REQUEST_EXISTS"

        async def terminalize_refund() -> None:
            async with api_session_factory() as session:
                refund = await session.get(
                    RefundRequest, UUID(created.json()["data"]["id"])
                )
                assert refund is not None
                refund.status = "demo_rejected"
                await session.commit()

        asyncio.run(terminalize_refund())
        replayed_confirmation = owner.post(
            f"/api/v1/orders/{order['order_code']}/refund-requests",
            headers={"Idempotency-Key": "postgres-refund-replayed-confirmation"},
            json={**refund_payload, "confirmation_token": refund_token},
        )
        assert replayed_confirmation.status_code == 409
        assert replayed_confirmation.json()["error"]["code"] == "CONFIRMATION_INVALID"

        expired_token = issue_confirmation(
            owner, "refund_request", order["order_code"], refund_payload
        )

        async def expire_confirmation() -> None:
            async with api_session_factory() as session:
                confirmation = await session.scalar(
                    select(ActionConfirmation).where(
                        ActionConfirmation.token_hash == hash_token(expired_token)
                    )
                )
                assert confirmation is not None
                confirmation.expires_at = confirmation.created_at + timedelta(
                    microseconds=1
                )
                await session.commit()

        asyncio.run(expire_confirmation())
        expired = owner.post(
            f"/api/v1/orders/{order['order_code']}/refund-requests",
            headers={"Idempotency-Key": "postgres-refund-expired-confirmation"},
            json={**refund_payload, "confirmation_token": expired_token},
        )
        assert expired.status_code == 409
        assert expired.json()["error"]["code"] == "CONFIRMATION_INVALID"

        resource_token = issue_confirmation(
            owner, "refund_request", order["order_code"], refund_payload
        )
        second_order = create_order(owner, "postgres-boundary-order-second")
        asyncio.run(
            set_order_state(
                second_order["id"],
                order_status="completed",
                payment_status="demo_approved",
            )
        )
        wrong_resource = owner.post(
            f"/api/v1/orders/{second_order['order_code']}/refund-requests",
            headers={"Idempotency-Key": "postgres-refund-wrong-resource"},
            json={**refund_payload, "confirmation_token": resource_token},
        )
        assert wrong_resource.status_code == 409
        assert wrong_resource.json()["error"]["code"] == "CONFIRMATION_INVALID"

        asyncio.run(
            set_order_state(
                intruder_order["id"],
                order_status="completed",
                payment_status="demo_approved",
            )
        )
        intruder_token = issue_confirmation(
            intruder,
            "refund_request",
            intruder_order["order_code"],
            refund_payload,
        )

        async def retarget_intruder_confirmation() -> None:
            async with api_session_factory() as session:
                confirmation = await session.scalar(
                    select(ActionConfirmation).where(
                        ActionConfirmation.token_hash == hash_token(intruder_token)
                    )
                )
                assert confirmation is not None
                confirmation.resource_key = order["order_code"]
                await session.commit()

        asyncio.run(retarget_intruder_confirmation())
        wrong_confirmation_owner = owner.post(
            f"/api/v1/orders/{order['order_code']}/refund-requests",
            headers={
                "Idempotency-Key": "postgres-refund-wrong-owner",
                "X-Order-Lookup-Token": order["guest_lookup_token"],
            },
            json={**refund_payload, "confirmation_token": intruder_token},
        )
        assert wrong_confirmation_owner.status_code == 409
        assert wrong_confirmation_owner.json()["error"]["code"] == "CONFIRMATION_INVALID"

        async def provider_constraint_rejects_external_value() -> None:
            async with api_session_factory() as session:
                payment = await session.scalar(
                    select(PaymentAttempt).where(
                        PaymentAttempt.order_id == UUID(order["id"])
                    )
                )
                assert payment is not None
                payment.provider = "external_gateway"
                with pytest.raises(IntegrityError):
                    await session.flush()
                await session.rollback()

        asyncio.run(provider_constraint_rejects_external_value())

        def deny_external_network(*args, **kwargs):
            raise AssertionError("demo payment/refund must not open provider connections")

        monkeypatch.setattr(socket, "create_connection", deny_external_network)
        payment = owner.get(
            f"/api/v1/orders/{order['order_code']}/payment",
            headers={"X-Order-Lookup-Token": order["guest_lookup_token"]},
        )
        assert payment.status_code == 200, payment.text
        assert payment.json()["data"]["provider"] == "demo"
        assert payment.json()["data"]["amount"] == order["total"]

    application.dependency_overrides.clear()
    asyncio.run(api_engine.dispose())


def test_postgres_chat_confirmation_concurrent_consume_is_idempotent() -> None:
    assert MIGRATION_DATABASE_URL is not None
    require_fresh_migrated_database(MIGRATION_DATABASE_URL)

    async def seed() -> str:
        engine = create_async_engine(MIGRATION_DATABASE_URL)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        suffix = uuid4().hex
        async with session_factory() as session:
            category = Category(name="Chat PG", slug=f"chat-pg-{suffix}")
            color = Color(name="Đen chat PG", slug=f"chat-black-{suffix}")
            size = Size(code=f"CH-{suffix[:8]}", name="Chat PG")
            product = Product(
                category=category,
                sku=f"CHAT-PG-{suffix}",
                slug=f"chat-pg-product-{suffix}",
                name="Sản phẩm chat PostgreSQL",
                price=250_000,
            )
            variant = ProductVariant(
                product=product,
                color=color,
                size=size,
                variant_sku=f"CHAT-PG-VARIANT-{suffix}",
                stock_quantity=5,
            )
            session.add_all([category, color, size, product, variant])
            await session.commit()
            variant_id = str(variant.id)
        await engine.dispose()
        return variant_id

    variant_id = asyncio.run(seed())
    application = create_app()
    api_engine = create_async_engine(MIGRATION_DATABASE_URL, poolclass=NullPool)
    api_session_factory = async_sessionmaker(api_engine, expire_on_commit=False)

    async def override_session():
        async with api_session_factory() as session:
            yield session

    application.dependency_overrides[get_db_session] = override_session
    with TestClient(application) as first, TestClient(application) as second:
        cart = first.post(
            "/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 1}
        ).json()["data"]
        proposal = first.post(
            "/api/v1/chat",
            json={
                "message": "Thêm sản phẩm đã chọn vào giỏ hàng",
                "action_context": {
                    "action": "cart_add",
                    "cart_id": cart["cart_id"],
                    "variant_id": variant_id,
                    "quantity": 1,
                },
            },
        )
        assert proposal.status_code == 200, proposal.text
        token = proposal.json()["data"]["proposed_action"]["confirmation_token"]
        assert first.get("/api/v1/cart").json()["data"]["items"][0]["quantity"] == 1
        second.cookies.set("shop_guest", first.cookies["shop_guest"])
        body = {
            "message": "Xác nhận",
            "confirmation_token": token,
            "client_message_id": "00000000-0000-0000-0000-000000000091",
        }
        headers = {"Idempotency-Key": "postgres-chat-cart-add"}

        def confirm(client: TestClient) -> tuple[int, str]:
            response = client.post("/api/v1/chat", json=body, headers=headers)
            return response.status_code, response.json()["data"]["answer"]

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(confirm, (first, second)))

    assert [status_code for status_code, _ in outcomes] == [200, 200]
    assert outcomes[0][1] == outcomes[1][1]

    async def persisted_state() -> tuple[int, int, int]:
        async with api_session_factory() as session:
            cart_id = UUID(cart["cart_id"])
            quantity = await session.scalar(
                select(CartItem.quantity).where(CartItem.cart_id == cart_id)
            )
            consumed = await session.scalar(
                select(func.count()).select_from(ActionConfirmation).where(
                    ActionConfirmation.token_hash == hash_token(token),
                    ActionConfirmation.consumed_at.is_not(None),
                )
            )
            records = await session.scalar(
                select(func.count()).select_from(IdempotencyRecord).where(
                    IdempotencyRecord.operation == "cart_add",
                    IdempotencyRecord.resource_key == str(cart_id),
                )
            )
            return int(quantity or 0), int(consumed or 0), int(records or 0)

    assert asyncio.run(persisted_state()) == (2, 1, 1)
    application.dependency_overrides.clear()
    asyncio.run(api_engine.dispose())


def test_postgres_chat_guest_lookup_ownership_and_concurrent_cancel(monkeypatch) -> None:
    assert MIGRATION_DATABASE_URL is not None
    require_fresh_migrated_database(MIGRATION_DATABASE_URL)

    async def seed() -> str:
        engine = create_async_engine(MIGRATION_DATABASE_URL)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        suffix = uuid4().hex
        async with session_factory() as session:
            category = Category(name="Chat lookup PG", slug=f"chat-lookup-pg-{suffix}")
            color = Color(
                name="Đen lookup PG", slug=f"chat-lookup-black-{suffix}"
            )
            size = Size(code=f"CL-{suffix[:8]}", name="Chat lookup PG")
            product = Product(
                category=category,
                sku=f"CHAT-LOOKUP-PG-{suffix}",
                slug=f"chat-lookup-pg-product-{suffix}",
                name="Sản phẩm chat lookup PostgreSQL",
                price=275_000,
            )
            variant = ProductVariant(
                product=product,
                color=color,
                size=size,
                variant_sku=f"CHAT-LOOKUP-PG-VARIANT-{suffix}",
                stock_quantity=4,
            )
            session.add_all([category, color, size, product, variant])
            await session.commit()
            variant_id = str(variant.id)
        await engine.dispose()
        return variant_id

    variant_id = asyncio.run(seed())
    application = create_app()
    api_engine = create_async_engine(MIGRATION_DATABASE_URL, poolclass=NullPool)
    api_session_factory = async_sessionmaker(api_engine, expire_on_commit=False)

    async def override_session():
        async with api_session_factory() as session:
            yield session

    application.dependency_overrides[get_db_session] = override_session
    with (
        TestClient(application) as first,
        TestClient(application) as second,
        TestClient(application) as third,
    ):
        cart_response = first.post(
            "/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 1}
        )
        assert cart_response.status_code == 201, cart_response.text
        cart = cart_response.json()["data"]
        checkout = {
            "cart_id": cart["cart_id"],
            "cart_version": cart["version"],
            "recipient_name": "Khách chat lookup PostgreSQL",
            "phone": "0901234567",
            "address_line": "4 Đường PostgreSQL",
            "province": "TP. Hồ Chí Minh",
            "payment_method": "cod",
        }
        create_confirmation = first.post(
            "/api/v1/action-confirmations",
            json={
                "action": "order_create",
                "resource_key": cart["cart_id"],
                "payload": checkout,
            },
        )
        assert create_confirmation.status_code == 201, create_confirmation.text
        created = first.post(
            "/api/v1/orders",
            headers={"Idempotency-Key": "postgres-chat-lookup-create"},
            json={
                **checkout,
                "confirmation_token": create_confirmation.json()["data"][
                    "confirmation_token"
                ],
            },
        )
        assert created.status_code == 201, created.text
        order = created.json()["data"]
        lookup_headers = {"X-Order-Lookup-Token": order["guest_lookup_token"]}
        first.cookies.clear()
        action = {
            "message": "Hủy đơn",
            "action_context": {
                "action": "order_cancel",
                "order_id": order["id"],
                "order_code": order["order_code"],
                "reason": "Khách đổi ý",
            },
        }

        missing = second.post("/api/v1/chat", json=action)
        wrong = second.post(
            "/api/v1/chat",
            headers={"X-Order-Lookup-Token": "wrong-postgres-lookup-token"},
            json=action,
        )
        assert missing.status_code == wrong.status_code == 404
        proposal = first.post("/api/v1/chat", headers=lookup_headers, json=action)
        assert proposal.status_code == 200, proposal.text
        token = proposal.json()["data"]["proposed_action"]["confirmation_token"]
        first_message_id = "00000000-0000-0000-0000-000000000083"
        second_message_id = "00000000-0000-0000-0000-000000000084"
        attempt_barrier = Barrier(4)
        original_bind = DatabaseChatActionAdapter._bind_confirmation_attempt

        async def bind_after_barrier(adapter, *args, **kwargs):
            await asyncio.to_thread(attempt_barrier.wait)
            return await original_bind(adapter, *args, **kwargs)

        monkeypatch.setattr(
            DatabaseChatActionAdapter,
            "_bind_confirmation_attempt",
            bind_after_barrier,
        )

        lock_acquired = Event()
        release_lock = Event()

        async def hold_confirmation_lock() -> None:
            async with api_session_factory() as session:
                async with session.begin():
                    locked = await session.scalar(
                        select(ActionConfirmation)
                        .where(ActionConfirmation.token_hash == hash_token(token))
                        .with_for_update()
                    )
                    assert locked is not None
                    lock_acquired.set()
                    await asyncio.to_thread(release_lock.wait)

        lock_thread = Thread(target=lambda: asyncio.run(hold_confirmation_lock()))
        lock_thread.start()
        assert lock_acquired.wait(timeout=5)

        def confirm(attempt: tuple[TestClient, str, str]) -> tuple[str, str, int, str]:
            client, client_message_id, idempotency_key = attempt
            response = client.post(
                "/api/v1/chat",
                headers={**lookup_headers, "Idempotency-Key": idempotency_key},
                json={
                    "message": "Xác nhận",
                    "confirmation_token": token,
                    "client_message_id": client_message_id,
                },
            )
            payload = response.json()
            detail = (
                payload["data"]["answer"]
                if response.status_code == 200
                else payload["error"]["code"]
            )
            return client_message_id, idempotency_key, response.status_code, detail

        attempts = (
            (first, first_message_id, "postgres-chat-lookup-cancel"),
            (second, first_message_id, "postgres-chat-lookup-cancel"),
            (third, second_message_id, "postgres-chat-lookup-cancel-changed"),
        )
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(confirm, attempt) for attempt in attempts]
            attempt_barrier.wait(timeout=5)
            assert all(not future.done() for future in futures)
            release_lock.set()
            outcomes = [future.result(timeout=10) for future in futures]
        lock_thread.join(timeout=5)
        assert not lock_thread.is_alive()

    winning_attempts = {
        (client_message_id, idempotency_key)
        for client_message_id, idempotency_key, status_code, _ in outcomes
        if status_code == 200
    }
    assert len(winning_attempts) == 1
    winning_attempt = next(iter(winning_attempts))
    for client_message_id, idempotency_key, status_code, detail in outcomes:
        if (client_message_id, idempotency_key) == winning_attempt:
            assert status_code == 200
        else:
            assert status_code == 409
            assert detail == "IDEMPOTENCY_KEY_REUSED"

    async def persisted_state() -> tuple[str, int, int, int, str | None, str | None]:
        async with api_session_factory() as session:
            persisted_order = await session.get(Order, UUID(order["id"]))
            assert persisted_order is not None
            restores = await session.scalar(
                select(func.count()).select_from(InventoryMovement).where(
                    InventoryMovement.order_id == persisted_order.id,
                    InventoryMovement.movement_type == "order_cancel_restore",
                )
            )
            confirmation = await session.scalar(
                select(ActionConfirmation).where(
                    ActionConfirmation.token_hash == hash_token(token)
                )
            )
            assert confirmation is not None
            records = await session.scalar(
                select(func.count()).select_from(IdempotencyRecord).where(
                    IdempotencyRecord.operation == "order_cancel",
                    IdempotencyRecord.resource_key == order["order_code"],
                )
            )
            return (
                persisted_order.status,
                int(restores or 0),
                int(confirmation.consumed_at is not None),
                int(records or 0),
                confirmation.payload_json.get("confirmed_client_message_id"),
                confirmation.payload_json.get("confirmed_idempotency_key_hash"),
            )

    assert asyncio.run(persisted_state()) == (
        "cancelled",
        1,
        1,
        1,
        winning_attempt[0],
        hash_token(winning_attempt[1]),
    )
    application.dependency_overrides.clear()
    asyncio.run(api_engine.dispose())
