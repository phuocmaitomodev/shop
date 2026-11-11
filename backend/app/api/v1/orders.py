import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.v1.cart import (
    CartOwner,
    _cart_response,
    _coupon_discount,
    _find_cart,
    _load_sellable_variant,
    _resolve_owner,
)
from app.commerce.identity import issue_confirmation_token
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import generate_token, hash_token
from app.db.session import get_db_session
from app.models.catalog import ProductImage, ProductVariant
from app.models.commerce import (
    ActionConfirmation,
    Cart,
    Coupon,
    CouponRedemption,
    IdempotencyRecord,
    InventoryMovement,
    Order,
    OrderItem,
    PaymentAttempt,
    RefundRequest,
)
from app.schemas.common import ErrorEnvelope
from app.schemas.orders import (
    ConfirmationCreateRequest,
    ConfirmationEnvelope,
    ConfirmationResponse,
    OrderCancelRequest,
    OrderCreateRequest,
    OrderEnvelope,
    OrderItemResponse,
    OrderConfirmationPayload,
    OrderResponse,
    PaymentEnvelope,
    PaymentResponse,
    RefundCreateRequest,
    RefundEnvelope,
    RefundResponse,
)

router = APIRouter(tags=["orders"])


async def _enforce_commerce_rate_limit(request: Request, scope: str) -> None:
    settings = get_settings()
    client_host = request.client.host if request.client is not None else "unknown"
    credential = (
        request.cookies.get(settings.auth_cookie_name)
        or request.headers.get("X-Order-Lookup-Token")
        or request.cookies.get(settings.guest_cookie_name)
    )
    owner_scope = hash_token(credential) if credential is not None else client_host
    limiter: InMemoryRateLimiter = request.app.state.commerce_rate_limiter
    allowed = await limiter.allow(
        f"{scope}:{owner_scope}",
        limit=settings.chat_rate_limit_requests,
        window_seconds=settings.chat_rate_limit_window_seconds,
        max_keys=settings.auth_rate_limit_max_keys,
    )
    if not allowed:
        raise AppError(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="RATE_LIMITED",
            message="Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau.",
        )


def _canonical_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized_confirmation_payload(action: str, payload: dict) -> dict:
    if action == "order_create":
        return OrderConfirmationPayload.model_validate(payload).model_dump(mode="json")
    placeholder = "confirmation-placeholder"
    if action == "order_cancel":
        return OrderCancelRequest.model_validate(
            {**payload, "confirmation_token": placeholder}
        ).model_dump(mode="json", exclude={"confirmation_token"})
    return RefundCreateRequest.model_validate(
        {**payload, "confirmation_token": placeholder}
    ).model_dump(mode="json", exclude={"confirmation_token"})


async def _order_confirmation_snapshot(
    session: AsyncSession, owner: CartOwner, cart: Cart
) -> dict:
    response = await _cart_response(session, owner, cart)
    return {
        "cart_id": str(cart.id),
        "cart_version": cart.version,
        "items": [
            {
                "variant_id": str(item.variant_id),
                "quantity": item.quantity,
                "unit_price": item.unit_price,
            }
            for item in sorted(response.items, key=lambda item: str(item.variant_id))
        ],
        "coupon_code": response.coupon_code,
        "subtotal": response.subtotal,
        "discount_amount": response.discount_amount,
        "shipping_fee": response.shipping_fee,
        "total": response.total,
        "currency": "VND",
    }


def _owner_guest_hash(owner: CartOwner) -> str | None:
    return hash_token(owner.guest_token) if owner.guest_token is not None else None


def _session_key(request: Request, owner: CartOwner) -> str:
    settings = get_settings()
    if owner.user_id is not None:
        token = request.cookies.get(settings.auth_cookie_name)
        if token is None:
            raise AppError(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="AUTH_REQUIRED",
                message="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
            )
        return f"user:{hash_token(token)}"
    if owner.guest_token is None:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="GUEST_SESSION_REQUIRED",
            message="Phiên khách không hợp lệ hoặc đã hết hạn.",
        )
    return f"guest:{hash_token(owner.guest_token)}"


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def _authorize_confirmation_resource(
    session: AsyncSession,
    owner: CartOwner,
    action: str,
    resource_key: str,
    *,
    allow_cart_token: bool,
) -> None:
    if action == "order_create":
        cart = await _find_cart(session, owner)
        if cart is None or str(cart.id) != resource_key or not cart.items:
            raise AppError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="CART_NOT_FOUND",
                message="Không tìm thấy giỏ hàng để xác nhận.",
            )
        return
    order = await _owned_order(
        session, owner, resource_key, allow_cart_token=allow_cart_token
    )
    if order is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ORDER_NOT_FOUND",
            message="Không tìm thấy đơn hàng.",
        )
    if action == "order_cancel" and order.status not in {
        "pending_confirmation",
        "confirmed",
    }:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="ORDER_STATUS_NOT_CANCELLABLE",
            message="Đơn hàng không còn ở trạng thái có thể hủy.",
        )
    if action == "refund_request" and (
        order.status != "completed"
        or order.payment_status not in {"paid_demo", "demo_approved"}
    ):
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="REFUND_NOT_ELIGIBLE",
            message="Đơn hàng chưa đủ điều kiện tạo yêu cầu hoàn tiền mô phỏng.",
        )


