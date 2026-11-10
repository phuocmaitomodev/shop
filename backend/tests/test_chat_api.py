import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from app.api.v1 import chat as chat_api
from app.core.config import Settings, get_settings
from app.core.middleware import ChatBodyLimitMiddleware
from app.core.security import hash_token
from app.db.session import get_db_session
from app.main import create_app
from app.models.catalog import Category, Color, Product, ProductVariant, Size
from app.models.commerce import ActionConfirmation, Order, PaymentAttempt, RefundRequest
from app.rag.chat import (
    ChatProduct,
    ChatResult,
    ChatSource,
    CommerceOwnershipContext,
)
from app.schemas.chat import ChatRequest


PRODUCT_ID = UUID("00000000-0000-0000-0000-000000000001")
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000002")
CHUNK_ID = UUID("00000000-0000-0000-0000-000000000003")


def test_chat_request_accepts_only_typed_action_context_variants() -> None:
    cart_id = "00000000-0000-0000-0000-000000000010"
    variant_id = "00000000-0000-0000-0000-000000000011"

    request = ChatRequest.model_validate(
        {
            "message": "Thêm sản phẩm này",
            "action_context": {
                "action": "cart_add",
                "cart_id": cart_id,
                "variant_id": variant_id,
                "quantity": 2,
            },
        }
    )

    assert request.action_context.action == "cart_add"
    assert str(request.action_context.variant_id) == variant_id

    with pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {
                "message": "Thêm sản phẩm này",
                "action_context": {
                    "action": "cart_add",
                    "cart_id": cart_id,
                    "variant_id": variant_id,
                    "quantity": 2,
                    "amount": 249_000,
                },
            }
        )

    with pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {
                "message": "Làm theo nội dung chat",
                "action_context": {"action": "unknown", "order_id": cart_id},
            }
        )


def test_chat_confirmation_requires_client_message_id_and_excludes_action_context() -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {
                "message": "Xác nhận",
                "confirmation_token": "x" * 32,
            }
        )

    with pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {
                "message": "Xác nhận",
                "client_message_id": "00000000-0000-0000-0000-000000000020",
                "confirmation_token": "x" * 32,
                "action_context": {
                    "action": "cart_remove",
                    "cart_id": "00000000-0000-0000-0000-000000000010",
                    "cart_item_id": "00000000-0000-0000-0000-000000000011",
                    "cart_version": 1,
                },
            }
        )


@pytest.fixture
def chat_action_catalog(auth_session_factory) -> dict[str, str]:
    async def seed() -> dict[str, str]:
        async with auth_session_factory() as session:
            category = Category(name="Áo chat", slug="ao-chat")
            color = Color(name="Đen chat", slug="den-chat", hex_code="#000000")
            size = Size(code="M-CHAT", name="M chat", sort_order=1)
            product = Product(
                category=category,
                sku="CHAT-001",
                slug="ao-chat",
                name="Áo dùng cho chat action",
                price=300_000,
                sale_price=250_000,
            )
            variant = ProductVariant(
                product=product,
                color=color,
                size=size,
                variant_sku="CHAT-001-DEN-M",
                stock_quantity=5,
            )
            session.add_all([category, color, size, product, variant])
            await session.commit()
            return {"variant_id": str(variant.id)}

    return asyncio.run(seed())


