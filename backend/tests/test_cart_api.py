import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.security import hash_token
from app.models.auth import User
from app.models.commerce import Cart, Coupon, CouponRedemption, Order
from app.models.catalog import Category, Color, Product, ProductVariant, Size


@pytest.fixture
def cart_client(auth_client: TestClient) -> TestClient:
    return auth_client


@pytest.fixture
def cart_catalog(auth_session_factory) -> dict[str, str]:
    async def seed() -> dict[str, str]:
        async with auth_session_factory() as session:
            category = Category(name="Áo thun", slug="ao-thun-cart")
            color = Color(name="Đen", slug="den-cart", hex_code="#000000")
            size = Size(code="M-CART", name="M", sort_order=2)
            product = Product(
                category=category,
                sku="CART-AT-001",
                slug="ao-thun-cart",
                name="Áo thun cho giỏ hàng",
                price=300_000,
                sale_price=250_000,
            )
            variant = ProductVariant(
                product=product,
                color=color,
                size=size,
                variant_sku="CART-AT-001-DEN-M",
                stock_quantity=5,
            )
            session.add_all([category, color, size, product, variant])
            await session.commit()
            return {
                "variant_id": str(variant.id),
                "product_id": str(product.id),
            }

    return asyncio.run(seed())


@pytest.fixture
def valid_coupon(auth_session_factory) -> None:
    async def seed() -> None:
        async with auth_session_factory() as session:
            session.add(
                Coupon(
                    code="GIAM10",
                    description="Giảm 10% tối đa 40.000 VND",
                    discount_type="percent",
                    discount_value=10,
                    max_discount=40_000,
                    min_subtotal=200_000,
                    per_user_limit=1,
                )
            )
            await session.commit()

    asyncio.run(seed())


def test_anonymous_empty_cart_read_does_not_persist_cart(
    cart_client: TestClient, auth_session_factory
) -> None:
    response = cart_client.get("/api/v1/cart")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "cart_id": None,
        "version": 0,
        "items": [],
        "item_count": 0,
        "coupon_code": None,
        "subtotal": 0,
        "discount_amount": 0,
        "shipping_fee": 0,
        "total": 0,
        "currency": "VND",
    }
    assert "shop_guest" not in response.cookies

    async def count_carts() -> int:
        async with auth_session_factory() as session:
            count = await session.scalar(select(func.count()).select_from(Cart))
            return int(count or 0)

    assert asyncio.run(count_carts()) == 0


def test_guest_adds_live_variant_with_server_calculated_totals(
    cart_client: TestClient, auth_session_factory, cart_catalog
) -> None:
    response = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 2},
    )

    assert response.status_code == 201
    raw_guest_token = response.cookies["shop_guest"]
    cart = response.json()["data"]
    assert cart["version"] == 2
    assert cart["item_count"] == 2
    assert cart["subtotal"] == 500_000
    assert cart["discount_amount"] == 0
    assert cart["shipping_fee"] == 0
    assert cart["total"] == 500_000
    assert cart["currency"] == "VND"
    assert cart["items"] == [
        {
            "item_id": cart["items"][0]["item_id"],
            "variant_id": cart_catalog["variant_id"],
            "product_id": cart_catalog["product_id"],
            "product_slug": "ao-thun-cart",
            "product_name": "Áo thun cho giỏ hàng",
            "variant_sku": "CART-AT-001-DEN-M",
            "color_name": "Đen",
            "size_code": "M-CART",
            "quantity": 2,
            "stock_quantity": 5,
            "is_available": True,
            "unit_price": 250_000,
            "previous_unit_price": 250_000,
            "price_changed": False,
            "line_total": 500_000,
        }
    ]

    async def persisted_guest_hash() -> str | None:
        async with auth_session_factory() as session:
            persisted = await session.get(Cart, UUID(cart["cart_id"]))
            assert persisted is not None
            return persisted.guest_token_hash

    assert asyncio.run(persisted_guest_hash()) == hash_token(raw_guest_token)


def test_cart_rejects_quantity_above_live_stock(
    cart_client: TestClient, cart_catalog
) -> None:
    response = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 6},
    )

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "OUT_OF_STOCK",
        "message": "Sản phẩm không đủ tồn kho.",
        "fields": {"quantity": "Tối đa 5"},
        "details": {
            "variant_id": cart_catalog["variant_id"],
            "available": 5,
            "requested": 6,
        },
    }
    assert cart_client.get("/api/v1/cart").json()["data"]["cart_id"] is None


