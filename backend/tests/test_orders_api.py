import asyncio
import socket
from datetime import timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.catalog import Category, Color, Product, ProductVariant, Size
from app.models.commerce import (
    Cart,
    IdempotencyRecord,
    InventoryMovement,
    Order,
    PaymentAttempt,
    RefundRequest,
)


@pytest.fixture
def order_catalog(auth_session_factory) -> dict[str, str]:
    async def seed() -> dict[str, str]:
        async with auth_session_factory() as session:
            category = Category(name="Áo khoác", slug="ao-khoac-order")
            color = Color(name="Xanh", slug="xanh-order", hex_code="#0000FF")
            size = Size(code="L-ORDER", name="L", sort_order=3)
            product = Product(
                category=category,
                sku="ORDER-AK-001",
                slug="ao-khoac-order",
                name="Áo khoác đặt hàng",
                price=400_000,
                sale_price=350_000,
            )
            variant = ProductVariant(
                product=product,
                color=color,
                size=size,
                variant_sku="ORDER-AK-001-XANH-L",
                stock_quantity=5,
            )
            session.add_all([category, color, size, product, variant])
            await session.commit()
            return {"variant_id": str(variant.id)}

    return asyncio.run(seed())


def _checkout_payload(cart: dict) -> dict:
    return {
        "cart_id": cart["cart_id"],
        "cart_version": cart["version"],
        "recipient_name": "Nguyễn Văn An",
        "phone": "0901234567",
        "address_line": "12 Nguyễn Huệ",
        "ward": "Bến Nghé",
        "district": "Quận 1",
        "province": "TP. Hồ Chí Minh",
        "note": "Giao giờ hành chính",
        "payment_method": "cod",
    }


def _issue_confirmation(client: TestClient, action: str, resource_key: str, payload: dict) -> str:
    response = client.post(
        "/api/v1/action-confirmations",
        json={"action": action, "resource_key": resource_key, "payload": payload},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["confirmation_token"]


def _create_guest_order(
    client: TestClient, variant_id: str, *, key: str, payment_method: str = "cod"
) -> dict:
    cart = client.post(
        "/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 1}
    ).json()["data"]
    payload = _checkout_payload(cart)
    payload["payment_method"] = payment_method
    payload["confirmation_token"] = _issue_confirmation(
        client, "order_create", cart["cart_id"], payload
    )
    response = client.post(
        "/api/v1/orders", headers={"Idempotency-Key": key}, json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_guest_checkout_snapshots_order_and_reserves_stock_once(
    auth_client: TestClient, auth_session_factory, order_catalog
) -> None:
    cart_response = auth_client.post(
        "/api/v1/cart/items",
        json={"variant_id": order_catalog["variant_id"], "quantity": 2},
    )
    cart = cart_response.json()["data"]
    payload = _checkout_payload(cart)
    payload["confirmation_token"] = _issue_confirmation(
        auth_client, "order_create", cart["cart_id"], payload
    )

    response = auth_client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": "checkout-guest-001"},
        json=payload,
    )

    assert response.status_code == 201, response.text
    order = response.json()["data"]
    assert order["order_code"].startswith("DH-")
    assert order["status"] == "pending_confirmation"
    assert order["payment"] == {
        "method": "cod",
        "status": "cod_due",
        "amount": 700_000,
        "provider": "demo",
        "is_simulation": True,
    }
    assert order["subtotal"] == 700_000
    assert order["discount_amount"] == 0
    assert order["shipping_fee"] == 0
    assert order["total"] == 700_000
    assert order["currency"] == "VND"
    assert order["guest_lookup_token"]
    assert order["items"][0]["variant_sku"] == "ORDER-AK-001-XANH-L"
    assert order["items"][0]["quantity"] == 2
    assert order["items"][0]["unit_price"] == 350_000

    async def persisted_state() -> tuple[int, int, int]:
        async with auth_session_factory() as session:
            stock = await session.scalar(
                select(ProductVariant.stock_quantity).where(
                    ProductVariant.id == UUID(order_catalog["variant_id"])
                )
            )
            movements = await session.scalar(
                select(func.count()).select_from(InventoryMovement).where(
                    InventoryMovement.order_id == UUID(order["id"]),
                    InventoryMovement.movement_type == "order_reserve",
                )
            )
            orders = await session.scalar(select(func.count()).select_from(Order))
            return int(stock or 0), int(movements or 0), int(orders or 0)

    assert asyncio.run(persisted_state()) == (3, 1, 1)


def test_order_create_retry_replays_and_changed_payload_conflicts(
    auth_client: TestClient, auth_session_factory, order_catalog
) -> None:
    cart = auth_client.post(
        "/api/v1/cart/items",
        json={"variant_id": order_catalog["variant_id"], "quantity": 1},
    ).json()["data"]
    payload = _checkout_payload(cart)
    payload["confirmation_token"] = _issue_confirmation(
        auth_client, "order_create", cart["cart_id"], payload
    )
    headers = {"Idempotency-Key": "checkout-retry-001"}

    first = auth_client.post("/api/v1/orders", headers=headers, json=payload)

    async def emulate_legacy_record_and_advance_order() -> None:
        async with auth_session_factory() as session:
            order = await session.get(Order, UUID(first.json()["data"]["id"]))
            record = await session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.operation == "order_create"
                )
            )
            payment = await session.scalar(
                select(PaymentAttempt).where(PaymentAttempt.order_id == order.id)
            )
            assert order is not None and record is not None and payment is not None
            record.response_body = {"order_id": str(order.id)}
            order.status = "completed"
            order.payment_status = "paid_demo"
            payment.status = "paid_demo"
            await session.commit()

    asyncio.run(emulate_legacy_record_and_advance_order())
    replay = auth_client.post("/api/v1/orders", headers=headers, json=payload)
    changed = {**payload, "recipient_name": "Người nhận khác"}
    conflict = auth_client.post("/api/v1/orders", headers=headers, json=changed)

    assert first.status_code == replay.status_code == 201
    assert first.json()["data"]["id"] == replay.json()["data"]["id"]
    assert first.json()["data"]["guest_lookup_token"]
    assert replay.json()["data"]["guest_lookup_token"] is None
    assert replay.json()["data"]["status"] == "pending_confirmation"
    assert replay.json()["data"]["payment"]["status"] == "cod_due"
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    async def counts() -> tuple[int, int]:
        async with auth_session_factory() as session:
            orders = await session.scalar(select(func.count()).select_from(Order))
            movements = await session.scalar(
                select(func.count()).select_from(InventoryMovement)
            )
            return int(orders or 0), int(movements or 0)

    assert asyncio.run(counts()) == (1, 1)