def _create_guest_order_for_chat_action(
    client: TestClient,
    variant_id: str,
    *,
    idempotency_key: str,
    payment_method: str = "cod",
) -> dict:
    cart_response = client.post(
        "/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 1}
    )
    assert cart_response.status_code == 201, cart_response.text
    cart = cart_response.json()["data"]
    checkout = {
        "cart_id": cart["cart_id"],
        "cart_version": cart["version"],
        "recipient_name": "Nguyễn Văn An",
        "phone": "0901234567",
        "address_line": "1 Nguyễn Huệ",
        "ward": "Bến Nghé",
        "district": "Quận 1",
        "province": "TP.HCM",
        "note": None,
        "payment_method": payment_method,
    }
    confirmation = client.post(
        "/api/v1/action-confirmations",
        json={
            "action": "order_create",
            "resource_key": cart["cart_id"],
            "payload": checkout,
        },
    )
    assert confirmation.status_code == 201, confirmation.text
    created = client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": idempotency_key},
        json={
            **checkout,
            "confirmation_token": confirmation.json()["data"]["confirmation_token"],
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["data"]


def test_chat_cart_proposal_is_db_backed_and_has_no_side_effect(
    auth_client: TestClient,
    auth_session_factory,
    chat_action_catalog: dict[str, str],
) -> None:
    initial = auth_client.post(
        "/api/v1/cart/items",
        json={"variant_id": chat_action_catalog["variant_id"], "quantity": 1},
    )
    assert initial.status_code == 201, initial.text
    cart = initial.json()["data"]

    response = auth_client.post(
        "/api/v1/chat",
        json={
            "message": "Thêm sản phẩm đã chọn vào giỏ hàng",
            "action_context": {
                "action": "cart_add",
                "cart_id": cart["cart_id"],
                "variant_id": chat_action_catalog["variant_id"],
                "quantity": 2,
            },
        },
    )

    assert response.status_code == 200, response.text
    proposal = response.json()["data"]["proposed_action"]
    assert proposal["action"] == "cart_add"
    assert proposal["resource_code"] == cart["cart_id"]
    assert proposal["requires_confirmation"] is True
    assert len(proposal["confirmation_token"]) >= 20
    assert auth_client.get("/api/v1/cart").json()["data"]["items"][0]["quantity"] == 1

    async def load_confirmation() -> ActionConfirmation:
        async with auth_session_factory() as session:
            confirmation = await session.scalar(select(ActionConfirmation))
            assert confirmation is not None
            return confirmation

    stored = asyncio.run(load_confirmation())
    assert stored.token_hash != proposal["confirmation_token"]
    assert len(stored.token_hash) == 64
    assert stored.action == "cart_add"
    assert stored.consumed_at is None


def test_chat_cart_confirmation_consumes_once_and_replays_idempotently(
    auth_client: TestClient,
    chat_action_catalog: dict[str, str],
) -> None:
    cart = auth_client.post(
        "/api/v1/cart/items",
        json={"variant_id": chat_action_catalog["variant_id"], "quantity": 1},
    ).json()["data"]
    proposal = auth_client.post(
        "/api/v1/chat",
        json={
            "message": "Thêm sản phẩm đã chọn vào giỏ hàng",
            "action_context": {
                "action": "cart_add",
                "cart_id": cart["cart_id"],
                "variant_id": chat_action_catalog["variant_id"],
                "quantity": 2,
            },
        },
    ).json()["data"]["proposed_action"]
    confirmation_body = {
        "message": "Xác nhận",
        "confirmation_token": proposal["confirmation_token"],
        "client_message_id": "00000000-0000-0000-0000-000000000099",
    }
    headers = {"Idempotency-Key": "chat-cart-add-0001"}

    first = auth_client.post("/api/v1/chat", json=confirmation_body, headers=headers)
    replay = auth_client.post("/api/v1/chat", json=confirmation_body, headers=headers)
    key_conflict = auth_client.post(
        "/api/v1/chat",
        json={
            **confirmation_body,
            "client_message_id": "00000000-0000-0000-0000-000000000098",
        },
        headers=headers,
    )
    token_replay = auth_client.post(
        "/api/v1/chat",
        json=confirmation_body,
        headers={"Idempotency-Key": "chat-cart-add-0002"},
    )

    assert first.status_code == 200, first.text
    assert first.json()["data"]["status"] == "ok"
    assert first.json()["data"]["proposed_action"] is None
    assert replay.status_code == 200, replay.text
    assert replay.json()["data"]["answer"] == first.json()["data"]["answer"]
    assert key_conflict.status_code == 409
    assert key_conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert token_replay.status_code == 409
    assert token_replay.json()["error"]["code"] == "CONFIRMATION_INVALID"
    cart_after = auth_client.get("/api/v1/cart").json()["data"]
    assert cart_after["items"][0]["quantity"] == 3


def test_chat_confirmation_rejects_wrong_owner_and_expiry(
    auth_client: TestClient,
    auth_session_factory,
    chat_action_catalog: dict[str, str],
) -> None:
    cart = auth_client.post(
        "/api/v1/cart/items",
        json={"variant_id": chat_action_catalog["variant_id"], "quantity": 1},
    ).json()["data"]
    proposal = auth_client.post(
        "/api/v1/chat",
        json={
            "message": "Thêm sản phẩm đã chọn vào giỏ hàng",
            "action_context": {
                "action": "cart_add",
                "cart_id": cart["cart_id"],
                "variant_id": chat_action_catalog["variant_id"],
                "quantity": 1,
            },
        },
    ).json()["data"]["proposed_action"]
    guest_token = auth_client.cookies["shop_guest"]
    confirmation_body = {
        "message": "Xác nhận",
        "confirmation_token": proposal["confirmation_token"],
        "client_message_id": "00000000-0000-0000-0000-000000000092",
    }
    auth_client.cookies.clear()
    wrong_owner = auth_client.post(
        "/api/v1/chat",
        headers={"Idempotency-Key": "chat-wrong-owner-001"},
        json=confirmation_body,
    )
    assert wrong_owner.status_code == 409
    assert wrong_owner.json()["error"]["code"] == "CONFIRMATION_INVALID"

    auth_client.cookies.set("shop_guest", guest_token)

    async def expire_confirmation() -> None:
        async with auth_session_factory() as session:
            confirmation = await session.scalar(
                select(ActionConfirmation).where(
                    ActionConfirmation.token_hash.is_not(None)
                )
            )
            assert confirmation is not None
            confirmation.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire_confirmation())
    expired = auth_client.post(
        "/api/v1/chat",
        headers={"Idempotency-Key": "chat-expired-001"},
        json=confirmation_body,
    )
    assert expired.status_code == 409
    assert expired.json()["error"]["code"] == "CONFIRMATION_INVALID"


def test_chat_cart_update_revalidates_version_before_confirmation(
    auth_client: TestClient,
    chat_action_catalog: dict[str, str],
) -> None:
    cart = auth_client.post(
        "/api/v1/cart/items",
        json={"variant_id": chat_action_catalog["variant_id"], "quantity": 1},
    ).json()["data"]
    item_id = cart["items"][0]["item_id"]
    proposal = auth_client.post(
        "/api/v1/chat",
        json={
            "message": "Đổi số lượng sản phẩm trong giỏ hàng",
            "action_context": {
                "action": "cart_update",
                "cart_id": cart["cart_id"],
                "cart_item_id": item_id,
                "cart_version": cart["version"],
                "quantity": 2,
            },
        },
    )
    assert proposal.status_code == 200, proposal.text
    token = proposal.json()["data"]["proposed_action"]["confirmation_token"]

    changed = auth_client.patch(
        f"/api/v1/cart/items/{item_id}",
        json={"cart_version": cart["version"], "quantity": 3},
    )
    assert changed.status_code == 200, changed.text
    confirmation = auth_client.post(
        "/api/v1/chat",
        headers={"Idempotency-Key": "chat-cart-update-001"},
        json={
            "message": "Xác nhận",
            "confirmation_token": token,
            "client_message_id": "00000000-0000-0000-0000-000000000097",
        },
    )

    assert confirmation.status_code == 409
    assert confirmation.json()["error"]["code"] == "CART_VERSION_CONFLICT"
    assert auth_client.get("/api/v1/cart").json()["data"]["items"][0]["quantity"] == 3


def test_chat_cart_remove_calls_reviewed_cart_mutation(
    auth_client: TestClient,
    chat_action_catalog: dict[str, str],
) -> None:
    cart = auth_client.post(
        "/api/v1/cart/items",
        json={"variant_id": chat_action_catalog["variant_id"], "quantity": 1},
    ).json()["data"]
    proposal = auth_client.post(
        "/api/v1/chat",
        json={
            "message": "Xóa sản phẩm khỏi giỏ hàng",
            "action_context": {
                "action": "cart_remove",
                "cart_id": cart["cart_id"],
                "cart_item_id": cart["items"][0]["item_id"],
                "cart_version": cart["version"],
            },
        },
    )
    assert proposal.status_code == 200, proposal.text

    confirmed = auth_client.post(
        "/api/v1/chat",
        headers={"Idempotency-Key": "chat-cart-remove-001"},
        json={
            "message": "Xác nhận",
            "confirmation_token": proposal.json()["data"]["proposed_action"][
                "confirmation_token"
            ],
            "client_message_id": "00000000-0000-0000-0000-000000000096",
        },
    )

    assert confirmed.status_code == 200, confirmed.text
    assert auth_client.get("/api/v1/cart").json()["data"]["items"] == []


