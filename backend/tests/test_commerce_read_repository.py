import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.auth import User
from app.models.catalog import Category, Color, Product, ProductVariant, Size
from app.models.commerce import Cart, CartItem, Order, PaymentAttempt, RefundRequest
from app.rag.chat import CommerceOwnershipContext
from app.rag.commerce_reads import DatabaseCommerceReadRepository


def test_database_commerce_reads_enforce_owner_and_hydrate_current_sql(
    auth_session_factory,
) -> None:
    async def exercise() -> None:
        owner_id = uuid4()
        intruder_id = uuid4()
        order_id = uuid4()
        owner = User(
            id=owner_id,
            email="read-owner@example.com",
            password_hash="test-hash",
            full_name="Read Owner",
            role="customer",
        )
        intruder = User(
            id=intruder_id,
            email="read-intruder@example.com",
            password_hash="test-hash",
            full_name="Read Intruder",
            role="customer",
        )
        category = Category(name="Read category", slug=f"read-{uuid4().hex}")
        color = Color(name="Đen", slug=f"read-black-{uuid4().hex}")
        size = Size(code=f"R-{uuid4().hex[:6]}", name="Read size")
        product = Product(
            category=category,
            sku=f"READ-{uuid4().hex}",
            slug=f"read-product-{uuid4().hex}",
            name="Sản phẩm đọc",
            price=500_000,
            sale_price=450_000,
        )
        variant = ProductVariant(
            product=product,
            color=color,
            size=size,
            variant_sku=f"READ-VARIANT-{uuid4().hex}",
            stock_quantity=4,
        )
        cart = Cart(user_id=owner_id, version=2, items=[])
        cart.items.append(
            CartItem(variant=variant, quantity=2, unit_price=500_000)
        )
        order = Order(
            id=order_id,
            order_code=f"DH-{uuid4().hex[:12].upper()}",
            user_id=owner_id,
            recipient_name="Khách đọc",
            phone="0901234567",
            address_line="1 Đường SQL",
            province="TP. Hồ Chí Minh",
            status="completed",
            payment_method="online_demo",
            payment_status="demo_approved",
            subtotal=900_000,
            discount_amount=0,
            shipping_fee=0,
            total=900_000,
            items=[],
        )
        payment = PaymentAttempt(
            order_id=order_id,
            method="online_demo",
            status="demo_approved",
            amount=900_000,
            provider="demo",
            idempotency_key_hash="a" * 64,
        )
        refund = RefundRequest(
            order_id=order_id,
            requester_user_id=owner_id,
            reason_code="manufacturer_fault",
            amount=900_000,
            status="demo_reviewing",
        )

        async with auth_session_factory() as session:
            session.add_all(
                [
                    owner,
                    intruder,
                    category,
                    color,
                    size,
                    product,
                    variant,
                    cart,
                    order,
                    payment,
                    refund,
                ]
            )
            await session.commit()

        async with auth_session_factory() as session:
            repository = DatabaseCommerceReadRepository(session)
            owner_context = CommerceOwnershipContext(user_id=owner_id)
            intruder_context = CommerceOwnershipContext(user_id=intruder_id)

            cart_read = await repository.get_cart(owner_context)
            assert cart_read is not None
            assert cart_read.version == 2
            assert cart_read.item_count == 2
            assert cart_read.subtotal == 900_000
            assert cart_read.total == 900_000

            order_read = await repository.get_order(owner_context, order.order_code)
            payment_read = await repository.get_payment_demo_status(
                owner_context, order.order_code
            )
            refund_read = await repository.get_refund_status(
                owner_context, order.order_code
            )
            assert order_read is not None and order_read.total == 900_000
            assert payment_read is not None and payment_read.amount == 900_000
            assert refund_read is not None and refund_read.amount == 900_000

            assert await repository.get_cart(intruder_context) is None
            assert await repository.get_order(intruder_context, order.order_code) is None
            assert (
                await repository.get_payment_demo_status(
                    intruder_context, order.order_code
                )
                is None
            )
            assert (
                await repository.get_refund_status(intruder_context, order.order_code)
                is None
            )

    asyncio.run(exercise())


def test_database_commerce_reads_require_current_guest_credentials(
    auth_session_factory,
) -> None:
    async def exercise() -> None:
        active_hash = "a" * 64
        expired_hash = "b" * 64
        lookup_hash = "c" * 64
        category = Category(name="Guest read", slug=f"guest-read-{uuid4().hex}")
        color = Color(name="Trắng", slug=f"guest-white-{uuid4().hex}")
        size = Size(code=f"G-{uuid4().hex[:6]}", name="Guest size")
        product = Product(
            category=category,
            sku=f"GUEST-READ-{uuid4().hex}",
            slug=f"guest-read-product-{uuid4().hex}",
            name="Sản phẩm khách",
            price=250_000,
        )
        variant = ProductVariant(
            product=product,
            color=color,
            size=size,
            variant_sku=f"GUEST-READ-VARIANT-{uuid4().hex}",
            stock_quantity=1,
        )
        active_cart = Cart(
            guest_token_hash=active_hash,
            guest_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            items=[],
        )
        active_cart.items.append(
            CartItem(variant=variant, quantity=1, unit_price=250_000)
        )
        expired_cart = Cart(
            guest_token_hash=expired_hash,
            guest_expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            items=[],
        )
        order = Order(
            order_code=f"DH-{uuid4().hex[:12].upper()}",
            guest_lookup_token_hash=lookup_hash,
            guest_lookup_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            recipient_name="Khách lookup",
            phone="0901234567",
            address_line="2 Đường SQL",
            province="Hà Nội",
            status="confirmed",
            payment_method="cod",
            payment_status="cod_due",
            subtotal=250_000,
            discount_amount=0,
            shipping_fee=30_000,
            total=280_000,
            items=[],
        )
        async with auth_session_factory() as session:
            session.add_all(
                [
                    category,
                    color,
                    size,
                    product,
                    variant,
                    active_cart,
                    expired_cart,
                    order,
                ]
            )
            await session.commit()

        async with auth_session_factory() as session:
            repository = DatabaseCommerceReadRepository(session)
            guest = CommerceOwnershipContext(
                guest_token_hash=active_hash,
                order_lookup_token_hash=lookup_hash,
            )
            assert await repository.get_cart(guest) is not None
            assert await repository.get_order(guest, order.order_code) is not None

            expired = CommerceOwnershipContext(guest_token_hash=expired_hash)
            assert await repository.get_cart(expired) is None

            wrong_lookup = CommerceOwnershipContext(
                order_lookup_token_hash="d" * 64
            )
            assert await repository.get_order(wrong_lookup, order.order_code) is None

    asyncio.run(exercise())