async def _owned_order(
    session: AsyncSession,
    owner: CartOwner,
    order_code: str,
    *,
    lock: bool = False,
    allow_cart_token: bool = True,
) -> Order | None:
    if owner.user_id is not None:
        statement = select(Order).where(
            Order.order_code == order_code, Order.user_id == owner.user_id
        )
        if lock:
            statement = statement.with_for_update(of=Order)
        result = await session.execute(statement.options(joinedload(Order.items)))
        return result.unique().scalar_one_or_none()
    if owner.guest_token is None:
        return None

    statement = (
        select(Order, Cart.guest_token_hash, Cart.guest_expires_at)
        .join(Cart, Cart.id == Order.cart_id)
        .where(Order.order_code == order_code, Order.user_id.is_(None))
    )
    if lock:
        statement = statement.with_for_update(of=Order)
    result = await session.execute(statement.options(joinedload(Order.items)))
    row = result.unique().one_or_none()
    if row is None:
        return None
    order, cart_token_hash, cart_expires_at = row
    now = datetime.now(timezone.utc)
    supplied_hash = hash_token(owner.guest_token)
    cart_matches = (
        allow_cart_token
        and _as_utc(cart_expires_at) > now
        and hmac.compare_digest(cart_token_hash, supplied_hash)
    )
    lookup_matches = (
        order.guest_lookup_token_hash is not None
        and order.guest_lookup_expires_at is not None
        and _as_utc(order.guest_lookup_expires_at) > now
        and hmac.compare_digest(order.guest_lookup_token_hash, supplied_hash)
    )
    return order if cart_matches or lookup_matches else None


async def _resolve_mutation_owner(
    request: Request, session: AsyncSession, *, allow_lookup: bool
) -> CartOwner:
    owner = await _resolve_owner(request, session)
    if owner.user_id is not None:
        return owner
    lookup_token = request.headers.get("X-Order-Lookup-Token") if allow_lookup else None
    if lookup_token is not None and 20 <= len(lookup_token) <= 200:
        return CartOwner(user_id=None, guest_token=lookup_token)
    return owner