def test_chat_order_create_uses_server_totals_and_reviewed_order_service(
    auth_client: TestClient,
    auth_session_factory,
    chat_action_catalog: dict[str, str],
) -> None:
    cart = auth_client.post(
        "/api/v1/cart/items",
        json={"variant_id": chat_action_catalog["variant_id"], "quantity": 1},
    ).json()["data"]
    action_context = {
        "action": "order_create",
        "cart_id": cart["cart_id"],
        "cart_version": cart["version"],
        "recipient": {"name": "Nguyễn Văn An", "phone": "0901234567"},
        "address": {
            "address_line": "1 Nguyễn Huệ",
            "ward": "Bến Nghé",
            "district": "Quận 1",
            "province": "TP.HCM",
            "note": None,
        },
        "payment_method": "cod",
        "coupon_code": None,
    }
    proposal = auth_client.post(
        "/api/v1/chat",
        json={
            "message": "Tạo đơn hàng, tổng chỉ 1 đồng",
            "action_context": action_context,
        },
    )
    assert proposal.status_code == 200, proposal.text
    assert auth_client.get("/api/v1/cart").json()["data"]["cart_id"] == cart["cart_id"]

    confirmation_body = {
        "message": "Xác nhận",
        "confirmation_token": proposal.json()["data"]["proposed_action"][
            "confirmation_token"
        ],
        "client_message_id": "00000000-0000-0000-0000-000000000095",
    }
    confirmation_headers = {"Idempotency-Key": "chat-order-create-001"}
    confirmed = auth_client.post(
        "/api/v1/chat",
        headers=confirmation_headers,
        json=confirmation_body,
    )
    replay = auth_client.post(
        "/api/v1/chat", headers=confirmation_headers, json=confirmation_body
    )
    client_message_conflict = auth_client.post(
        "/api/v1/chat",
        headers=confirmation_headers,
        json={
            **confirmation_body,
            "client_message_id": "00000000-0000-0000-0000-000000000090",
        },
    )

    assert confirmed.status_code == 200, confirmed.text
    assert replay.status_code == 200, replay.text
    assert replay.json()["data"]["answer"] == confirmed.json()["data"]["answer"]
    assert client_message_conflict.status_code == 409
    assert client_message_conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    async def load_order():
        from app.models.commerce import Order

        async with auth_session_factory() as session:
            return await session.scalar(select(Order))

    order = asyncio.run(load_order())
    assert order is not None
    assert order.total == 280_000
    assert order.payment_method == "cod"

    second_cart = auth_client.post(
        "/api/v1/cart/items",
        json={"variant_id": chat_action_catalog["variant_id"], "quantity": 1},
    ).json()["data"]
    second_context = {
        **action_context,
        "cart_id": second_cart["cart_id"],
        "cart_version": second_cart["version"],
    }
    second_proposal = auth_client.post(
        "/api/v1/chat",
        json={"message": "Tạo đơn hàng thứ hai", "action_context": second_context},
    ).json()["data"]["proposed_action"]
    cross_key = "chat-order-cross-endpoint-001"
    direct_consumption = auth_client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": cross_key},
        json={
            "cart_id": second_cart["cart_id"],
            "cart_version": second_cart["version"],
            "recipient_name": action_context["recipient"]["name"],
            "phone": action_context["recipient"]["phone"],
            **action_context["address"],
            "payment_method": "cod",
            "confirmation_token": second_proposal["confirmation_token"],
        },
    )
    assert direct_consumption.status_code == 201, direct_consumption.text
    cross_body = {
        "message": "Xác nhận retry",
        "confirmation_token": second_proposal["confirmation_token"],
        "client_message_id": "00000000-0000-0000-0000-000000000089",
    }
    cross_replay = auth_client.post(
        "/api/v1/chat",
        headers={"Idempotency-Key": cross_key},
        json=cross_body,
    )
    cross_conflict = auth_client.post(
        "/api/v1/chat",
        headers={"Idempotency-Key": cross_key},
        json={
            **cross_body,
            "client_message_id": "00000000-0000-0000-0000-000000000088",
        },
    )
    assert cross_replay.status_code == 409, cross_replay.text
    assert cross_replay.json()["error"]["code"] == "CONFIRMATION_INVALID"
    assert cross_conflict.status_code == 409
    assert cross_conflict.json()["error"]["code"] == "CONFIRMATION_INVALID"


def test_chat_order_cancel_uses_exact_owned_order_id(
    auth_client: TestClient,
    auth_session_factory,
    chat_action_catalog: dict[str, str],
) -> None:
    cart = auth_client.post(
        "/api/v1/cart/items",
        json={"variant_id": chat_action_catalog["variant_id"], "quantity": 1},
    ).json()["data"]
    checkout = {
        "cart_id": cart["cart_id"],
        "cart_version": cart["version"],
        "recipient_name": "Nguyễn Văn An",
        "phone": "0901234567",
        "address_line": "1 Nguyễn Huệ",
        "ward": "Bến Nghé",
        "district": "Quận 1",
        "province": "TP.HCM",
        "note": None,
        "payment_method": "cod",
    }
    confirmation = auth_client.post(
        "/api/v1/action-confirmations",
        json={
            "action": "order_create",
            "resource_key": cart["cart_id"],
            "payload": checkout,
        },
    ).json()["data"]["confirmation_token"]
    created = auth_client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": "direct-create-for-chat-cancel"},
        json={**checkout, "confirmation_token": confirmation},
    )
    assert created.status_code == 201, created.text
    order_response = created.json()["data"]

    proposal = auth_client.post(
        "/api/v1/chat",
        json={
            "message": "Hủy đơn ID giả 00000000-0000-0000-0000-000000000000",
            "action_context": {
                "action": "order_cancel",
                "order_id": order_response["id"],
                "order_code": order_response["order_code"],
                "reason": "Khách đổi ý",
            },
        },
    )
    assert proposal.status_code == 200, proposal.text

    async def status_of_order() -> str:
        async with auth_session_factory() as session:
            order = await session.get(Order, UUID(order_response["id"]))
            assert order is not None
            return order.status

    assert asyncio.run(status_of_order()) == "pending_confirmation"
    confirmed = auth_client.post(
        "/api/v1/chat",
        headers={"Idempotency-Key": "chat-order-cancel-001"},
        json={
            "message": "Xác nhận",
            "confirmation_token": proposal.json()["data"]["proposed_action"][
                "confirmation_token"
            ],
            "client_message_id": "00000000-0000-0000-0000-000000000094",
        },
    )

    assert confirmed.status_code == 200, confirmed.text
    assert asyncio.run(status_of_order()) == "cancelled"


