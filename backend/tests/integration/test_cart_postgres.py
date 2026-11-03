import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import hash_password
from app.db.session import get_db_session
from app.main import create_app
from app.models.auth import User
from app.models.catalog import Category, Color, Product, ProductVariant, Size
from app.models.commerce import Coupon, CouponRedemption, InventoryMovement, Order
from tests.integration.database_guard import require_fresh_migrated_database

MIGRATION_DATABASE_URL = os.getenv("MIGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not MIGRATION_DATABASE_URL,
    reason="MIGRATION_DATABASE_URL is required for PostgreSQL cart integration tests",
)


def test_postgres_cart_ownership_concurrency_live_data_and_coupon_boundaries() -> None:
    assert MIGRATION_DATABASE_URL is not None
    require_fresh_migrated_database(MIGRATION_DATABASE_URL)

    async def seed() -> tuple[str, str, str, str]:
        engine = create_async_engine(MIGRATION_DATABASE_URL)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        suffix = uuid4().hex
        async with session_factory() as session:
            category = Category(name="Áo cart PG", slug=f"cart-pg-{suffix}")
            color = Color(name="Đen", slug=f"cart-pg-black-{suffix}")
            size = Size(code=f"PG-{suffix[:8]}", name="PG")
            product = Product(
                category=category,
                sku=f"CART-PG-{suffix}",
                slug=f"cart-pg-product-{suffix}",
                name="Sản phẩm cart PostgreSQL",
                price=300_000,
                sale_price=250_000,
            )
            variant = ProductVariant(
                product=product,
                color=color,
                size=size,
                variant_sku=f"CART-PG-VARIANT-{suffix}",
                stock_quantity=5,
            )
            coupon = Coupon(
                code=f"PG10-{suffix}",
                discount_type="percent",
                discount_value=10,
                max_discount=40_000,
                min_subtotal=400_000,
                per_user_limit=1,
            )
            live_coupon = Coupon(
                code=f"PGLIVE10-{suffix}",
                discount_type="percent",
                discount_value=10,
                max_discount=40_000,
                min_subtotal=400_000,
                per_user_limit=1,
            )
            email = f"cart-pg-owner-{suffix}@example.com"
            user = User(
                email=email,
                password_hash=hash_password("MatKhau-AnToan-123"),
                full_name="Khách PostgreSQL",
                role="customer",
            )
            session.add_all(
                [category, color, size, product, variant, coupon, live_coupon, user]
            )
            await session.commit()
            result = str(variant.id), coupon.code, live_coupon.code, email
        await engine.dispose()
        return result

    variant_id, coupon_code, live_coupon_code, owner_email = asyncio.run(seed())
    application = create_app()
    with TestClient(application) as owner:
        added = owner.post(
            "/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 1}
        ).json()["data"]
        item_id = added["items"][0]["item_id"]
        guest_token = owner.cookies["shop_guest"]

        def mutate(quantity: int) -> tuple[int, str | None]:
            response = owner.patch(
                f"/api/v1/cart/items/{item_id}",
                json={"quantity": quantity, "cart_version": added["version"]},
            )
            body = response.json()
            return response.status_code, body.get("error", {}).get("code")

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(mutate, (2, 3)))
        assert sorted(status_code for status_code, _ in outcomes) == [200, 409]
        assert {code for _, code in outcomes if code} == {"CART_VERSION_CONFLICT"}

        owner.cookies.delete("shop_guest")
        denied = owner.patch(
            f"/api/v1/cart/items/{item_id}",
            json={"quantity": 1, "cart_version": added["version"] + 1},
        )
        assert denied.status_code == 404
        assert denied.json()["error"]["code"] == "CART_ITEM_NOT_FOUND"
        owner.cookies.set("shop_guest", guest_token)

        async def change_variant(*, stock: int | None = None, price: int | None = None, active: bool | None = None) -> None:
            engine = create_async_engine(MIGRATION_DATABASE_URL)
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as session:
                variant = await session.get(ProductVariant, UUID(variant_id))
                assert variant is not None
                if stock is not None:
                    variant.stock_quantity = stock
                if active is not None:
                    variant.is_active = active
                if price is not None:
                    product = await session.get(Product, variant.product_id)
                    assert product is not None
                    product.sale_price = price
                await session.commit()
            await engine.dispose()

        asyncio.run(change_variant(stock=0))
        current = owner.get("/api/v1/cart").json()["data"]
        assert current["items"][0]["is_available"] is False
        out_of_stock = owner.patch(
            f"/api/v1/cart/items/{item_id}",
            json={"quantity": 1, "cart_version": current["version"]},
        )
        assert out_of_stock.status_code == 409
        assert out_of_stock.json()["error"]["code"] == "OUT_OF_STOCK"

        asyncio.run(change_variant(stock=5, price=240_000))
        price_changed = owner.patch(
            f"/api/v1/cart/items/{item_id}",
            json={"quantity": 1, "cart_version": current["version"]},
        )
        assert price_changed.status_code == 409
        assert price_changed.json()["error"]["code"] == "PRICE_CHANGED"

        owner.cookies.delete("shop_guest")
        coupon_cart = owner.post(
            "/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 2}
        ).json()["data"]
        applied = owner.post(
            "/api/v1/cart/coupon",
            json={"code": coupon_code, "cart_version": coupon_cart["version"]},
        )
        assert applied.status_code == 200
        totals = applied.json()["data"]
        assert (totals["subtotal"], totals["discount_amount"]) == (480_000, 40_000)
        assert (totals["shipping_fee"], totals["total"]) == (30_000, 470_000)

        async def redeem_for_owner(code: str, order_code: str) -> None:
            engine = create_async_engine(MIGRATION_DATABASE_URL)
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as session:
                user = await session.scalar(select(User).where(User.email == owner_email))
                coupon = await session.scalar(select(Coupon).where(Coupon.code == code))
                assert user is not None and coupon is not None
                order = Order(
                    order_code=order_code,
                    user_id=user.id,
                    coupon_id=coupon.id,
                    recipient_name="Khách PostgreSQL",
                    phone="0900000000",
                    address_line="1 Đường PostgreSQL",
                    province="TP. Hồ Chí Minh",
                    payment_method="cod",
                    payment_status="cod_due",
                    subtotal=480_000,
                    discount_amount=40_000,
                    shipping_fee=30_000,
                    total=470_000,
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
            await engine.dispose()

        asyncio.run(redeem_for_owner(coupon_code, f"PGC-{uuid4().hex}"))
        login = owner.post(
            "/api/v1/auth/login",
            json={"email": owner_email, "password": "MatKhau-AnToan-123"},
        )
        assert login.status_code == 200
        claimed = owner.get("/api/v1/cart").json()["data"]
        assert claimed["coupon_code"] == coupon_code
        assert claimed["discount_amount"] == 0

        reapplied = owner.post(
            "/api/v1/cart/coupon",
            json={"code": live_coupon_code, "cart_version": claimed["version"]},
        )
        assert reapplied.status_code == 200
        assert reapplied.json()["data"]["discount_amount"] == 40_000
        asyncio.run(redeem_for_owner(live_coupon_code, f"PGL-{uuid4().hex}"))
        live_limited = owner.get("/api/v1/cart").json()["data"]
        assert live_limited["coupon_code"] == live_coupon_code
        assert live_limited["discount_amount"] == 0

        asyncio.run(change_variant(active=False))
        owner.cookies.delete("shop_guest")
        unavailable = owner.post(
            "/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 1}
        )
        assert unavailable.status_code == 404
        assert unavailable.json()["error"]["code"] == "VARIANT_NOT_AVAILABLE"


def test_postgres_concurrent_checkout_reserves_last_item_once() -> None:
    assert MIGRATION_DATABASE_URL is not None
    require_fresh_migrated_database(MIGRATION_DATABASE_URL)

    async def seed() -> str:
        engine = create_async_engine(MIGRATION_DATABASE_URL)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        suffix = uuid4().hex
        async with session_factory() as session:
            category = Category(name="Checkout PG", slug=f"checkout-pg-{suffix}")
            color = Color(name="Xanh PG", slug=f"checkout-blue-{suffix}")
            size = Size(code=f"CO-{suffix[:8]}", name="Checkout")
            product = Product(
                category=category,
                sku=f"CHECKOUT-PG-{suffix}",
                slug=f"checkout-pg-product-{suffix}",
                name="Sản phẩm checkout PostgreSQL",
                price=250_000,
            )
            variant = ProductVariant(
                product=product,
                color=color,
                size=size,
                variant_sku=f"CHECKOUT-PG-VARIANT-{suffix}",
                stock_quantity=1,
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

    def prepare(client: TestClient, key_suffix: str) -> tuple[dict, dict]:
        cart = client.post(
            "/api/v1/cart/items", json={"variant_id": variant_id, "quantity": 1}
        ).json()["data"]
        payload = {
            "cart_id": cart["cart_id"],
            "cart_version": cart["version"],
            "recipient_name": f"Khách {key_suffix}",
            "phone": "0901234567",
            "address_line": "1 Đường PostgreSQL",
            "province": "TP. Hồ Chí Minh",
            "payment_method": "cod",
        }
        confirmation = client.post(
            "/api/v1/action-confirmations",
            json={
                "action": "order_create",
                "resource_key": cart["cart_id"],
                "payload": payload,
            },
        )
        assert confirmation.status_code == 201, confirmation.text
        payload["confirmation_token"] = confirmation.json()["data"][
            "confirmation_token"
        ]
        return payload, {"Idempotency-Key": f"checkout-race-{key_suffix}"}

    with TestClient(application) as first, TestClient(application) as second:
        first_request = prepare(first, "first")
        second_request = prepare(second, "second")

        def checkout(args: tuple[TestClient, tuple[dict, dict]]) -> tuple[int, str | None]:
            client, (payload, headers) = args
            response = client.post("/api/v1/orders", json=payload, headers=headers)
            return response.status_code, response.json().get("error", {}).get("code")

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(
                executor.map(
                    checkout,
                    ((first, first_request), (second, second_request)),
                )
            )

    assert sorted(status_code for status_code, _ in outcomes) == [201, 409], outcomes
    assert {code for _, code in outcomes if code} == {"OUT_OF_STOCK"}

    async def persisted_state() -> tuple[int, int]:
        engine = create_async_engine(MIGRATION_DATABASE_URL)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            stock = await session.scalar(
                select(ProductVariant.stock_quantity).where(
                    ProductVariant.id == UUID(variant_id)
                )
            )
            reserves = await session.scalar(
                select(func.count()).select_from(InventoryMovement).where(
                    InventoryMovement.variant_id == UUID(variant_id),
                    InventoryMovement.movement_type == "order_reserve",
                )
            )
        await engine.dispose()
        return int(stock or 0), int(reserves or 0)

    assert asyncio.run(persisted_state()) == (0, 1)
    application.dependency_overrides.clear()
    asyncio.run(api_engine.dispose())