@router.post(
    "/action-confirmations",
    response_model=ConfirmationEnvelope,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
        status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorEnvelope},
    },
)
async def create_action_confirmation(
    payload: ConfirmationCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await _enforce_commerce_rate_limit(request, "confirmation")
    owner = await _resolve_mutation_owner(
        request, session, allow_lookup=payload.action != "order_create"
    )
    await _authorize_confirmation_resource(
        session,
        owner,
        payload.action,
        payload.resource_key,
        allow_cart_token=request.headers.get("X-Order-Lookup-Token") is None,
    )
    confirmation_payload = _normalized_confirmation_payload(
        payload.action, payload.payload
    )
    if payload.action == "order_create":
        cart = await _find_cart(session, owner)
        if cart is None:
            raise RuntimeError("cart disappeared while issuing confirmation")
        confirmation_payload["server_snapshot"] = await _order_confirmation_snapshot(
            session, owner, cart
        )
    settings = get_settings()
    token = issue_confirmation_token(
        ttl_seconds=settings.action_confirmation_ttl_seconds
    )
    issued_at = token.expires_at - timedelta(
        seconds=settings.action_confirmation_ttl_seconds
    )
    session.add(
        ActionConfirmation(
            owner_user_id=owner.user_id,
            owner_guest_token_hash=_owner_guest_hash(owner),
            session_key=_session_key(request, owner),
            action=payload.action,
            resource_key=payload.resource_key,
            payload_json=confirmation_payload,
            payload_hash=_canonical_hash(confirmation_payload),
            token_hash=token.digest,
            expires_at=token.expires_at,
            created_at=issued_at,
            updated_at=issued_at,
        )
    )
    await session.commit()
    return {
        "data": ConfirmationResponse(
            confirmation_token=token.raw, expires_at=token.expires_at
        ),
        "meta": {"request_id": request.state.request_id},
    }


async def _consume_confirmation(
    session: AsyncSession,
    request: Request,
    owner: CartOwner,
    *,
    token: str,
    action: str,
    resource_key: str,
    payload: dict,
) -> None:
    confirmation = await session.scalar(
        select(ActionConfirmation)
        .where(ActionConfirmation.token_hash == hash_token(token))
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    valid = (
        confirmation is not None
        and confirmation.consumed_at is None
        and _as_utc(confirmation.expires_at) > now
        and confirmation.owner_user_id == owner.user_id
        and confirmation.owner_guest_token_hash == _owner_guest_hash(owner)
        and confirmation.session_key == _session_key(request, owner)
        and confirmation.action == action
        and confirmation.resource_key == resource_key
        and hmac.compare_digest(confirmation.payload_hash, _canonical_hash(payload))
    )
    if not valid:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="CONFIRMATION_INVALID",
            message="Xác nhận không hợp lệ, đã hết hạn hoặc đã được sử dụng.",
        )
    confirmation.consumed_at = now


async def _order_response(
    session: AsyncSession,
    order: Order,
    *,
    expose_guest_token: bool,
    issued_guest_token: str | None = None,
) -> OrderResponse:
    payment = await session.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.order_id == order.id)
        .order_by(PaymentAttempt.created_at.desc())
        .limit(1)
    )
    if payment is None:
        raise RuntimeError("order payment attempt is missing")
    return OrderResponse(
        id=order.id,
        order_code=order.order_code,
        status=order.status,
        recipient_name=order.recipient_name,
        phone=order.phone,
        address_line=order.address_line,
        ward=order.ward,
        district=order.district,
        province=order.province,
        note=order.note,
        subtotal=order.subtotal,
        discount_amount=order.discount_amount,
        shipping_fee=order.shipping_fee,
        total=order.total,
        items=[
            OrderItemResponse(
                product_id=item.product_id,
                variant_id=item.variant_id,
                product_name=item.product_name,
                product_sku=item.product_sku,
                variant_sku=item.variant_sku,
                color_name=item.color_name,
                size_code=item.size_code,
                image_url=item.image_url,
                unit_price=item.unit_price,
                quantity=item.quantity,
                line_total=item.line_total,
            )
            for item in sorted(order.items, key=lambda candidate: str(candidate.id))
        ],
        payment=PaymentResponse(
            method=payment.method,
            status=payment.status,
            amount=payment.amount,
        ),
        guest_lookup_token=(
            issued_guest_token if expose_guest_token and order.user_id is None else None
        ),
        created_at=order.created_at,
    )


async def _load_order(session: AsyncSession, order_id: UUID) -> Order:
    result = await session.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(joinedload(Order.items))
        .execution_options(populate_existing=True)
    )
    order = result.unique().scalar_one_or_none()
    if order is None:
        raise RuntimeError("order disappeared during transaction")
    return order


async def _idempotent_order_response(
    session: AsyncSession,
    response_body: dict,
    *,
    legacy_order_create: bool = False,
    legacy_order_cancel: bool = False,
) -> OrderResponse:
    snapshot = response_body.get("order")
    if snapshot is not None:
        return OrderResponse.model_validate(snapshot)
    order = await _load_order(session, UUID(response_body["order_id"]))
    response = await _order_response(session, order, expose_guest_token=False)
    if legacy_order_cancel:
        return response.model_copy(
            update={
                "status": "cancelled",
                "payment": response.payment.model_copy(
                    update={"status": "cancelled"}
                ),
            }
        )
    if not legacy_order_create:
        return response
    initial_payment_status = (
        "cod_due" if response.payment.method == "cod" else "demo_processing"
    )
    return response.model_copy(
        update={
            "status": "pending_confirmation",
            "payment": response.payment.model_copy(
                update={"status": initial_payment_status}
            ),
        }
    )


async def _existing_idempotency(
    session: AsyncSession,
    owner: CartOwner,
    *,
    operation: str,
    resource_key: str,
    key_hash: str,
) -> IdempotencyRecord | None:
    statement = (
        select(IdempotencyRecord)
        .where(
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.resource_key == resource_key,
            IdempotencyRecord.key_hash == key_hash,
        )
        .with_for_update()
    )
    if owner.user_id is not None:
        statement = statement.where(IdempotencyRecord.owner_user_id == owner.user_id)
    else:
        statement = statement.where(
            IdempotencyRecord.owner_guest_token_hash == _owner_guest_hash(owner)
        )
    record = await session.scalar(statement)
    if record is not None and _as_utc(record.expires_at) <= datetime.now(timezone.utc):
        await session.delete(record)
        await session.flush()
        return None
    return record