def test_guest_updates_owned_item_with_current_cart_version(
    cart_client: TestClient, cart_catalog
) -> None:
    added = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 1},
    ).json()["data"]

    response = cart_client.patch(
        f"/api/v1/cart/items/{added['items'][0]['item_id']}",
        json={"quantity": 4, "cart_version": added["version"]},
    )

    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["version"] == added["version"] + 1
    assert updated["items"][0]["quantity"] == 4
    assert updated["subtotal"] == 1_000_000


def test_stale_cart_version_is_rejected_without_mutation(
    cart_client: TestClient, cart_catalog
) -> None:
    added = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 1},
    ).json()["data"]
    item_id = added["items"][0]["item_id"]
    updated = cart_client.patch(
        f"/api/v1/cart/items/{item_id}",
        json={"quantity": 2, "cart_version": added["version"]},
    ).json()["data"]

    response = cart_client.patch(
        f"/api/v1/cart/items/{item_id}",
        json={"quantity": 3, "cart_version": added["version"]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CART_VERSION_CONFLICT"
    assert response.json()["error"]["details"] == {
        "expected_version": updated["version"],
        "provided_version": added["version"],
    }
    current = cart_client.get("/api/v1/cart").json()["data"]
    assert current["version"] == updated["version"]
    assert current["items"][0]["quantity"] == 2


def test_guest_removes_owned_item_with_current_cart_version(
    cart_client: TestClient, cart_catalog
) -> None:
    added = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 2},
    ).json()["data"]

    response = cart_client.request(
        "DELETE",
        f"/api/v1/cart/items/{added['items'][0]['item_id']}",
        json={"cart_version": added["version"]},
    )

    assert response.status_code == 200
    removed = response.json()["data"]
    assert removed["version"] == added["version"] + 1
    assert removed["items"] == []
    assert removed["total"] == 0


def test_cart_mutation_rejects_live_price_change(
    cart_client: TestClient, auth_session_factory, cart_catalog
) -> None:
    added = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 1},
    ).json()["data"]

    async def change_price() -> None:
        async with auth_session_factory() as session:
            product = await session.get(Product, UUID(cart_catalog["product_id"]))
            assert product is not None
            product.sale_price = 240_000
            await session.commit()

    asyncio.run(change_price())
    response = cart_client.patch(
        f"/api/v1/cart/items/{added['items'][0]['item_id']}",
        json={"quantity": 2, "cart_version": added["version"]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PRICE_CHANGED"
    assert response.json()["error"]["details"] == {
        "variant_id": cart_catalog["variant_id"],
        "previous_unit_price": 250_000,
        "current_unit_price": 240_000,
    }
    current = cart_client.get("/api/v1/cart").json()["data"]
    assert current["items"][0]["price_changed"] is True
    assert current["items"][0]["unit_price"] == 240_000
    assert current["items"][0]["quantity"] == 1


def test_price_changed_has_typed_remove_and_readd_recovery_flow(
    cart_client: TestClient, auth_session_factory, cart_catalog
) -> None:
    added = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 1},
    ).json()["data"]
    item_id = added["items"][0]["item_id"]

    async def change_price() -> None:
        async with auth_session_factory() as session:
            product = await session.get(Product, UUID(cart_catalog["product_id"]))
            assert product is not None
            product.sale_price = 240_000
            await session.commit()

    asyncio.run(change_price())
    rejected = cart_client.patch(
        f"/api/v1/cart/items/{item_id}",
        json={"quantity": 2, "cart_version": added["version"]},
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "PRICE_CHANGED"

    refreshed = cart_client.get("/api/v1/cart").json()["data"]
    assert refreshed["items"][0]["price_changed"] is True
    assert refreshed["items"][0]["previous_unit_price"] == 250_000
    assert refreshed["items"][0]["unit_price"] == 240_000
    removed = cart_client.request(
        "DELETE",
        f"/api/v1/cart/items/{item_id}",
        json={"cart_version": refreshed["version"]},
    ).json()["data"]
    recovered = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 1},
    ).json()["data"]

    assert recovered["version"] == removed["version"] + 1
    assert recovered["items"][0]["previous_unit_price"] == 240_000
    assert recovered["items"][0]["unit_price"] == 240_000
    assert recovered["items"][0]["price_changed"] is False
    accepted = cart_client.patch(
        f"/api/v1/cart/items/{recovered['items'][0]['item_id']}",
        json={"quantity": 2, "cart_version": recovered["version"]},
    )
    assert accepted.status_code == 200
    assert accepted.json()["data"]["items"][0]["quantity"] == 2