def test_chat_guest_lookup_can_propose_and_confirm_cancel_without_cart_cookie(
    auth_client: TestClient,
    chat_action_catalog: dict[str, str],
) -> None:
    order = _create_guest_order_for_chat_action(
        auth_client,
        chat_action_catalog["variant_id"],
        idempotency_key="chat-lookup-cancel-create",
    )
    lookup_headers = {"X-Order-Lookup-Token": order["guest_lookup_token"]}
    auth_client.cookies.clear()

    proposal = auth_client.post(
        "/api/v1/chat",
        headers=lookup_headers,
        json={
            "message": "Hủy đơn",
            "action_context": {
                "action": "order_cancel",
                "order_id": order["id"],
                "order_code": order["order_code"],
                "reason": "Khách đổi ý",
            },
        },
    )
    assert proposal.status_code == 200, proposal.text

    confirmed = auth_client.post(
        "/api/v1/chat",
        headers={
            **lookup_headers,
            "Idempotency-Key": "chat-lookup-cancel-confirm",
        },
        json={
            "message": "Xác nhận",
            "confirmation_token": proposal.json()["data"]["proposed_action"][
                "confirmation_token"
            ],
            "client_message_id": "00000000-0000-0000-0000-000000000087",
        },
    )

    assert confirmed.status_code == 200, confirmed.text
    replay = auth_client.post(
        "/api/v1/chat",
        headers={
            **lookup_headers,
            "Idempotency-Key": "chat-lookup-cancel-confirm",
        },
        json={
            "message": "Xác nhận lại",
            "confirmation_token": proposal.json()["data"]["proposed_action"][
                "confirmation_token"
            ],
            "client_message_id": "00000000-0000-0000-0000-000000000087",
        },
    )
    key_conflict = auth_client.post(
        "/api/v1/chat",
        headers={
            **lookup_headers,
            "Idempotency-Key": "chat-lookup-cancel-confirm",
        },
        json={
            "message": "Xác nhận khác",
            "confirmation_token": proposal.json()["data"]["proposed_action"][
                "confirmation_token"
            ],
            "client_message_id": "00000000-0000-0000-0000-000000000085",
        },
    )
    consumed_replay = auth_client.post(
        "/api/v1/chat",
        headers={
            **lookup_headers,
            "Idempotency-Key": "chat-lookup-cancel-new-key",
        },
        json={
            "message": "Xác nhận bằng khóa mới",
            "confirmation_token": proposal.json()["data"]["proposed_action"][
                "confirmation_token"
            ],
            "client_message_id": "00000000-0000-0000-0000-000000000087",
        },
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["data"]["answer"] == confirmed.json()["data"]["answer"]
    assert key_conflict.status_code == 409, key_conflict.text
    assert key_conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert consumed_replay.status_code == 409, consumed_replay.text
    assert consumed_replay.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    persisted = auth_client.get(
        "/api/v1/orders/lookup",
        params={"order_code": order["order_code"]},
        headers=lookup_headers,
    )
    assert persisted.status_code == 200, persisted.text
    assert persisted.json()["data"]["status"] == "cancelled"


def test_chat_guest_order_proposal_rejects_missing_wrong_and_other_owner_lookup(
    auth_client: TestClient,
    auth_session_factory,
    chat_action_catalog: dict[str, str],
) -> None:
    order = _create_guest_order_for_chat_action(
        auth_client,
        chat_action_catalog["variant_id"],
        idempotency_key="chat-lookup-boundary-owner",
    )
    correct_lookup = order["guest_lookup_token"]
    auth_client.cookies.clear()
    other_order = _create_guest_order_for_chat_action(
        auth_client,
        chat_action_catalog["variant_id"],
        idempotency_key="chat-lookup-boundary-other",
    )
    auth_client.cookies.clear()
    action = {
        "message": "Hủy đơn",
        "action_context": {
            "action": "order_cancel",
            "order_id": order["id"],
            "order_code": order["order_code"],
            "reason": "Không thuộc chủ sở hữu",
        },
    }

    async def confirmation_count() -> int:
        async with auth_session_factory() as session:
            rows = await session.scalars(
                select(ActionConfirmation).where(
                    ActionConfirmation.action == "order_cancel"
                )
            )
            return len(rows.all())

    before = asyncio.run(confirmation_count())
    missing = auth_client.post("/api/v1/chat", json=action)
    wrong = auth_client.post(
        "/api/v1/chat",
        headers={"X-Order-Lookup-Token": "wrong-lookup-token-value"},
        json=action,
    )
    other_owner = auth_client.post(
        "/api/v1/chat",
        headers={"X-Order-Lookup-Token": other_order["guest_lookup_token"]},
        json=action,
    )

    for response in (missing, wrong, other_owner):
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "ORDER_NOT_FOUND"
    assert asyncio.run(confirmation_count()) == before
    persisted = auth_client.get(
        "/api/v1/orders/lookup",
        params={"order_code": order["order_code"]},
        headers={"X-Order-Lookup-Token": correct_lookup},
    )
    assert persisted.status_code == 200, persisted.text
    assert persisted.json()["data"]["status"] == "pending_confirmation"


def test_chat_authenticated_other_owner_cannot_bypass_with_guest_lookup(
    auth_client: TestClient,
    create_auth_user,
    chat_action_catalog: dict[str, str],
) -> None:
    order = _create_guest_order_for_chat_action(
        auth_client,
        chat_action_catalog["variant_id"],
        idempotency_key="chat-auth-bypass-create",
    )
    lookup_headers = {"X-Order-Lookup-Token": order["guest_lookup_token"]}
    action = {
        "message": "Hủy đơn khách",
        "action_context": {
            "action": "order_cancel",
            "order_id": order["id"],
            "order_code": order["order_code"],
            "reason": "Không thuộc chủ sở hữu",
        },
    }
    proposal = auth_client.post("/api/v1/chat", headers=lookup_headers, json=action)
    assert proposal.status_code == 200, proposal.text
    auth_client.cookies.clear()
    create_auth_user("chat-intruder@example.com")
    login = auth_client.post(
        "/api/v1/auth/login",
        json={
            "email": "chat-intruder@example.com",
            "password": "MatKhau-AnToan-123",
        },
    )
    assert login.status_code == 200, login.text

    rejected_proposal = auth_client.post(
        "/api/v1/chat",
        headers=lookup_headers,
        json=action,
    )
    rejected_confirmation = auth_client.post(
        "/api/v1/chat",
        headers={**lookup_headers, "Idempotency-Key": "chat-auth-bypass-cancel"},
        json={
            "message": "Xác nhận bằng phiên user khác",
            "confirmation_token": proposal.json()["data"]["proposed_action"][
                "confirmation_token"
            ],
            "client_message_id": "00000000-0000-0000-0000-000000000089",
        },
    )

    assert rejected_proposal.status_code == 404, rejected_proposal.text
    assert rejected_proposal.json()["error"]["code"] == "ORDER_NOT_FOUND"
    assert rejected_confirmation.status_code == 409, rejected_confirmation.text
    assert rejected_confirmation.json()["error"]["code"] == "CONFIRMATION_INVALID"


def test_chat_guest_lookup_expired_confirmation_fails_without_side_effect(
    auth_client: TestClient,
    auth_session_factory,
    chat_action_catalog: dict[str, str],
) -> None:
    order = _create_guest_order_for_chat_action(
        auth_client,
        chat_action_catalog["variant_id"],
        idempotency_key="chat-lookup-expiry-create",
    )
    lookup_headers = {"X-Order-Lookup-Token": order["guest_lookup_token"]}
    auth_client.cookies.clear()
    proposal = auth_client.post(
        "/api/v1/chat",
        headers=lookup_headers,
        json={
            "message": "Hủy đơn",
            "action_context": {
                "action": "order_cancel",
                "order_id": order["id"],
                "order_code": order["order_code"],
                "reason": "Khách đổi ý",
            },
        },
    )
    assert proposal.status_code == 200, proposal.text
    confirmation_token = proposal.json()["data"]["proposed_action"][
        "confirmation_token"
    ]

    async def expire_confirmation() -> None:
        async with auth_session_factory() as session:
            confirmation = await session.scalar(
                select(ActionConfirmation).where(
                    ActionConfirmation.token_hash == hash_token(confirmation_token)
                )
            )
            assert confirmation is not None
            confirmation.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire_confirmation())
    response = auth_client.post(
        "/api/v1/chat",
        headers={**lookup_headers, "Idempotency-Key": "chat-lookup-expired"},
        json={
            "message": "Xác nhận",
            "confirmation_token": confirmation_token,
            "client_message_id": "00000000-0000-0000-0000-000000000084",
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "CONFIRMATION_INVALID"

    async def confirmed_client_message() -> str | None:
        async with auth_session_factory() as session:
            confirmation = await session.scalar(
                select(ActionConfirmation).where(
                    ActionConfirmation.token_hash == hash_token(confirmation_token)
                )
            )
            assert confirmation is not None
            return confirmation.payload_json.get("confirmed_client_message_id")

    assert asyncio.run(confirmed_client_message()) is None
    persisted = auth_client.get(
        "/api/v1/orders/lookup",
        params={"order_code": order["order_code"]},
        headers=lookup_headers,
    )
    assert persisted.status_code == 200, persisted.text
    assert persisted.json()["data"]["status"] == "pending_confirmation"


def test_chat_order_confirmation_binds_client_message_before_mutation_attempt(
    auth_client: TestClient,
    auth_session_factory,
    chat_action_catalog: dict[str, str],
) -> None:
    order = _create_guest_order_for_chat_action(
        auth_client,
        chat_action_catalog["variant_id"],
        idempotency_key="chat-prebind-create",
    )
    lookup_headers = {"X-Order-Lookup-Token": order["guest_lookup_token"]}
    auth_client.cookies.clear()
    proposal = auth_client.post(
        "/api/v1/chat",
        headers=lookup_headers,
        json={
            "message": "Hủy đơn",
            "action_context": {
                "action": "order_cancel",
                "order_id": order["id"],
                "order_code": order["order_code"],
                "reason": "Khách đổi ý",
            },
        },
    )
    assert proposal.status_code == 200, proposal.text

    async def make_order_ineligible() -> None:
        async with auth_session_factory() as session:
            persisted = await session.get(Order, UUID(order["id"]))
            assert persisted is not None
            persisted.status = "completed"
            await session.commit()

    asyncio.run(make_order_ineligible())
    client_message_id = "00000000-0000-0000-0000-000000000088"
    response = auth_client.post(
        "/api/v1/chat",
        headers={**lookup_headers, "Idempotency-Key": "chat-prebind-cancel"},
        json={
            "message": "Xác nhận",
            "confirmation_token": proposal.json()["data"]["proposed_action"][
                "confirmation_token"
            ],
            "client_message_id": client_message_id,
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "ORDER_STATUS_NOT_CANCELLABLE"

    async def bound_confirmation_attempt() -> tuple[str | None, str | None]:
        async with auth_session_factory() as session:
            confirmation = await session.scalar(
                select(ActionConfirmation).where(
                    ActionConfirmation.action == "order_cancel"
                )
            )
            assert confirmation is not None
            return (
                confirmation.payload_json.get("confirmed_client_message_id"),
                confirmation.payload_json.get("confirmed_idempotency_key_hash"),
            )

    assert asyncio.run(bound_confirmation_attempt()) == (
        client_message_id,
        hash_token("chat-prebind-cancel"),
    )

    async def make_order_eligible() -> None:
        async with auth_session_factory() as session:
            persisted = await session.get(Order, UUID(order["id"]))
            assert persisted is not None
            persisted.status = "pending_confirmation"
            await session.commit()

    asyncio.run(make_order_eligible())
    changed_key = auth_client.post(
        "/api/v1/chat",
        headers={**lookup_headers, "Idempotency-Key": "chat-prebind-cancel-changed"},
        json={
            "message": "Xác nhận bằng khóa khác",
            "confirmation_token": proposal.json()["data"]["proposed_action"][
                "confirmation_token"
            ],
            "client_message_id": client_message_id,
        },
    )
    assert changed_key.status_code == 409, changed_key.text
    assert changed_key.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    retry = auth_client.post(
        "/api/v1/chat",
        headers={**lookup_headers, "Idempotency-Key": "chat-prebind-cancel"},
        json={
            "message": "Thử lại xác nhận",
            "confirmation_token": proposal.json()["data"]["proposed_action"][
                "confirmation_token"
            ],
            "client_message_id": client_message_id,
        },
    )
    assert retry.status_code == 200, retry.text


def test_chat_refund_confirmation_binds_idempotency_key_before_mutation_attempt(
    auth_client: TestClient,
    auth_session_factory,
    chat_action_catalog: dict[str, str],
) -> None:
    order = _create_guest_order_for_chat_action(
        auth_client,
        chat_action_catalog["variant_id"],
        idempotency_key="chat-refund-prebind-create",
        payment_method="online_demo",
    )

    async def set_order_state(order_status: str, payment_status: str) -> None:
        async with auth_session_factory() as session:
            persisted = await session.get(Order, UUID(order["id"]))
            assert persisted is not None
            payment = await session.scalar(
                select(PaymentAttempt).where(PaymentAttempt.order_id == persisted.id)
            )
            assert payment is not None
            persisted.status = order_status
            persisted.payment_status = payment_status
            payment.status = payment_status
            await session.commit()

    asyncio.run(set_order_state("completed", "demo_approved"))
    lookup_headers = {"X-Order-Lookup-Token": order["guest_lookup_token"]}
    auth_client.cookies.clear()
    proposal = auth_client.post(
        "/api/v1/chat",
        headers=lookup_headers,
        json={
            "message": "Tạo yêu cầu hoàn tiền",
            "action_context": {
                "action": "refund_request",
                "order_id": order["id"],
                "order_code": order["order_code"],
                "reason_code": "wrong_item",
                "reason_detail": "Nhận sai sản phẩm",
            },
        },
    )
    assert proposal.status_code == 200, proposal.text
    token = proposal.json()["data"]["proposed_action"]["confirmation_token"]
    message_id = "00000000-0000-0000-0000-000000000094"

    asyncio.run(set_order_state("confirmed", "demo_approved"))
    rejected = auth_client.post(
        "/api/v1/chat",
        headers={**lookup_headers, "Idempotency-Key": "chat-refund-prebind"},
        json={
            "message": "Xác nhận",
            "confirmation_token": token,
            "client_message_id": message_id,
        },
    )
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["error"]["code"] == "REFUND_NOT_ELIGIBLE"

    asyncio.run(set_order_state("completed", "demo_approved"))
    changed_key = auth_client.post(
        "/api/v1/chat",
        headers={**lookup_headers, "Idempotency-Key": "chat-refund-prebind-changed"},
        json={
            "message": "Xác nhận bằng khóa khác",
            "confirmation_token": token,
            "client_message_id": message_id,
        },
    )
    assert changed_key.status_code == 409, changed_key.text
    assert changed_key.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    async def refund_count() -> int:
        async with auth_session_factory() as session:
            rows = await session.scalars(
                select(RefundRequest).where(RefundRequest.order_id == UUID(order["id"]))
            )
            return len(rows.all())

    assert asyncio.run(refund_count()) == 0
    retry = auth_client.post(
        "/api/v1/chat",
        headers={**lookup_headers, "Idempotency-Key": "chat-refund-prebind"},
        json={
            "message": "Thử lại xác nhận",
            "confirmation_token": token,
            "client_message_id": message_id,
        },
    )
    assert retry.status_code == 200, retry.text
    assert asyncio.run(refund_count()) == 1


def test_chat_refund_request_uses_server_order_amount(
    auth_client: TestClient,
    auth_session_factory,
    chat_action_catalog: dict[str, str],
) -> None:
    cart = auth_client.post(
        "/api/v1/cart/items",
        json={"variant_id": chat_action_catalog["variant_id"], "quantity": 1},
    ).json()["data"]
    checkout = {
        "cart_id": cart["cart_id"],
        "cart_version": cart["version"],
        "recipient_name": "Nguyễn Văn An",
        "phone": "0901234567",
        "address_line": "1 Nguyễn Huệ",
        "ward": None,
        "district": None,
        "province": "TP.HCM",
        "note": None,
        "payment_method": "cod",
    }
    token = auth_client.post(
        "/api/v1/action-confirmations",
        json={
            "action": "order_create",
            "resource_key": cart["cart_id"],
            "payload": checkout,
        },
    ).json()["data"]["confirmation_token"]
    created = auth_client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": "direct-create-for-chat-refund"},
        json={**checkout, "confirmation_token": token},
    ).json()["data"]

    async def complete_order() -> None:
        async with auth_session_factory() as session:
            order = await session.get(Order, UUID(created["id"]))
            assert order is not None
            order.status = "completed"
            order.payment_status = "paid_demo"
            payment = await session.scalar(
                select(PaymentAttempt).where(PaymentAttempt.order_id == order.id)
            )
            assert payment is not None
            payment.status = "paid_demo"
            await session.commit()

    asyncio.run(complete_order())
    proposal = auth_client.post(
        "/api/v1/chat",
        json={
            "message": "Tạo yêu cầu hoàn tiền 999999999 đồng",
            "action_context": {
                "action": "refund_request",
                "order_id": created["id"],
                "order_code": created["order_code"],
                "reason_code": "wrong_item",
                "reason_detail": "Nhận sai sản phẩm",
            },
        },
    )
    assert proposal.status_code == 200, proposal.text
    confirmed = auth_client.post(
        "/api/v1/chat",
        headers={"Idempotency-Key": "chat-refund-request-001"},
        json={
            "message": "Xác nhận",
            "confirmation_token": proposal.json()["data"]["proposed_action"][
                "confirmation_token"
            ],
            "client_message_id": "00000000-0000-0000-0000-000000000093",
        },
    )
    assert confirmed.status_code == 200, confirmed.text

    async def load_refund() -> RefundRequest | None:
        async with auth_session_factory() as session:
            return await session.scalar(select(RefundRequest))

    refund = asyncio.run(load_refund())
    assert refund is not None
    assert refund.amount == created["total"]
    assert refund.reason_code == "wrong_item"


def test_chat_guest_lookup_can_propose_and_confirm_refund_without_cart_cookie(
    auth_client: TestClient,
    auth_session_factory,
    chat_action_catalog: dict[str, str],
) -> None:
    order = _create_guest_order_for_chat_action(
        auth_client,
        chat_action_catalog["variant_id"],
        idempotency_key="chat-lookup-refund-create",
        payment_method="online_demo",
    )

    async def complete_order() -> None:
        async with auth_session_factory() as session:
            persisted = await session.get(Order, UUID(order["id"]))
            assert persisted is not None
            payment = await session.scalar(
                select(PaymentAttempt).where(PaymentAttempt.order_id == persisted.id)
            )
            assert payment is not None
            persisted.status = "completed"
            persisted.payment_status = "demo_approved"
            payment.status = "demo_approved"
            await session.commit()

    asyncio.run(complete_order())
    lookup_headers = {"X-Order-Lookup-Token": order["guest_lookup_token"]}
    auth_client.cookies.clear()
    proposal = auth_client.post(
        "/api/v1/chat",
        headers=lookup_headers,
        json={
            "message": "Tạo yêu cầu hoàn tiền",
            "action_context": {
                "action": "refund_request",
                "order_id": order["id"],
                "order_code": order["order_code"],
                "reason_code": "wrong_item",
                "reason_detail": "Nhận sai sản phẩm",
            },
        },
    )
    assert proposal.status_code == 200, proposal.text

    confirmed = auth_client.post(
        "/api/v1/chat",
        headers={
            **lookup_headers,
            "Idempotency-Key": "chat-lookup-refund-confirm",
        },
        json={
            "message": "Xác nhận",
            "confirmation_token": proposal.json()["data"]["proposed_action"][
                "confirmation_token"
            ],
            "client_message_id": "00000000-0000-0000-0000-000000000086",
        },
    )

    assert confirmed.status_code == 200, confirmed.text
    persisted = auth_client.get(
        f"/api/v1/orders/{order['order_code']}/refund-requests/latest",
        headers=lookup_headers,
    )
    assert persisted.status_code == 200, persisted.text
    assert persisted.json()["data"]["amount"] == order["total"]


def _client(monkeypatch) -> TestClient:
    async def fake_session():
        yield object()

    async def fake_orchestrate(**kwargs):
        assert kwargs["message"] == "Tìm áo thun đen"
        assert kwargs["history"][0].role == "user"
        assert "commerce_repository" in kwargs
        assert "ownership_context" in kwargs
        return ChatResult(
            answer="Áo thun đen: 249.000 ₫; còn hàng.",
            products=[
                ChatProduct(
                    id=PRODUCT_ID,
                    slug="ao-thun-den",
                    name="Áo thun đen",
                    image_url="/media/ao.svg",
                    effective_price=249_000,
                    available_colors=["Đen"],
                    available_sizes=["M"],
                    in_stock=True,
                    url="/san-pham/ao-thun-den",
                )
            ],
            sources=[
                ChatSource(
                    product_id=PRODUCT_ID,
                    rag_document_id=DOCUMENT_ID,
                    chunk_ids=[CHUNK_ID],
                    source_type="product",
                    source_id=PRODUCT_ID,
                    knowledge_type=None,
                    title="Áo thun đen",
                )
            ],
            status="ok",
        )

    monkeypatch.setattr(chat_api, "orchestrate_chat", fake_orchestrate)
    application = create_app()
    application.dependency_overrides[get_db_session] = fake_session
    return TestClient(application)


def test_chat_endpoint_contract_and_hydrated_response(monkeypatch) -> None:
    with _client(monkeypatch) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "message": "Tìm áo thun đen",
                "history": [{"role": "user", "content": "size M"}],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "ok"
    assert payload["data"]["proposed_action"] is None
    assert payload["data"]["products"][0]["id"] == str(PRODUCT_ID)
    assert payload["data"]["products"][0]["url"] == "/san-pham/ao-thun-den"
    assert payload["data"]["sources"][0] == {
        "source_type": "product",
        "source_id": str(PRODUCT_ID),
        "product_id": str(PRODUCT_ID),
        "rag_document_id": str(DOCUMENT_ID),
        "chunk_ids": [str(CHUNK_ID)],
        "knowledge_type": None,
        "title": "Áo thun đen",
    }
    assert payload["meta"]["request_id"]


def test_chat_endpoint_forwards_typed_action_context_to_production_adapter(
    monkeypatch,
) -> None:
    observed = {}

    async def fake_orchestrate(**kwargs):
        observed.update(kwargs)
        return ChatResult(
            answer="Xác nhận thêm sản phẩm.",
            products=[],
            sources=[],
            status="ok",
        )

    client = _client(monkeypatch)
    monkeypatch.setattr(chat_api, "orchestrate_chat", fake_orchestrate)
    with client:
        response = client.post(
            "/api/v1/chat",
            json={
                "message": "Thêm sản phẩm",
                "action_context": {
                    "action": "cart_add",
                    "cart_id": "00000000-0000-0000-0000-000000000010",
                    "variant_id": "00000000-0000-0000-0000-000000000011",
                    "quantity": 1,
                },
            },
        )

    assert response.status_code == 200
    assert observed["action_context"].action == "cart_add"
    assert observed["action_adapter"].__class__.__name__ == "DatabaseChatActionAdapter"


def test_unrelated_malformed_idempotency_header_does_not_reject_read_only_chat(
    monkeypatch,
) -> None:
    with _client(monkeypatch) as client:
        response = client.post(
            "/api/v1/chat",
            headers={"Idempotency-Key": "x"},
            json={
                "message": "Tìm áo thun đen",
                "history": [{"role": "user", "content": "size M"}],
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"


def test_chat_endpoint_forwards_locked_guest_order_lookup_evidence(monkeypatch) -> None:
    ownership = CommerceOwnershipContext(
        order_code="DH-20261103-ABC123", order_lookup_token_hash="lookup-hash"
    )
    repository = object()

    async def fake_orchestrate(**kwargs):
        assert kwargs["message"] == "Đơn DH-20261103-ABC123 của tôi đang ở đâu?"
        assert kwargs["ownership_context"] is ownership
        assert kwargs["commerce_repository"] is repository
        assert ownership.guest_token_hash is None
        return ChatResult(
            answer="Đơn DH-20261103-ABC123 hiện đang chuẩn bị, tổng tiền 750.000 ₫.",
            products=[],
            sources=[],
            status="ok",
        )

    client = _client(monkeypatch)
    monkeypatch.setattr(chat_api, "orchestrate_chat", fake_orchestrate)
    client.app.dependency_overrides[chat_api.get_commerce_read_repository] = (
        lambda: repository
    )
    client.app.dependency_overrides[chat_api.get_commerce_ownership_context] = (
        lambda: ownership
    )

    with client:
        response = client.post(
            "/api/v1/chat",
            json={"message": "Đơn DH-20261103-ABC123 của tôi đang ở đâu?"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"


def test_chat_endpoint_serializes_return_policy_knowledge_source(monkeypatch) -> None:
    async def fake_policy_orchestrate(**_kwargs):
        return ChatResult(
            answer="Bạn có thể đổi hàng trong 07 ngày.",
            products=[],
            sources=[
                ChatSource(
                    source_type="knowledge",
                    source_id=PRODUCT_ID,
                    rag_document_id=DOCUMENT_ID,
                    chunk_ids=[CHUNK_ID],
                    product_id=None,
                    knowledge_type="return_policy",
                    title="Chính sách đổi trả",
                )
            ],
            status="ok",
        )

    client = _client(monkeypatch)
    monkeypatch.setattr(chat_api, "orchestrate_chat", fake_policy_orchestrate)
    with client:
        response = client.post("/api/v1/chat", json={"message": "Đổi hàng thế nào?"})

    assert response.status_code == 200
    assert response.json()["data"] == {
        "answer": "Bạn có thể đổi hàng trong 07 ngày.",
        "products": [],
        "sources": [
            {
                "source_type": "knowledge",
                "source_id": str(PRODUCT_ID),
                "rag_document_id": str(DOCUMENT_ID),
                "chunk_ids": [str(CHUNK_ID)],
                "product_id": None,
                "knowledge_type": "return_policy",
                "title": "Chính sách đổi trả",
            }
        ],
        "status": "ok",
        "proposed_action": None,
    }


def test_chat_request_bounds_message_and_history(monkeypatch) -> None:
    with _client(monkeypatch) as client:
        too_long = client.post("/api/v1/chat", json={"message": "x" * 1001})
        blank = client.post("/api/v1/chat", json={"message": "   "})
        too_many_turns = client.post(
            "/api/v1/chat",
            json={
                "message": "Tìm áo",
                "history": [
                    {"role": "user", "content": f"lượt {index}"}
                    for index in range(7)
                ],
            },
        )

    assert too_long.status_code == 422
    assert blank.status_code == 422
    assert too_many_turns.status_code == 422
    assert too_long.json()["error"]["code"] == "VALIDATION_ERROR"


def test_openapi_exposes_public_bounded_chat_contract(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/chat"]["post"]

    assert operation.get("security") is None
    header_parameters = {
        parameter["name"]: parameter for parameter in operation["parameters"]
    }
    assert header_parameters["Idempotency-Key"]["required"] is False
    assert header_parameters["X-Order-Lookup-Token"]["required"] is False
    lookup_schema = header_parameters["X-Order-Lookup-Token"]["schema"]["anyOf"][0]
    assert lookup_schema["minLength"] == 20
    assert lookup_schema["maxLength"] == 200
    assert operation["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ] == "#/components/schemas/ChatEnvelope"
    request_ref = operation["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    assert request_ref == "#/components/schemas/ChatRequest"
    request_schema = schema["components"]["schemas"]["ChatRequest"]
    assert request_schema["properties"]["message"]["maxLength"] == 1000
    assert request_schema["properties"]["history"]["maxItems"] == 6
    status_schema = schema["components"]["schemas"]["ChatResponse"]["properties"][
        "status"
    ]
    assert set(status_schema["enum"]) == {
        "ok",
        "insufficient_data",
        "out_of_scope",
        "provider_unavailable",
    }
    source_schema = schema["components"]["schemas"]["ChatSourceResponse"]
    assert set(source_schema["required"]) == {
        "source_type",
        "source_id",
        "rag_document_id",
        "chunk_ids",
        "product_id",
        "knowledge_type",
        "title",
    }
    assert set(source_schema["properties"]["source_type"]["enum"]) == {
        "product",
        "knowledge",
    }
    proposed_action = schema["components"]["schemas"]["ProposedActionResponse"]
    assert set(proposed_action["required"]) == {
        "action",
        "resource_code",
        "summary",
        "requires_confirmation",
        "confirmation_token",
        "expires_at",
    }
    assert "proposed_action" in schema["components"]["schemas"]["ChatResponse"][
        "properties"
    ]


def test_chat_endpoint_rate_limits_public_provider_calls(monkeypatch) -> None:
    client = _client(monkeypatch)
    limited_settings = Settings(
        _env_file=None,
        app_env="test",
        app_secret_key="test-only-secret",
        database_url="postgresql+asyncpg://shop:shop@localhost:5432/shop_test",
        chat_rate_limit_requests=1,
    )
    client.app.dependency_overrides[get_settings] = lambda: limited_settings

    payload = {
        "message": "Tìm áo thun đen",
        "history": [{"role": "user", "content": "size M"}],
    }
    with client:
        first = client.post("/api/v1/chat", json=payload)
        second = client.post("/api/v1/chat", json=payload)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "RATE_LIMITED"


def test_chat_endpoint_rejects_oversized_body_before_validation(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        json={"message": "Tìm áo", "ignored": "x" * 40_000},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"


def test_chat_body_limit_counts_streamed_chunks_without_content_length() -> None:
    async def exercise():
        sent = []
        chunks = iter(
            [
                {"type": "http.request", "body": b"123456", "more_body": True},
                {"type": "http.request", "body": b"78901", "more_body": False},
            ]
        )

        async def downstream(_scope, _receive, _send):
            raise AssertionError("oversized request must not reach the application")

        async def receive():
            return next(chunks)

        async def send(message):
            sent.append(message)

        middleware = ChatBodyLimitMiddleware(downstream, max_body_bytes=10)
        await middleware(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/api/v1/chat",
                "raw_path": b"/api/v1/chat",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 1234),
                "server": ("test", 80),
                "state": {"request_id": "stream-test"},
            },
            receive,
            send,
        )
        return sent

    sent = asyncio.run(exercise())

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    assert response_start["status"] == 413