def test_guest_order_lookup_requires_matching_header_token(
    auth_client: TestClient, order_catalog
) -> None:
    order = _create_guest_order(
        auth_client, order_catalog["variant_id"], key="lookup-order-001"
    )

    missing = auth_client.get(
        "/api/v1/orders/lookup", params={"order_code": order["order_code"]}
    )
    wrong = auth_client.get(
        "/api/v1/orders/lookup",
        params={"order_code": order["order_code"]},
        headers={"X-Order-Lookup-Token": "olt_wrong-token-value"},
    )
    cart_token = auth_client.get("/api/v1/cart").request.headers.get("cookie", "").split(
        "shop_guest=", 1
    )[1].split(";", 1)[0]
    confused = auth_client.get(
        "/api/v1/orders/lookup",
        params={"order_code": order["order_code"]},
        headers={"X-Order-Lookup-Token": cart_token},
    )
    found = auth_client.get(
        "/api/v1/orders/lookup",
        params={"order_code": order["order_code"]},
        headers={"X-Order-Lookup-Token": order["guest_lookup_token"]},
    )

    assert missing.status_code == 422
    assert wrong.status_code == 404
    assert wrong.json()["error"]["code"] == "ORDER_NOT_FOUND"
    assert confused.status_code == 404
    assert found.status_code == 200
    assert found.json()["data"]["id"] == order["id"]
    assert found.json()["data"]["guest_lookup_token"] is None