@router.post(
    "/orders",
    response_model=OrderEnvelope,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
        status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
        status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorEnvelope},
    },
)
async def create_order(
    payload: OrderCreateRequest,
    request: Request,
    idempotency_key: str = Header(min_length=8, max_length=200, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await _enforce_commerce_rate_limit(request, "order-create")
    owner = await _resolve_owner(request, session)
    if owner.user_id is None and owner.guest_token is None:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="GUEST_SESSION_REQUIRED",
            message="Phiên khách không hợp lệ hoặc đã hết hạn.",
        )
    if owner.user_id is None:
        owned_cart_id = await session.scalar(
            select(Cart.id).where(
                Cart.id == payload.cart_id,
                Cart.guest_token_hash == _owner_guest_hash(owner),
                Cart.guest_expires_at > datetime.now(timezone.utc),
            )
        )
        if owned_cart_id is None:
            raise AppError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="CART_NOT_FOUND",
                message="Không tìm thấy giỏ hàng để đặt hàng.",
            )
    request_payload = payload.model_dump(mode="json", exclude={"confirmation_token"})
    request_hash = _canonical_hash(request_payload)
    key_hash = hash_token(idempotency_key)
    resource_key = str(payload.cart_id)
    existing = await _existing_idempotency(
        session,
        owner,
        operation="order_create",
        resource_key=resource_key,
        key_hash=key_hash,
    )
    if existing is not None:
        if not hmac.compare_digest(existing.request_hash, request_hash):
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="IDEMPOTENCY_KEY_REUSED",
                message="Idempotency-Key đã được dùng cho dữ liệu khác.",
            )
        if existing.status == "completed" and existing.response_body:
            return {
                "data": await _idempotent_order_response(
                    session,
                    existing.response_body,
                    legacy_order_create=True,
                ),
                "meta": {"request_id": request.state.request_id},
            }

    cart = await _find_cart(session, owner, lock=True)
    if cart is None:
        existing = await _existing_idempotency(
            session,
            owner,
            operation="order_create",
            resource_key=resource_key,
            key_hash=key_hash,
        )
        if (
            existing is not None
            and hmac.compare_digest(existing.request_hash, request_hash)
            and existing.status == "completed"
            and existing.response_body
        ):
            return {
                "data": await _idempotent_order_response(
                    session,
                    existing.response_body,
                    legacy_order_create=True,
                ),
                "meta": {"request_id": request.state.request_id},
            }
    if cart is None or cart.id != payload.cart_id or not cart.items:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="CART_NOT_FOUND",
            message="Không tìm thấy giỏ hàng để đặt hàng.",
        )
    if cart.version != payload.cart_version:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="CART_VERSION_CONFLICT",
            message="Giỏ hàng đã thay đổi. Vui lòng kiểm tra lại.",
        )
    variants = []
    subtotal = 0
    for item in sorted(cart.items, key=lambda candidate: str(candidate.variant_id)):
        variant = await _load_sellable_variant(session, item.variant_id)
        current_price = (
            variant.product.sale_price
            if variant.product.sale_price is not None
            else variant.product.price
        )
        if current_price != item.unit_price:
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="PRICE_CHANGED",
                message="Giá sản phẩm đã thay đổi. Vui lòng kiểm tra lại giỏ hàng.",
            )
        if item.quantity > variant.stock_quantity:
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="OUT_OF_STOCK",
                message="Sản phẩm không đủ tồn kho.",
            )
        variants.append((item, variant, current_price))
        subtotal += current_price * item.quantity

    if cart.coupon_id is not None:
        coupon = await session.scalar(
            select(Coupon)
            .where(Coupon.id == cart.coupon_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if coupon is None:
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="COUPON_INVALID",
                message="Mã giảm giá không còn hợp lệ.",
            )
        cart.coupon = coupon
    discount = await _coupon_discount(session, owner, cart.coupon, subtotal)
    if cart.coupon is not None and discount == 0:
        now = datetime.now(timezone.utc)
        starts_at = (
            _as_utc(cart.coupon.starts_at) if cart.coupon.starts_at is not None else None
        )
        ends_at = (
            _as_utc(cart.coupon.ends_at) if cart.coupon.ends_at is not None else None
        )
        if (starts_at is not None and starts_at > now) or (
            ends_at is not None and ends_at <= now
        ):
            code = "COUPON_EXPIRED"
            message = "Mã giảm giá chưa có hiệu lực hoặc đã hết hạn."
        elif not cart.coupon.is_active:
            code = "COUPON_INVALID"
            message = "Mã giảm giá không còn hợp lệ."
        else:
            code = "COUPON_NOT_APPLICABLE"
            message = "Mã giảm giá không còn đủ điều kiện áp dụng."
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code=code,
            message=message,
        )
    settings = get_settings()
    shipping_fee = (
        0
        if subtotal == 0 or subtotal >= settings.free_shipping_threshold
        else settings.shipping_flat_fee
    )
    total = subtotal - discount + shipping_fee
    confirmation_payload = dict(request_payload)
    confirmation_payload["server_snapshot"] = {
        "cart_id": str(cart.id),
        "cart_version": cart.version,
        "items": [
            {
                "variant_id": str(variant.id),
                "quantity": item.quantity,
                "unit_price": unit_price,
            }
            for item, variant, unit_price in variants
        ],
        "coupon_code": cart.coupon.code if cart.coupon is not None else None,
        "subtotal": subtotal,
        "discount_amount": discount,
        "shipping_fee": shipping_fee,
        "total": total,
        "currency": "VND",
    }
    await _consume_confirmation(
        session,
        request,
        owner,
        token=payload.confirmation_token,
        action="order_create",
        resource_key=resource_key,
        payload=confirmation_payload,
    )
    order_id = uuid4()
    lookup_token = generate_token() if owner.user_id is None else None
    payment_status = "cod_due" if payload.payment_method == "cod" else "demo_processing"
    order = Order(
        id=order_id,
        order_code=f"DH-{order_id.hex[:12].upper()}",
        user_id=owner.user_id,
        cart_id=cart.id,
        coupon_id=cart.coupon_id,
        guest_lookup_token_hash=hash_token(lookup_token) if lookup_token else None,
        guest_lookup_expires_at=(
            datetime.now(timezone.utc) + timedelta(days=settings.guest_token_ttl_days)
            if lookup_token
            else None
        ),
        recipient_name=payload.recipient_name,
        phone=payload.phone,
        address_line=payload.address_line,
        ward=payload.ward,
        district=payload.district,
        province=payload.province,
        note=payload.note,
        status="pending_confirmation",
        payment_method=payload.payment_method,
        payment_status=payment_status,
        subtotal=subtotal,
        discount_amount=discount,
        shipping_fee=shipping_fee,
        total=total,
        items=[],
    )
    session.add(order)
    await session.flush()
    for cart_item, variant, unit_price in variants:
        image_url = await session.scalar(
            select(ProductImage.file_path)
            .where(
                ProductImage.product_id == variant.product.id,
                ProductImage.is_primary.is_(True),
            )
            .limit(1)
        )
        order.items.append(
            OrderItem(
                product_id=variant.product.id,
                variant_id=variant.id,
                product_name=variant.product.name,
                product_sku=variant.product.sku,
                variant_sku=variant.variant_sku,
                color_name=variant.color.name,
                size_code=variant.size.code,
                image_url=image_url,
                unit_price=unit_price,
                quantity=cart_item.quantity,
                line_total=unit_price * cart_item.quantity,
            )
        )
        variant.stock_quantity -= cart_item.quantity
        variant.version += 1
        session.add(
            InventoryMovement(
                variant_id=variant.id,
                order_id=order.id,
                movement_type="order_reserve",
                quantity_delta=-cart_item.quantity,
                stock_after=variant.stock_quantity,
                reason="Đặt hàng",
            )
        )
    session.add(
        PaymentAttempt(
            order_id=order.id,
            method=payload.payment_method,
            status=payment_status,
            amount=total,
            provider="demo",
            idempotency_key_hash=key_hash,
        )
    )
    if cart.coupon is not None and discount > 0:
        cart.coupon.used_count += 1
        session.add(
            CouponRedemption(
                coupon_id=cart.coupon.id,
                order_id=order.id,
                user_id=owner.user_id,
                guest_fingerprint=_owner_guest_hash(owner),
                discount_amount=discount,
            )
        )
    cart.status = "converted"
    await session.flush()
    order = await _load_order(session, order.id)
    initial_response = await _order_response(
        session,
        order,
        expose_guest_token=True,
        issued_guest_token=lookup_token,
    )
    replay_response = initial_response.model_copy(update={"guest_lookup_token": None})
    record = IdempotencyRecord(
        owner_user_id=owner.user_id,
        owner_guest_token_hash=_owner_guest_hash(owner),
        operation="order_create",
        resource_key=resource_key,
        key_hash=key_hash,
        request_hash=request_hash,
        status="completed",
        response_body={"order": replay_response.model_dump(mode="json")},
        response_status=status.HTTP_201_CREATED,
        expires_at=datetime.now(timezone.utc)
        + timedelta(hours=settings.idempotency_ttl_hours),
    )
    session.add(record)
    await session.commit()
    return {
        "data": initial_response,
        "meta": {"request_id": request.state.request_id},
    }