def test_guest_applies_valid_coupon_with_server_calculated_cap(
    cart_client: TestClient, cart_catalog, valid_coupon
) -> None:
    added = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 2},
    ).json()["data"]

    response = cart_client.post(
        "/api/v1/cart/coupon",
        json={"code": "  giam10  ", "cart_version": added["version"]},
    )

    assert response.status_code == 200
    cart = response.json()["data"]
    assert cart["version"] == added["version"] + 1
    assert cart["coupon_code"] == "GIAM10"
    assert cart["subtotal"] == 500_000
    assert cart["discount_amount"] == 40_000
    assert cart["shipping_fee"] == 0
    assert cart["total"] == 460_000


def test_guest_removes_coupon_with_current_cart_version(
    cart_client: TestClient, cart_catalog, valid_coupon
) -> None:
    added = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 2},
    ).json()["data"]
    discounted = cart_client.post(
        "/api/v1/cart/coupon",
        json={"code": "GIAM10", "cart_version": added["version"]},
    ).json()["data"]

    response = cart_client.request(
        "DELETE",
        "/api/v1/cart/coupon",
        json={"cart_version": discounted["version"]},
    )

    assert response.status_code == 200
    cart = response.json()["data"]
    assert cart["version"] == discounted["version"] + 1
    assert cart["coupon_code"] is None
    assert cart["discount_amount"] == 0
    assert cart["total"] == 500_000


def test_login_claims_guest_cart_transactionally(
    cart_client: TestClient, create_auth_user, cart_catalog, auth_session_factory
) -> None:
    create_auth_user("cart-owner@example.com")
    guest_cart = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 2},
    ).json()["data"]

    login = cart_client.post(
        "/api/v1/auth/login",
        json={
            "email": "cart-owner@example.com",
            "password": "MatKhau-AnToan-123",
        },
    )

    assert login.status_code == 200
    assert "shop_guest" not in cart_client.cookies
    claimed = cart_client.get("/api/v1/cart").json()["data"]
    assert claimed["cart_id"] == guest_cart["cart_id"]
    assert claimed["items"][0]["quantity"] == 2

    async def owner_state() -> tuple[UUID | None, str | None]:
        async with auth_session_factory() as session:
            cart = await session.get(Cart, UUID(guest_cart["cart_id"]))
            assert cart is not None
            return cart.user_id, cart.guest_token_hash

    user_id, guest_hash = asyncio.run(owner_state())
    assert user_id is not None
    assert guest_hash is None


def test_guest_cannot_mutate_another_guest_cart_item(
    cart_client: TestClient, cart_catalog
) -> None:
    added = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 1},
    ).json()["data"]

    with TestClient(cart_client.app) as other_guest:
        response = other_guest.patch(
            f"/api/v1/cart/items/{added['items'][0]['item_id']}",
            json={"quantity": 2, "cart_version": added["version"]},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CART_ITEM_NOT_FOUND"
    assert cart_client.get("/api/v1/cart").json()["data"]["items"][0][
        "quantity"
    ] == 1


def test_adding_existing_item_rejects_live_price_change(
    cart_client: TestClient, auth_session_factory, cart_catalog
) -> None:
    cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 1},
    )

    async def change_price() -> None:
        async with auth_session_factory() as session:
            product = await session.get(Product, UUID(cart_catalog["product_id"]))
            assert product is not None
            product.sale_price = 240_000
            await session.commit()

    asyncio.run(change_price())
    response = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 1},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PRICE_CHANGED"


@pytest.mark.parametrize(
    ("coupon", "expected_code"),
    [
        (None, "COUPON_INVALID"),
        (
            {
                "code": "HETHAN",
                "discount_type": "fixed",
                "discount_value": 50_000,
                "min_subtotal": 0,
                "ends_at": datetime.now(timezone.utc) - timedelta(days=1),
            },
            "COUPON_EXPIRED",
        ),
        (
            {
                "code": "TOITHIEU",
                "discount_type": "fixed",
                "discount_value": 50_000,
                "min_subtotal": 600_000,
            },
            "COUPON_NOT_APPLICABLE",
        ),
    ],
)
def test_coupon_boundary_returns_stable_error_code(
    cart_client: TestClient,
    auth_session_factory,
    cart_catalog,
    coupon,
    expected_code,
) -> None:
    if coupon is not None:
        async def seed_coupon() -> None:
            async with auth_session_factory() as session:
                session.add(Coupon(**coupon))
                await session.commit()

        asyncio.run(seed_coupon())
        code = coupon["code"]
    else:
        code = "KHONGTONTAI"
    added = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 2},
    ).json()["data"]

    response = cart_client.post(
        "/api/v1/cart/coupon",
        json={"code": code, "cart_version": added["version"]},
    )

    assert response.status_code in {400, 409}
    assert response.json()["error"]["code"] == expected_code