def test_cancel_replays_without_restoring_stock_twice(
    auth_client: TestClient, auth_session_factory, order_catalog
) -> None:
    order = _create_guest_order(
        auth_client, order_catalog["variant_id"], key="cancel-order-create-001"
    )
    cancel_payload = {"reason": "Khách đổi ý"}
    cancel_payload["confirmation_token"] = _issue_confirmation(
        auth_client, "order_cancel", order["order_code"], cancel_payload
    )
    headers = {"Idempotency-Key": "cancel-order-001"}

    first = auth_client.post(
        f"/api/v1/orders/{order['order_code']}/cancel",
        headers=headers,
        json=cancel_payload,
    )

    async def emulate_legacy_record_and_advance_order() -> None:
        async with auth_session_factory() as session:
            persisted = await session.get(Order, UUID(order["id"]))
            record = await session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.operation == "order_cancel"
                )
            )
            payment = await session.scalar(
                select(PaymentAttempt).where(PaymentAttempt.order_id == persisted.id)
            )
            assert persisted is not None and record is not None and payment is not None
            record.response_body = {"order_id": str(persisted.id)}
            persisted.status = "completed"
            persisted.cancelled_at = None
            await session.commit()

    asyncio.run(emulate_legacy_record_and_advance_order())
    replay = auth_client.post(
        f"/api/v1/orders/{order['order_code']}/cancel",
        headers=headers,
        json=cancel_payload,
    )

    assert first.status_code == replay.status_code == 200
    assert first.json()["data"]["status"] == "cancelled"
    assert replay.json()["data"]["status"] == "cancelled"
    assert replay.json()["data"]["payment"]["status"] == "cancelled"

    async def state() -> tuple[int, int]:
        async with auth_session_factory() as session:
            stock = await session.scalar(
                select(ProductVariant.stock_quantity).where(
                    ProductVariant.id == UUID(order_catalog["variant_id"])
                )
            )
            restores = await session.scalar(
                select(func.count()).select_from(InventoryMovement).where(
                    InventoryMovement.order_id == UUID(order["id"]),
                    InventoryMovement.movement_type == "order_cancel_restore",
                )
            )
            return int(stock or 0), int(restores or 0)

    assert asyncio.run(state()) == (5, 1)


def test_online_payment_status_is_demo_and_amount_is_server_side(
    auth_client: TestClient, order_catalog
) -> None:
    order = _create_guest_order(
        auth_client,
        order_catalog["variant_id"],
        key="online-demo-order-001",
        payment_method="online_demo",
    )

    response = auth_client.get(
        f"/api/v1/orders/{order['order_code']}/payment",
        headers={"X-Order-Lookup-Token": order["guest_lookup_token"]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "method": "online_demo",
        "status": "demo_processing",
        "amount": order["total"],
        "provider": "demo",
        "is_simulation": True,
    }


def test_completed_order_refund_uses_server_amount_and_latest_is_owner_scoped(
    auth_client: TestClient, auth_session_factory, order_catalog
) -> None:
    order = _create_guest_order(
        auth_client, order_catalog["variant_id"], key="refund-order-create-001"
    )

    async def complete_order() -> None:
        async with auth_session_factory() as session:
            persisted_order = await session.get(Order, UUID(order["id"]))
            payment = await session.scalar(
                select(PaymentAttempt).where(
                    PaymentAttempt.order_id == UUID(order["id"])
                )
            )
            assert persisted_order is not None and payment is not None
            persisted_order.status = "completed"
            persisted_order.payment_status = "paid_demo"
            payment.status = "paid_demo"
            await session.commit()

    asyncio.run(complete_order())
    refund_payload = {
        "reason_code": "manufacturer_fault",
        "reason_detail": "Đường may bị lỗi",
    }
    refund_payload["confirmation_token"] = _issue_confirmation(
        auth_client, "refund_request", order["order_code"], refund_payload
    )

    created = auth_client.post(
        f"/api/v1/orders/{order['order_code']}/refund-requests",
        headers={"Idempotency-Key": "refund-request-001"},
        json=refund_payload,
    )

    async def emulate_legacy_record_and_advance_refund() -> None:
        async with auth_session_factory() as session:
            refund = await session.scalar(select(RefundRequest))
            record = await session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.operation == "refund_request"
                )
            )
            assert refund is not None and record is not None
            record.response_body = {"refund_id": str(refund.id)}
            refund.status = "demo_approved"
            await session.commit()

    asyncio.run(emulate_legacy_record_and_advance_refund())
    replay = auth_client.post(
        f"/api/v1/orders/{order['order_code']}/refund-requests",
        headers={"Idempotency-Key": "refund-request-001"},
        json=refund_payload,
    )
    latest = auth_client.get(
        f"/api/v1/orders/{order['order_code']}/refund-requests/latest",
        headers={"X-Order-Lookup-Token": order["guest_lookup_token"]},
    )

    assert created.status_code == 201, created.text
    assert created.json()["data"]["amount"] == order["total"]
    assert created.json()["data"]["status"] == "requested"
    assert replay.status_code == 201, replay.text
    assert replay.json()["data"]["status"] == "requested"
    assert created.json()["data"]["provider"] == "demo"
    assert created.json()["data"]["is_simulation"] is True
    assert latest.status_code == 200
    assert latest.json()["data"]["id"] == created.json()["data"]["id"]

    async def persisted_amount() -> int:
        async with auth_session_factory() as session:
            amount = await session.scalar(select(RefundRequest.amount))
            return int(amount or 0)

    assert asyncio.run(persisted_amount()) == order["total"]


