import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.auth import User
from app.models.catalog import Category, Color, Product, ProductVariant, Size
from app.models.commerce import Cart, CartItem, Order, PaymentAttempt, RefundRequest
from app.rag.chat import CommerceOwnershipContext
from app.rag.commerce_reads import DatabaseCommerceReadRepository
from tests.integration.database_guard import require_fresh_migrated_database


DATABASE_URL = os.getenv("MIGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="MIGRATION_DATABASE_URL is required for PostgreSQL chat read-tool tests",
)


def test_postgres_chat_read_tools_enforce_ownership_and_refresh_live_facts() -> None:
    assert DATABASE_URL is not None
    require_fresh_migrated_database(DATABASE_URL)

    async def exercise() -> None:
        engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        owner_id = uuid4()
        intruder_id = uuid4()
        order_id = uuid4()
        lookup_hash = uuid4().hex + uuid4().hex
        suffix = uuid4().hex
        async with session_factory() as session:
            owner = User(
                id=owner_id,
                email=f"chat-read-owner-{suffix}@example.com",
                password_hash="test-hash",
                full_name="Chat read owner",
                role="customer",
            )
            intruder = User(
                id=intruder_id,
                email=f"chat-read-intruder-{suffix}@example.com",
                password_hash="test-hash",
                full_name="Chat read intruder",
                role="customer",
            )
            category = Category(name="Chat read PG", slug=f"chat-read-{suffix}")
            color = Color(name="Đen PG", slug=f"chat-read-black-{suffix}")
            size = Size(code=f"CR-{suffix[:8]}", name="Chat read PG")
            product = Product(
                category=category,
                sku=f"CHAT-READ-{suffix}",
                slug=f"chat-read-product-{suffix}",
                name="Sản phẩm chat read PostgreSQL",
                price=500_000,
                sale_price=450_000,
            )
            variant = ProductVariant(
                product=product,
                color=color,
                size=size,
                variant_sku=f"CHAT-READ-VARIANT-{suffix}",
                stock_quantity=5,
            )
            cart = Cart(user_id=owner_id, version=2, items=[])
            cart.items.append(
                CartItem(variant=variant, quantity=2, unit_price=500_000)
            )
            order = Order(
                id=order_id,
                order_code=f"DH-{suffix[:12].upper()}",
                guest_lookup_token_hash=lookup_hash,
                guest_lookup_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                recipient_name="Khách PostgreSQL",
                phone="0901234567",
                address_line="1 Đường PostgreSQL",
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
                    PaymentAttempt(
                        order_id=order_id,
                        method="online_demo",
                        status="demo_approved",
                        amount=900_000,
                        provider="demo",
                        idempotency_key_hash=uuid4().hex,
                    ),
                    RefundRequest(
                        order_id=order_id,
                        requester_guest_token_hash=lookup_hash,
                        reason_code="manufacturer_fault",
                        amount=900_000,
                        status="demo_reviewing",
                    ),
                ]
            )
            await session.commit()
            product_id = product.id

        async with session_factory() as reader:
            repository = DatabaseCommerceReadRepository(reader)
            owner_context = CommerceOwnershipContext(user_id=owner_id)
            guest_context = CommerceOwnershipContext(
                order_lookup_token_hash=lookup_hash
            )
            intruder_context = CommerceOwnershipContext(user_id=intruder_id)

            initial_cart = await repository.get_cart(owner_context)
            initial_order = await repository.get_order(guest_context, order.order_code)
            assert initial_cart is not None and initial_cart.subtotal == 900_000
            assert initial_order is not None and initial_order.total == 900_000
            assert await repository.get_cart(intruder_context) is None
            assert await repository.get_order(intruder_context, order.order_code) is None

            async with session_factory() as writer:
                await writer.execute(
                    update(Product).where(Product.id == product_id).values(sale_price=400_000)
                )
                await writer.execute(
                    update(Order)
                    .where(Order.id == order_id)
                    .values(subtotal=800_000, total=800_000)
                )
                await writer.execute(
                    update(PaymentAttempt)
                    .where(PaymentAttempt.order_id == order_id)
                    .values(amount=800_000, status="paid_demo")
                )
                await writer.execute(
                    update(RefundRequest)
                    .where(RefundRequest.order_id == order_id)
                    .values(amount=800_000, status="demo_refunded")
                )
                await writer.commit()

            await reader.rollback()
            refreshed_cart = await repository.get_cart(owner_context)
            refreshed_order = await repository.get_order(guest_context, order.order_code)
            refreshed_payment = await repository.get_payment_demo_status(
                guest_context, order.order_code
            )
            refreshed_refund = await repository.get_refund_status(
                guest_context, order.order_code
            )
            assert refreshed_cart is not None and refreshed_cart.subtotal == 800_000
            assert refreshed_order is not None and refreshed_order.total == 800_000
            assert refreshed_payment is not None and refreshed_payment.amount == 800_000
            assert refreshed_payment.status == "paid_demo"
            assert refreshed_refund is not None and refreshed_refund.amount == 800_000
            assert refreshed_refund.status == "demo_refunded"

        await engine.dispose()

    asyncio.run(exercise())