@router.get(
    "/orders/lookup",
    response_model=OrderEnvelope,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorEnvelope},
    },
)
async def lookup_guest_order(
    order_code: str,
    request: Request,
    lookup_token: str = Header(
        min_length=20, max_length=200, alias="X-Order-Lookup-Token"
    ),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await _enforce_commerce_rate_limit(request, "order-lookup")
    order = await _owned_order(
        session,
        CartOwner(user_id=None, guest_token=lookup_token),
        order_code,
        allow_cart_token=False,
    )
    if order is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ORDER_NOT_FOUND",
            message="Không tìm thấy đơn hàng.",
        )
    return {
        "data": await _order_response(session, order, expose_guest_token=False),
        "meta": {"request_id": request.state.request_id},
    }


async def _read_owned_order(
    session: AsyncSession,
    request: Request,
    order_code: str,
    lookup_token: str | None,
) -> Order:
    owner = await _resolve_owner(request, session)
    if owner.user_id is not None:
        order = await _owned_order(session, owner, order_code)
    elif lookup_token is not None:
        order = await _owned_order(
            session,
            CartOwner(user_id=None, guest_token=lookup_token),
            order_code,
            allow_cart_token=False,
        )
    else:
        order = None
    if order is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ORDER_NOT_FOUND",
            message="Không tìm thấy đơn hàng.",
        )
    return order


