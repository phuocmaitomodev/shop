from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.models.catalog import ProductVariant
from app.models.commerce import (
    Cart,
    CartItem,
    CouponRedemption,
    Order,
    PaymentAttempt,
    RefundRequest,
)
from app.rag.chat import (
    CartReadModel,
    CommerceOwnershipContext,
    OrderReadModel,
    PaymentDemoReadModel,
    RefundDemoReadModel,
)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


class DatabaseCommerceReadRepository:
    """Closed, read-only SQL tools for owner-scoped commerce chat intents."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_cart(
        self, context: CommerceOwnershipContext
    ) -> CartReadModel | None:
        statement = select(Cart).where(Cart.status == "active")
        if context.user_id is not None:
            statement = statement.where(Cart.user_id == context.user_id)
        elif context.guest_token_hash is not None:
            statement = statement.where(
                Cart.user_id.is_(None),
                Cart.guest_token_hash == context.guest_token_hash,
                Cart.guest_expires_at > datetime.now(timezone.utc),
            )
        else:
            return None
        result = await self._session.execute(
            statement.options(
                joinedload(Cart.coupon),
                joinedload(Cart.items)
                .joinedload(CartItem.variant)
                .joinedload(ProductVariant.product),
            ).execution_options(populate_existing=True)
        )
        cart = result.unique().scalar_one_or_none()
        if cart is None:
            return None

        subtotal = sum(
            (
                item.variant.product.sale_price
                if item.variant.product.sale_price is not None
                else item.variant.product.price
            )
            * item.quantity
            for item in cart.items
        )
        discount = await self._current_discount(context, cart, subtotal)
        settings = get_settings()
        shipping_fee = (
            0
            if subtotal == 0 or subtotal >= settings.free_shipping_threshold
            else settings.shipping_flat_fee
        )
        return CartReadModel(
            cart_id=cart.id,
            version=cart.version,
            item_count=sum(item.quantity for item in cart.items),
            subtotal=subtotal,
            discount_amount=discount,
            shipping_fee=shipping_fee,
            total=subtotal - discount + shipping_fee,
        )

    async def _current_discount(
        self, context: CommerceOwnershipContext, cart: Cart, subtotal: int
    ) -> int:
        coupon = cart.coupon
        now = datetime.now(timezone.utc)
        if (
            coupon is None
            or not coupon.is_active
            or subtotal < coupon.min_subtotal
            or (coupon.starts_at is not None and _as_utc(coupon.starts_at) > now)
            or (coupon.ends_at is not None and _as_utc(coupon.ends_at) <= now)
            or (
                coupon.usage_limit is not None
                and coupon.used_count >= coupon.usage_limit
            )
        ):
            return 0
        if coupon.per_user_limit is not None:
            ownership = (
                CouponRedemption.user_id == context.user_id
                if context.user_id is not None
                else CouponRedemption.guest_fingerprint == context.guest_token_hash
            )
            used = await self._session.scalar(
                select(func.count(CouponRedemption.id)).where(
                    CouponRedemption.coupon_id == coupon.id,
                    ownership,
                )
            )
            if int(used or 0) >= coupon.per_user_limit:
                return 0
        if coupon.discount_type == "fixed":
            discount = coupon.discount_value
        else:
            discount = subtotal * coupon.discount_value // 100
        if coupon.max_discount is not None:
            discount = min(discount, coupon.max_discount)
        return min(discount, subtotal)

    def _owned_order_statement(
        self, context: CommerceOwnershipContext, order_code: str
    ):
        statement = select(Order).where(Order.order_code == order_code)
        if context.user_id is not None:
            return statement.where(Order.user_id == context.user_id)
        if (
            context.order_lookup_token_hash is None
            or (
                context.order_code is not None
                and context.order_code.upper() != order_code.upper()
            )
        ):
            return None
        return statement.where(
            Order.user_id.is_(None),
            Order.guest_lookup_token_hash == context.order_lookup_token_hash,
            Order.guest_lookup_expires_at > datetime.now(timezone.utc),
        )

    async def get_order(
        self, context: CommerceOwnershipContext, order_code: str
    ) -> OrderReadModel | None:
        statement = self._owned_order_statement(context, order_code)
        if statement is None:
            return None
        order = await self._session.scalar(
            statement.execution_options(populate_existing=True)
        )
        if order is None:
            return None
        return OrderReadModel(
            order_code=order.order_code,
            status=order.status,
            total=order.total,
        )

    async def get_payment_demo_status(
        self, context: CommerceOwnershipContext, order_code: str
    ) -> PaymentDemoReadModel | None:
        statement = self._owned_order_statement(context, order_code)
        if statement is None:
            return None
        owned_order = statement.subquery()
        row = (
            await self._session.execute(
                select(PaymentAttempt, owned_order.c.order_code)
                .join(owned_order, owned_order.c.id == PaymentAttempt.order_id)
                .order_by(PaymentAttempt.created_at.desc(), PaymentAttempt.id.desc())
                .limit(1)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if row is None:
            return None
        payment, persisted_code = row
        return PaymentDemoReadModel(
            order_code=persisted_code,
            method=payment.method,
            status=payment.status,
            amount=payment.amount,
            provider=payment.provider,
        )

    async def get_refund_status(
        self, context: CommerceOwnershipContext, order_code: str
    ) -> RefundDemoReadModel | None:
        statement = self._owned_order_statement(context, order_code)
        if statement is None:
            return None
        owned_order = statement.subquery()
        row = (
            await self._session.execute(
                select(RefundRequest, owned_order.c.order_code)
                .join(owned_order, owned_order.c.id == RefundRequest.order_id)
                .order_by(RefundRequest.created_at.desc(), RefundRequest.id.desc())
                .limit(1)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if row is None:
            return None
        refund, persisted_code = row
        return RefundDemoReadModel(
            request_id=refund.id,
            order_code=persisted_code,
            status=refund.status,
            amount=refund.amount,
        )