def test_login_merges_duplicate_variant_deterministically_at_live_stock(
    cart_client: TestClient, create_auth_user, cart_catalog
) -> None:
    create_auth_user("merge-cart@example.com")
    assert cart_client.post(
        "/api/v1/auth/login",
        json={
            "email": "merge-cart@example.com",
            "password": "MatKhau-AnToan-123",
        },
    ).status_code == 200
    customer_cart = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 4},
    ).json()["data"]
    assert cart_client.post("/api/v1/auth/logout").status_code == 200
    guest_cart = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 3},
    ).json()["data"]

    assert cart_client.post(
        "/api/v1/auth/login",
        json={
            "email": "merge-cart@example.com",
            "password": "MatKhau-AnToan-123",
        },
    ).status_code == 200

    merged = cart_client.get("/api/v1/cart").json()["data"]
    assert merged["cart_id"] == customer_cart["cart_id"]
    assert merged["items"][0]["quantity"] == 5
    assert merged["version"] == customer_cart["version"] + 1
    assert merged["cart_id"] != guest_cart["cart_id"]


def test_applied_coupon_stops_discounting_when_deactivated(
    cart_client: TestClient, auth_session_factory, cart_catalog, valid_coupon
) -> None:
    added = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 2},
    ).json()["data"]
    applied = cart_client.post(
        "/api/v1/cart/coupon",
        json={"code": "GIAM10", "cart_version": added["version"]},
    ).json()["data"]
    assert applied["discount_amount"] == 40_000

    async def deactivate_coupon() -> None:
        async with auth_session_factory() as session:
            coupon = await session.scalar(select(Coupon).where(Coupon.code == "GIAM10"))
            assert coupon is not None
            coupon.is_active = False
            await session.commit()

    asyncio.run(deactivate_coupon())
    current = cart_client.get("/api/v1/cart").json()["data"]

    assert current["coupon_code"] == "GIAM10"
    assert current["discount_amount"] == 0
    assert current["total"] == 500_000


def test_coupon_rejects_authenticated_owner_at_per_user_limit(
    cart_client: TestClient,
    create_auth_user,
    auth_session_factory,
    cart_catalog,
    valid_coupon,
) -> None:
    email = "coupon-limit@example.com"
    create_auth_user(email)

    async def seed_redemption() -> None:
        async with auth_session_factory() as session:
            user = await session.scalar(select(User).where(User.email == email))
            coupon = await session.scalar(select(Coupon).where(Coupon.code == "GIAM10"))
            assert user is not None and coupon is not None
            order = Order(
                order_code="ORDER-COUPON-LIMIT",
                user_id=user.id,
                coupon_id=coupon.id,
                recipient_name="Người Dùng Kiểm Thử",
                phone="0900000000",
                address_line="1 Đường Kiểm Thử",
                province="TP. Hồ Chí Minh",
                payment_method="cod",
                payment_status="cod_due",
                subtotal=250_000,
                discount_amount=25_000,
                shipping_fee=30_000,
                total=255_000,
            )
            session.add(order)
            await session.flush()
            session.add(
                CouponRedemption(
                    coupon_id=coupon.id,
                    order_id=order.id,
                    user_id=user.id,
                    discount_amount=25_000,
                )
            )
            await session.commit()

    asyncio.run(seed_redemption())
    cart_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "MatKhau-AnToan-123"},
    )
    cart = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 1},
    ).json()["data"]

    response = cart_client.post(
        "/api/v1/cart/coupon",
        json={"code": "GIAM10", "cart_version": cart["version"]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "COUPON_NOT_APPLICABLE"


def test_login_claim_revalidates_guest_coupon_for_authenticated_owner(
    cart_client: TestClient,
    create_auth_user,
    auth_session_factory,
    cart_catalog,
    valid_coupon,
) -> None:
    email = "coupon-claim-limit@example.com"
    create_auth_user(email)
    added = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 2},
    ).json()["data"]
    applied = cart_client.post(
        "/api/v1/cart/coupon",
        json={"code": "GIAM10", "cart_version": added["version"]},
    ).json()["data"]
    assert applied["discount_amount"] == 40_000

    async def seed_authenticated_redemption() -> None:
        async with auth_session_factory() as session:
            user = await session.scalar(select(User).where(User.email == email))
            coupon = await session.scalar(select(Coupon).where(Coupon.code == "GIAM10"))
            assert user is not None and coupon is not None
            order = Order(
                order_code="ORDER-COUPON-CLAIM-LIMIT",
                user_id=user.id,
                coupon_id=coupon.id,
                recipient_name="Người Dùng Kiểm Thử",
                phone="0900000000",
                address_line="1 Đường Kiểm Thử",
                province="TP. Hồ Chí Minh",
                payment_method="cod",
                payment_status="cod_due",
                subtotal=500_000,
                discount_amount=40_000,
                shipping_fee=0,
                total=460_000,
            )
            session.add(order)
            await session.flush()
            session.add(
                CouponRedemption(
                    coupon_id=coupon.id,
                    order_id=order.id,
                    user_id=user.id,
                    discount_amount=40_000,
                )
            )
            await session.commit()

    asyncio.run(seed_authenticated_redemption())
    login = cart_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "MatKhau-AnToan-123"},
    )

    assert login.status_code == 200
    claimed = cart_client.get("/api/v1/cart").json()["data"]
    assert claimed["coupon_code"] == "GIAM10"
    assert claimed["discount_amount"] == 0
    assert claimed["total"] == 500_000