@router.get(
    "/orders/{order_code}/payment",
    response_model=PaymentEnvelope,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope}},
)
async def get_order_payment(
    order_code: str,
    request: Request,
    lookup_token: str | None = Header(
        default=None, min_length=20, max_length=200, alias="X-Order-Lookup-Token"
    ),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    order = await _read_owned_order(session, request, order_code, lookup_token)
    payment = await session.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.order_id == order.id)
        .order_by(PaymentAttempt.created_at.desc())
        .limit(1)
    )
    if payment is None:
        raise RuntimeError("order payment attempt is missing")
    return {
        "data": PaymentResponse(
            method=payment.method,
            status=payment.status,
            amount=payment.amount,
        ),
        "meta": {"request_id": request.state.request_id},
    }


@router.post(
    "/orders/{order_code}/cancel",
    response_model=OrderEnvelope,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
        status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
        status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorEnvelope},
    },
)
async def cancel_order(
    order_code: str,
    payload: OrderCancelRequest,
    request: Request,
    idempotency_key: str = Header(min_length=8, max_length=200, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await _enforce_commerce_rate_limit(request, "order-cancel")
    owner = await _resolve_mutation_owner(request, session, allow_lookup=True)
    allow_cart_token = request.headers.get("X-Order-Lookup-Token") is None
    if await _owned_order(
        session, owner, order_code, allow_cart_token=allow_cart_token
    ) is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ORDER_NOT_FOUND",
            message="Không tìm thấy đơn hàng.",
        )
    request_payload = payload.model_dump(mode="json", exclude={"confirmation_token"})
    request_hash = _canonical_hash(request_payload)
    key_hash = hash_token(idempotency_key)
    existing = await _existing_idempotency(
        session,
        owner,
        operation="order_cancel",
        resource_key=order_code,
        key_hash=key_hash,
    )
    if existing is not None:
        if not hmac.compare_digest(existing.request_hash, request_hash):
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="IDEMPOTENCY_KEY_REUSED",
                message="Idempotency-Key đã được dùng cho dữ liệu khác.",
            )
        if existing.status == "completed" and existing.response_body:
            return {
                "data": await _idempotent_order_response(
                    session,
                    existing.response_body,
                    legacy_order_cancel=True,
                ),
                "meta": {"request_id": request.state.request_id},
            }

    order = await _owned_order(
        session,
        owner,
        order_code,
        lock=True,
        allow_cart_token=allow_cart_token,
    )
    if order is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ORDER_NOT_FOUND",
            message="Không tìm thấy đơn hàng.",
        )
    existing = await _existing_idempotency(
        session,
        owner,
        operation="order_cancel",
        resource_key=order_code,
        key_hash=key_hash,
    )
    if existing is not None:
        if not hmac.compare_digest(existing.request_hash, request_hash):
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="IDEMPOTENCY_KEY_REUSED",
                message="Idempotency-Key đã được dùng cho dữ liệu khác.",
            )
        if existing.status == "completed" and existing.response_body:
            return {
                "data": await _idempotent_order_response(
                    session,
                    existing.response_body,
                    legacy_order_cancel=True,
                ),
                "meta": {"request_id": request.state.request_id},
            }
    if order.status not in {"pending_confirmation", "confirmed"}:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="ORDER_STATUS_NOT_CANCELLABLE",
            message="Đơn hàng không còn ở trạng thái có thể hủy.",
        )
    await _consume_confirmation(
        session,
        request,
        owner,
        token=payload.confirmation_token,
        action="order_cancel",
        resource_key=order_code,
        payload=request_payload,
    )
    for item in sorted(order.items, key=lambda candidate: str(candidate.variant_id)):
        if item.variant_id is None:
            continue
        variant = await session.scalar(
            select(ProductVariant)
            .where(ProductVariant.id == item.variant_id)
            .with_for_update()
        )
        if variant is None:
            raise RuntimeError("order variant disappeared before cancellation")
        variant.stock_quantity += item.quantity
        variant.version += 1
        session.add(
            InventoryMovement(
                variant_id=variant.id,
                order_id=order.id,
                movement_type="order_cancel_restore",
                quantity_delta=item.quantity,
                stock_after=variant.stock_quantity,
                reason=payload.reason or "Khách hủy đơn",
            )
        )
    order.status = "cancelled"
    order.payment_status = "cancelled"
    order.cancelled_at = datetime.now(timezone.utc)
    order.cancel_reason = payload.reason
    payment = await session.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.order_id == order.id)
        .with_for_update()
    )
    if payment is not None:
        payment.status = "cancelled"
    await session.flush()
    order_response = await _order_response(session, order, expose_guest_token=False)
    settings = get_settings()
    session.add(
        IdempotencyRecord(
            owner_user_id=owner.user_id,
            owner_guest_token_hash=_owner_guest_hash(owner),
            operation="order_cancel",
            resource_key=order_code,
            key_hash=key_hash,
            request_hash=request_hash,
            status="completed",
            response_body={"order": order_response.model_dump(mode="json")},
            response_status=status.HTTP_200_OK,
            expires_at=datetime.now(timezone.utc)
            + timedelta(hours=settings.idempotency_ttl_hours),
        )
    )
    await session.commit()
    return {
        "data": order_response,
        "meta": {"request_id": request.state.request_id},
    }