def test_authenticated_order_detail_rejects_another_customer(
    auth_client: TestClient, create_auth_user, order_catalog
) -> None:
    create_auth_user("owner@example.com")
    create_auth_user("other@example.com")
    login = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "MatKhau-AnToan-123"},
    )
    assert login.status_code == 200
    cart = auth_client.post(
        "/api/v1/cart/items",
        json={"variant_id": order_catalog["variant_id"], "quantity": 1},
    ).json()["data"]
    payload = _checkout_payload(cart)
    payload["confirmation_token"] = _issue_confirmation(
        auth_client, "order_create", cart["cart_id"], payload
    )
    created = auth_client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": "customer-order-create-001"},
        json=payload,
    ).json()["data"]

    own = auth_client.get(f"/api/v1/orders/{created['order_code']}")
    auth_client.post("/api/v1/auth/logout")
    auth_client.post(
        "/api/v1/auth/login",
        json={"email": "other@example.com", "password": "MatKhau-AnToan-123"},
    )
    foreign = auth_client.get(f"/api/v1/orders/{created['order_code']}")

    assert own.status_code == 200
    assert own.json()["data"]["id"] == created["id"]
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "ORDER_NOT_FOUND"


def test_online_demo_checkout_makes_no_external_network_call(
    auth_client: TestClient, order_catalog, monkeypatch
) -> None:
    def deny_network(*args, **kwargs):
        raise AssertionError("online demo must not open a provider connection")

    monkeypatch.setattr(socket, "create_connection", deny_network)

    order = _create_guest_order(
        auth_client,
        order_catalog["variant_id"],
        key="online-network-deny-001",
        payment_method="online_demo",
    )

    assert order["payment"]["provider"] == "demo"
    assert order["payment"]["is_simulation"] is True


def test_expired_guest_capabilities_cannot_read_or_confirm_order_mutation(
    auth_client: TestClient, auth_session_factory, order_catalog
) -> None:
    order = _create_guest_order(
        auth_client, order_catalog["variant_id"], key="expired-capability-order-001"
    )

    async def expire_capabilities() -> None:
        async with auth_session_factory() as session:
            persisted_order = await session.get(Order, UUID(order["id"]))
            assert persisted_order is not None and persisted_order.cart_id is not None
            cart = await session.get(Cart, persisted_order.cart_id)
            assert cart is not None
            persisted_order.guest_lookup_expires_at = (
                persisted_order.created_at + timedelta(microseconds=1)
            )
            cart.guest_expires_at = cart.created_at + timedelta(microseconds=1)
            await session.commit()

    asyncio.run(expire_capabilities())
    lookup = auth_client.get(
        "/api/v1/orders/lookup",
        params={"order_code": order["order_code"]},
        headers={"X-Order-Lookup-Token": order["guest_lookup_token"]},
    )
    confirmation = auth_client.post(
        "/api/v1/action-confirmations",
        json={
            "action": "order_cancel",
            "resource_key": order["order_code"],
            "payload": {"reason": "Không còn nhu cầu"},
        },
    )

    assert lookup.status_code == 404
    assert confirmation.status_code == 404