def test_cart_read_revalidates_coupon_after_owner_reaches_per_user_limit(
    cart_client: TestClient,
    create_auth_user,
    auth_session_factory,
    cart_catalog,
    valid_coupon,
) -> None:
    email = "coupon-live-limit@example.com"
    create_auth_user(email)
    assert cart_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "MatKhau-AnToan-123"},
    ).status_code == 200
    added = cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 2},
    ).json()["data"]
    applied = cart_client.post(
        "/api/v1/cart/coupon",
        json={"code": "GIAM10", "cart_version": added["version"]},
    ).json()["data"]
    assert applied["discount_amount"] == 40_000

    async def redeem_coupon_elsewhere() -> None:
        async with auth_session_factory() as session:
            user = await session.scalar(select(User).where(User.email == email))
            coupon = await session.scalar(select(Coupon).where(Coupon.code == "GIAM10"))
            assert user is not None and coupon is not None
            order = Order(
                order_code="ORDER-COUPON-LIVE-LIMIT",
                user_id=user.id,
                coupon_id=coupon.id,
                recipient_name="Người Dùng Kiểm Thử",
                phone="0900000000",
                address_line="1 Đường Kiểm Thử",
                province="TP. Hồ Chí Minh",
                payment_method="cod",
                payment_status="cod_due",
                subtotal=500_000,
                discount_amount=40_000,
                shipping_fee=0,
                total=460_000,
            )
            session.add(order)
            await session.flush()
            session.add(
                CouponRedemption(
                    coupon_id=coupon.id,
                    order_id=order.id,
                    user_id=user.id,
                    discount_amount=40_000,
                )
            )
            await session.commit()

    asyncio.run(redeem_coupon_elsewhere())
    current = cart_client.get("/api/v1/cart").json()["data"]

    assert current["coupon_code"] == "GIAM10"
    assert current["discount_amount"] == 0
    assert current["total"] == 500_000
    mutated = cart_client.patch(
        f"/api/v1/cart/items/{current['items'][0]['item_id']}",
        json={"quantity": 1, "cart_version": current["version"]},
    ).json()["data"]
    assert mutated["coupon_code"] == "GIAM10"
    assert mutated["discount_amount"] == 0
    assert mutated["total"] == 280_000


def test_login_merge_keeps_positive_quantity_when_stock_drops_to_zero(
    cart_client: TestClient, create_auth_user, auth_session_factory, cart_catalog
) -> None:
    create_auth_user("merge-zero-stock@example.com")
    cart_client.post(
        "/api/v1/auth/login",
        json={
            "email": "merge-zero-stock@example.com",
            "password": "MatKhau-AnToan-123",
        },
    )
    cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 1},
    )
    cart_client.post("/api/v1/auth/logout")
    cart_client.post(
        "/api/v1/cart/items",
        json={"variant_id": cart_catalog["variant_id"], "quantity": 1},
    )

    async def remove_stock() -> None:
        async with auth_session_factory() as session:
            variant = await session.get(ProductVariant, UUID(cart_catalog["variant_id"]))
            assert variant is not None
            variant.stock_quantity = 0
            await session.commit()

    asyncio.run(remove_stock())
    login = cart_client.post(
        "/api/v1/auth/login",
        json={
            "email": "merge-zero-stock@example.com",
            "password": "MatKhau-AnToan-123",
        },
    )

    assert login.status_code == 200
    merged = cart_client.get("/api/v1/cart").json()["data"]
    assert merged["items"][0]["quantity"] > 0
    assert merged["items"][0]["is_available"] is False