def _refund_response(refund: RefundRequest, order_code: str) -> RefundResponse:
    return RefundResponse(
        id=refund.id,
        order_code=order_code,
        reason_code=refund.reason_code,
        reason_detail=refund.reason_detail,
        amount=refund.amount,
        status=refund.status,
        created_at=refund.created_at,
    )


async def _idempotent_refund_response(
    session: AsyncSession, response_body: dict, order_code: str
) -> RefundResponse:
    snapshot = response_body.get("refund")
    if snapshot is not None:
        return RefundResponse.model_validate(snapshot)
    refund = await session.get(RefundRequest, UUID(response_body["refund_id"]))
    if refund is None:
        raise RuntimeError("refund request disappeared")
    return _refund_response(refund, order_code).model_copy(
        update={"status": "requested"}
    )


@router.post(
    "/orders/{order_code}/refund-requests",
    response_model=RefundEnvelope,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
        status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorEnvelope},
    },
)
async def create_refund_request(
    order_code: str,
    payload: RefundCreateRequest,
    request: Request,
    idempotency_key: str = Header(min_length=8, max_length=200, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await _enforce_commerce_rate_limit(request, "refund-create")
    owner = await _resolve_mutation_owner(request, session, allow_lookup=True)
    allow_cart_token = request.headers.get("X-Order-Lookup-Token") is None
    if await _owned_order(
        session, owner, order_code, allow_cart_token=allow_cart_token
    ) is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ORDER_NOT_FOUND",
            message="Không tìm thấy đơn hàng.",
        )
    request_payload = payload.model_dump(mode="json", exclude={"confirmation_token"})
    request_hash = _canonical_hash(request_payload)
    key_hash = hash_token(idempotency_key)
    existing = await _existing_idempotency(
        session, owner, operation="refund_request", resource_key=order_code, key_hash=key_hash
    )
    if existing is not None:
        if not hmac.compare_digest(existing.request_hash, request_hash):
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="IDEMPOTENCY_KEY_REUSED",
                message="Idempotency-Key đã được dùng cho dữ liệu khác.",
            )
        if existing.status == "completed" and existing.response_body:
            return {
                "data": await _idempotent_refund_response(
                    session, existing.response_body, order_code
                ),
                "meta": {"request_id": request.state.request_id},
            }

    order = await _owned_order(
        session,
        owner,
        order_code,
        lock=True,
        allow_cart_token=allow_cart_token,
    )
    if order is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ORDER_NOT_FOUND",
            message="Không tìm thấy đơn hàng.",
        )
    existing = await _existing_idempotency(
        session,
        owner,
        operation="refund_request",
        resource_key=order_code,
        key_hash=key_hash,
    )
    if existing is not None:
        if not hmac.compare_digest(existing.request_hash, request_hash):
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="IDEMPOTENCY_KEY_REUSED",
                message="Idempotency-Key đã được dùng cho dữ liệu khác.",
            )
        if existing.status == "completed" and existing.response_body:
            return {
                "data": await _idempotent_refund_response(
                    session, existing.response_body, order_code
                ),
                "meta": {"request_id": request.state.request_id},
            }
    if order.status != "completed" or order.payment_status not in {"paid_demo", "demo_approved"}:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="REFUND_NOT_ELIGIBLE",
            message="Đơn hàng chưa đủ điều kiện tạo yêu cầu hoàn tiền mô phỏng.",
        )
    active_refund = await session.scalar(
        select(RefundRequest).where(
            RefundRequest.order_id == order.id,
            RefundRequest.status.not_in(("demo_rejected", "cancelled", "demo_refunded")),
        )
    )
    if active_refund is not None:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="REFUND_REQUEST_EXISTS",
            message="Đơn hàng đã có yêu cầu hoàn tiền đang xử lý.",
        )
    await _consume_confirmation(
        session,
        request,
        owner,
        token=payload.confirmation_token,
        action="refund_request",
        resource_key=order_code,
        payload=request_payload,
    )
    refund = RefundRequest(
        order_id=order.id,
        requester_user_id=owner.user_id,
        requester_guest_token_hash=_owner_guest_hash(owner),
        reason_code=payload.reason_code,
        reason_detail=payload.reason_detail,
        amount=order.total,
        status="requested",
    )
    session.add(refund)
    await session.flush()
    refund_response = _refund_response(refund, order_code)
    settings = get_settings()
    session.add(
        IdempotencyRecord(
            owner_user_id=owner.user_id,
            owner_guest_token_hash=_owner_guest_hash(owner),
            operation="refund_request",
            resource_key=order_code,
            key_hash=key_hash,
            request_hash=request_hash,
            status="completed",
            response_body={"refund": refund_response.model_dump(mode="json")},
            response_status=status.HTTP_201_CREATED,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.idempotency_ttl_hours),
        )
    )
    await session.commit()
    return {
        "data": refund_response,
        "meta": {"request_id": request.state.request_id},
    }


@router.get(
    "/orders/{order_code}/refund-requests/latest",
    response_model=RefundEnvelope,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope}},
)
async def get_latest_refund_request(
    order_code: str,
    request: Request,
    lookup_token: str | None = Header(
        default=None, min_length=20, max_length=200, alias="X-Order-Lookup-Token"
    ),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    order = await _read_owned_order(session, request, order_code, lookup_token)
    refund = await session.scalar(
        select(RefundRequest)
        .where(RefundRequest.order_id == order.id)
        .order_by(RefundRequest.created_at.desc())
        .limit(1)
    )
    if refund is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="REFUND_REQUEST_NOT_FOUND",
            message="Chưa có yêu cầu hoàn tiền cho đơn hàng.",
        )
    return {
        "data": _refund_response(refund, order_code),
        "meta": {"request_id": request.state.request_id},
    }


@router.get(
    "/orders/{order_code}",
    response_model=OrderEnvelope,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope}},
)
async def get_order_detail(
    order_code: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    order = await _read_owned_order(session, request, order_code, lookup_token=None)
    return {
        "data": await _order_response(session, order, expose_guest_token=False),
        "meta": {"request_id": request.state.request_id},
    }
