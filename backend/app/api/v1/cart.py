import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, joinedload

from app.commerce.identity import issue_guest_token, set_guest_cookie
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import hash_token
from app.db.session import get_db_session
from app.models.auth import AuthSession, User
from app.models.catalog import Category, Color, Product, ProductVariant, Size
from app.models.commerce import Cart, CartItem, Coupon, CouponRedemption
from app.schemas.cart import (
    CartEnvelope,
    CartCouponRequest,
    CartCouponRemoveRequest,
    CartItemCreateRequest,
    CartItemDeleteRequest,
    CartItemResponse,
    CartItemUpdateRequest,
    CartResponse,
)
from app.schemas.common import ErrorEnvelope

router = APIRouter(prefix="/cart", tags=["cart"])


@dataclass
class CartOwner:
    user_id: UUID | None
    guest_token: str | None


def _bootstrap_cart_id(owner: CartOwner, *, generation: int = 0) -> UUID | None:
    if owner.user_id is not None:
        owner_key = f"user:{owner.user_id}"
    elif owner.guest_token is not None:
        owner_key = f"guest:{owner.guest_token}"
    else:
        return None
    secret = get_settings().app_secret_key.get_secret_value().encode("utf-8")
    digest = hmac.new(
        secret,
        f"cart-bootstrap:{owner_key}:{generation}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return UUID(bytes=digest[:16], version=4)


async def _available_bootstrap_cart_id(
    session: AsyncSession, owner: CartOwner
) -> UUID | None:
    generation = 0
    while True:
        cart_id = _bootstrap_cart_id(owner, generation=generation)
        if cart_id is None:
            return None
        if await session.get(Cart, cart_id) is None:
            return cart_id
        generation += 1


async def _lock_guest_cart_bootstrap(
    session: AsyncSession, guest_token: str | None
) -> None:
    if guest_token is None or session.bind is None:
        return
    if session.bind.dialect.name != "postgresql":
        return
    lock_key = int.from_bytes(
        hashlib.sha256(guest_token.encode("utf-8")).digest()[:8],
        byteorder="big",
        signed=True,
    )
    await session.execute(select(func.pg_advisory_xact_lock(lock_key)))


async def _abandon_expired_guest_cart(
    session: AsyncSession, guest_token: str | None
) -> None:
    if guest_token is None:
        return
    expired_cart = await session.scalar(
        select(Cart)
        .where(
            Cart.guest_token_hash == hash_token(guest_token),
            Cart.guest_expires_at <= datetime.now(timezone.utc),
            Cart.status == "active",
        )
        .with_for_update()
    )
    if expired_cart is not None:
        expired_cart.status = "abandoned"
        await session.flush()


async def _resolve_owner(request: Request, session: AsyncSession) -> CartOwner:
    settings = get_settings()
    auth_token = request.cookies.get(settings.auth_cookie_name)
    if auth_token:
        user_id = await session.scalar(
            select(User.id)
            .join(AuthSession, AuthSession.user_id == User.id)
            .where(
                AuthSession.refresh_token_hash == hash_token(auth_token),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > datetime.now(timezone.utc),
                User.is_active.is_(True),
            )
        )
        if user_id is not None:
            return CartOwner(user_id=user_id, guest_token=None)

    guest_token = request.cookies.get(settings.guest_cookie_name)
    if guest_token is not None and len(guest_token) > 200:
        guest_token = None
    return CartOwner(user_id=None, guest_token=guest_token)


def _cart_options():
    return (
        joinedload(Cart.coupon),
        joinedload(Cart.items)
        .joinedload(CartItem.variant)
        .joinedload(ProductVariant.product)
        .joinedload(Product.category),
        joinedload(Cart.items)
        .joinedload(CartItem.variant)
        .joinedload(ProductVariant.color),
        joinedload(Cart.items)
        .joinedload(CartItem.variant)
        .joinedload(ProductVariant.size),
    )


async def _find_cart(
    session: AsyncSession, owner: CartOwner, *, lock: bool = False
) -> Cart | None:
    statement = select(Cart).where(Cart.status == "active")
    if owner.user_id is not None:
        statement = statement.where(Cart.user_id == owner.user_id)
    elif owner.guest_token is not None:
        statement = statement.where(
            Cart.guest_token_hash == hash_token(owner.guest_token),
            Cart.guest_expires_at > datetime.now(timezone.utc),
        )
    else:
        return None
    if lock:
        cart = await session.scalar(statement.with_for_update())
        return await _reload_cart(session, cart.id) if cart is not None else None
    result = await session.execute(statement.options(*_cart_options()))
    return result.unique().scalar_one_or_none()


async def _get_or_create_cart(
    session: AsyncSession,
    owner: CartOwner,
    response: Response,
) -> Cart:
    cart = await _find_cart(session, owner, lock=True)
    if cart is not None:
        return cart

    settings = get_settings()
    if owner.user_id is not None:
        active_user_id = await session.scalar(
            select(User.id)
            .where(User.id == owner.user_id, User.is_active.is_(True))
            .with_for_update()
        )
        if active_user_id is None:
            raise AppError(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="AUTH_REQUIRED",
                message="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
            )
        cart = await _find_cart(session, owner, lock=True)
        if cart is not None:
            return cart
        cart = Cart(
            id=await _available_bootstrap_cart_id(session, owner),
            user_id=owner.user_id,
            items=[],
        )
    else:
        await _lock_guest_cart_bootstrap(session, owner.guest_token)
        await _abandon_expired_guest_cart(session, owner.guest_token)
        cart = await _find_cart(session, owner, lock=True)
        if cart is not None:
            return cart
        if owner.guest_token is None:
            token = issue_guest_token(ttl_days=settings.guest_token_ttl_days)
            owner.guest_token = token.raw
            guest_expires_at = token.expires_at
            set_guest_cookie(
                response,
                name=settings.guest_cookie_name,
                token=token.raw,
                max_age=settings.guest_token_ttl_days * 24 * 60 * 60,
                secure=settings.auth_cookie_secure,
            )
        else:
            guest_expires_at = datetime.now(timezone.utc) + timedelta(
                days=settings.guest_token_ttl_days
            )
        cart = Cart(
            id=await _available_bootstrap_cart_id(session, owner),
            guest_token_hash=hash_token(owner.guest_token),
            guest_expires_at=guest_expires_at,
            items=[],
        )
    session.add(cart)
    await session.flush()
    return cart


async def merge_guest_cart_on_login(
    session: AsyncSession, *, user_id: UUID, guest_token: str | None
) -> None:
    if guest_token is None or len(guest_token) > 200:
        return
    now = datetime.now(timezone.utc)
    guest_cart = await session.scalar(
        select(Cart)
        .where(
            Cart.guest_token_hash == hash_token(guest_token),
            Cart.guest_expires_at > now,
            Cart.status == "active",
        )
        .with_for_update()
    )
    if guest_cart is None:
        return
    guest_cart = await _reload_cart(session, guest_cart.id)
    user_cart = await session.scalar(
        select(Cart)
        .where(Cart.user_id == user_id, Cart.status == "active")
        .with_for_update()
    )
    if user_cart is None:
        guest_cart.user_id = user_id
        guest_cart.guest_token_hash = None
        guest_cart.guest_expires_at = None
        guest_cart.version += 1
        return
    user_cart = await _reload_cart(session, user_cart.id)

    user_items = {item.variant_id: item for item in user_cart.items}
    for guest_item in sorted(guest_cart.items, key=lambda item: str(item.id)):
        user_item = user_items.get(guest_item.variant_id)
        if user_item is None:
            if guest_item.variant.stock_quantity > 0:
                guest_item.quantity = min(
                    guest_item.quantity, guest_item.variant.stock_quantity
                )
            guest_item.cart_id = user_cart.id
            user_items[guest_item.variant_id] = guest_item
        else:
            merged_quantity = user_item.quantity + guest_item.quantity
            if user_item.variant.stock_quantity > 0:
                merged_quantity = min(
                    merged_quantity, user_item.variant.stock_quantity
                )
            user_item.quantity = merged_quantity
            await session.delete(guest_item)
    if user_cart.coupon_id is None:
        user_cart.coupon_id = guest_cart.coupon_id
    user_cart.version += 1
    guest_cart.status = "converted"


async def _load_sellable_variant(
    session: AsyncSession, variant_id: UUID
) -> ProductVariant:
    variant = await session.scalar(
        select(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .join(Category, Category.id == Product.category_id)
        .join(Color, Color.id == ProductVariant.color_id)
        .join(Size, Size.id == ProductVariant.size_id)
        .where(
            ProductVariant.id == variant_id,
            ProductVariant.is_active.is_(True),
            Product.is_active.is_(True),
            Product.deleted_at.is_(None),
            Category.is_active.is_(True),
            Color.is_active.is_(True),
            Size.is_active.is_(True),
        )
        .options(
            contains_eager(ProductVariant.product).contains_eager(Product.category),
            contains_eager(ProductVariant.color),
            contains_eager(ProductVariant.size),
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if variant is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="VARIANT_NOT_AVAILABLE",
            message="Biến thể sản phẩm không tồn tại hoặc không còn được bán.",
        )
    return variant


def _effective_price(variant: ProductVariant) -> int:
    product = variant.product
    return product.sale_price if product.sale_price is not None else product.price


def _validate_stock(variant: ProductVariant, quantity: int) -> None:
    if quantity > variant.stock_quantity:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="OUT_OF_STOCK",
            message="Sản phẩm không đủ tồn kho.",
            fields={"quantity": f"Tối đa {variant.stock_quantity}"},
            details={
                "variant_id": str(variant.id),
                "available": variant.stock_quantity,
                "requested": quantity,
            },
        )


def _validate_price(item: CartItem, variant: ProductVariant) -> None:
    current_price = _effective_price(variant)
    if current_price != item.unit_price:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="PRICE_CHANGED",
            message="Giá sản phẩm đã thay đổi. Vui lòng kiểm tra lại giỏ hàng.",
            details={
                "variant_id": str(variant.id),
                "previous_unit_price": item.unit_price,
                "current_unit_price": current_price,
            },
        )


def _empty_cart(cart_id: UUID) -> CartResponse:
    return CartResponse(
        cart_id=cart_id,
        version=0,
        items=[],
        item_count=0,
        coupon_code=None,
        subtotal=0,
        discount_amount=0,
        shipping_fee=0,
        total=0,
        currency="VND",
    )


async def _coupon_owner_limit_reached(
    session: AsyncSession, owner: CartOwner, coupon: Coupon
) -> bool:
    if coupon.per_user_limit is None:
        return False
    redemption_statement = select(func.count(CouponRedemption.id)).where(
        CouponRedemption.coupon_id == coupon.id
    )
    if owner.user_id is not None:
        redemption_statement = redemption_statement.where(
            CouponRedemption.user_id == owner.user_id
        )
    elif owner.guest_token is not None:
        redemption_statement = redemption_statement.where(
            CouponRedemption.guest_fingerprint == hash_token(owner.guest_token)
        )
    else:
        return True
    redemption_count = await session.scalar(redemption_statement)
    return (redemption_count or 0) >= coupon.per_user_limit


async def _coupon_discount(
    session: AsyncSession,
    owner: CartOwner,
    coupon: Coupon | None,
    subtotal: int,
) -> int:
    if coupon is None or not coupon.is_active or subtotal < coupon.min_subtotal:
        return 0
    now = datetime.now(timezone.utc)
    starts_at = _as_utc(coupon.starts_at)
    ends_at = _as_utc(coupon.ends_at)
    if (starts_at is not None and starts_at > now) or (
        ends_at is not None and ends_at <= now
    ):
        return 0
    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        return 0
    if await _coupon_owner_limit_reached(session, owner, coupon):
        return 0
    if coupon.discount_type == "fixed":
        discount = coupon.discount_value
    else:
        discount = subtotal * coupon.discount_value // 100
    if coupon.max_discount is not None:
        discount = min(discount, coupon.max_discount)
    return min(discount, subtotal)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


async def _cart_response(
    session: AsyncSession, owner: CartOwner, cart: Cart
) -> CartResponse:
    response_items: list[CartItemResponse] = []
    for item in sorted(cart.items, key=lambda candidate: str(candidate.id)):
        variant = item.variant
        product = variant.product
        current_price = _effective_price(variant)
        is_available = (
            variant.is_active
            and variant.color.is_active
            and variant.size.is_active
            and product.is_active
            and product.deleted_at is None
            and product.category.is_active
            and item.quantity <= variant.stock_quantity
        )
        response_items.append(
            CartItemResponse(
                item_id=item.id,
                variant_id=variant.id,
                product_id=product.id,
                product_slug=product.slug,
                product_name=product.name,
                variant_sku=variant.variant_sku,
                color_name=variant.color.name,
                size_code=variant.size.code,
                quantity=item.quantity,
                stock_quantity=variant.stock_quantity,
                is_available=is_available,
                unit_price=current_price,
                previous_unit_price=item.unit_price,
                price_changed=current_price != item.unit_price,
                line_total=current_price * item.quantity,
            )
        )

    subtotal = sum(item.line_total for item in response_items)
    settings = get_settings()
    shipping_fee = (
        0
        if subtotal == 0 or subtotal >= settings.free_shipping_threshold
        else settings.shipping_flat_fee
    )
    discount_amount = await _coupon_discount(session, owner, cart.coupon, subtotal)
    return CartResponse(
        cart_id=cart.id,
        version=cart.version,
        items=response_items,
        item_count=sum(item.quantity for item in response_items),
        coupon_code=cart.coupon.code if cart.coupon is not None else None,
        subtotal=subtotal,
        discount_amount=discount_amount,
        shipping_fee=shipping_fee,
        total=subtotal - discount_amount + shipping_fee,
        currency="VND",
    )


async def _reload_cart(session: AsyncSession, cart_id: UUID) -> Cart:
    result = await session.execute(
        select(Cart)
        .where(Cart.id == cart_id)
        .options(*_cart_options())
        .execution_options(populate_existing=True)
    )
    cart = result.unique().scalar_one_or_none()
    if cart is None:
        raise RuntimeError("cart disappeared during transaction")
    return cart


async def _owned_item(
    session: AsyncSession, owner: CartOwner, item_id: UUID
) -> tuple[Cart, CartItem]:
    cart = await _find_cart(session, owner, lock=True)
    if cart is not None:
        item = next((candidate for candidate in cart.items if candidate.id == item_id), None)
        if item is not None:
            return cart, item
    raise AppError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="CART_ITEM_NOT_FOUND",
        message="Không tìm thấy sản phẩm trong giỏ hàng.",
    )


def _require_cart_version(cart: Cart, supplied_version: int) -> None:
    if supplied_version != cart.version:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="CART_VERSION_CONFLICT",
            message="Giỏ hàng đã thay đổi. Vui lòng tải lại và thử lại.",
            details={
                "expected_version": cart.version,
                "provided_version": supplied_version,
            },
        )


@router.get("", response_model=CartEnvelope)
async def get_cart(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    owner = await _resolve_owner(request, session)
    cart = await _find_cart(session, owner)
    if cart is None and owner.user_id is None and owner.guest_token is None:
        settings = get_settings()
        token = issue_guest_token(ttl_days=settings.guest_token_ttl_days)
        owner.guest_token = token.raw
        set_guest_cookie(
            response,
            name=settings.guest_cookie_name,
            token=token.raw,
            max_age=settings.guest_token_ttl_days * 24 * 60 * 60,
            secure=settings.auth_cookie_secure,
        )
    cart_id = cart.id if cart is not None else await _available_bootstrap_cart_id(
        session, owner
    )
    if cart_id is None:
        raise RuntimeError("cart owner could not be bootstrapped")
    return {
        "data": await _cart_response(session, owner, cart)
        if cart is not None
        else _empty_cart(cart_id),
        "meta": {"request_id": request.state.request_id},
    }


@router.post(
    "/items",
    response_model=CartEnvelope,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
        status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorEnvelope},
    },
)
async def add_cart_item(
    payload: CartItemCreateRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    owner = await _resolve_owner(request, session)
    cart = await _get_or_create_cart(session, owner, response)
    variant = await _load_sellable_variant(session, payload.variant_id)
    item = next(
        (candidate for candidate in cart.items if candidate.variant_id == variant.id),
        None,
    )
    requested_quantity = payload.quantity + (item.quantity if item is not None else 0)
    _validate_stock(variant, requested_quantity)
    current_price = _effective_price(variant)
    if item is None:
        session.add(
            CartItem(
                cart_id=cart.id,
                variant_id=variant.id,
                quantity=payload.quantity,
                unit_price=current_price,
            )
        )
    else:
        _validate_price(item, variant)
        item.quantity = requested_quantity
    cart.version += 1
    await session.commit()
    cart = await _reload_cart(session, cart.id)
    return {
        "data": await _cart_response(session, owner, cart),
        "meta": {"request_id": request.state.request_id},
    }


@router.patch(
    "/items/{item_id}",
    response_model=CartEnvelope,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
        status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorEnvelope},
    },
)
async def update_cart_item(
    item_id: UUID,
    payload: CartItemUpdateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    owner = await _resolve_owner(request, session)
    cart, item = await _owned_item(session, owner, item_id)
    _require_cart_version(cart, payload.cart_version)
    variant = await _load_sellable_variant(session, item.variant_id)
    _validate_price(item, variant)
    _validate_stock(variant, payload.quantity)
    item.quantity = payload.quantity
    cart.version += 1
    await session.commit()
    cart = await _reload_cart(session, cart.id)
    return {
        "data": await _cart_response(session, owner, cart),
        "meta": {"request_id": request.state.request_id},
    }


@router.delete(
    "/items/{item_id}",
    response_model=CartEnvelope,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
        status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorEnvelope},
    },
)
async def delete_cart_item(
    item_id: UUID,
    payload: CartItemDeleteRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    owner = await _resolve_owner(request, session)
    cart, item = await _owned_item(session, owner, item_id)
    _require_cart_version(cart, payload.cart_version)
    await session.delete(item)
    cart.version += 1
    await session.commit()
    cart = await _reload_cart(session, cart.id)
    return {
        "data": await _cart_response(session, owner, cart),
        "meta": {"request_id": request.state.request_id},
    }


@router.post(
    "/coupon",
    response_model=CartEnvelope,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorEnvelope},
        status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
        status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorEnvelope},
    },
)
async def apply_cart_coupon(
    payload: CartCouponRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    owner = await _resolve_owner(request, session)
    cart = await _find_cart(session, owner, lock=True)
    if cart is None or not cart.items:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="COUPON_NOT_APPLICABLE",
            message="Mã giảm giá chưa thể áp dụng cho giỏ hàng này.",
        )
    _require_cart_version(cart, payload.cart_version)

    subtotal = 0
    for cart_item in sorted(cart.items, key=lambda item: str(item.variant_id)):
        variant = await _load_sellable_variant(session, cart_item.variant_id)
        _validate_price(cart_item, variant)
        _validate_stock(variant, cart_item.quantity)
        subtotal += cart_item.unit_price * cart_item.quantity

    normalized_code = payload.code.strip().lower()
    coupon = await session.scalar(
        select(Coupon)
        .where(func.lower(Coupon.code) == normalized_code)
        .with_for_update()
    )
    if coupon is None or not coupon.is_active:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="COUPON_INVALID",
            message="Mã giảm giá không hợp lệ.",
        )
    now = datetime.now(timezone.utc)
    starts_at = _as_utc(coupon.starts_at)
    ends_at = _as_utc(coupon.ends_at)
    if (starts_at is not None and starts_at > now) or (
        ends_at is not None and ends_at <= now
    ):
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="COUPON_EXPIRED",
            message="Mã giảm giá chưa có hiệu lực hoặc đã hết hạn.",
        )
    if subtotal < coupon.min_subtotal or (
        coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit
    ):
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="COUPON_NOT_APPLICABLE",
            message="Mã giảm giá chưa đủ điều kiện áp dụng.",
            details={"min_subtotal": coupon.min_subtotal, "subtotal": subtotal},
        )

    if await _coupon_owner_limit_reached(session, owner, coupon):
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="COUPON_NOT_APPLICABLE",
            message="Mã giảm giá đã đạt giới hạn sử dụng cho khách hàng này.",
        )

    cart.coupon_id = coupon.id
    cart.coupon = coupon
    cart.version += 1
    await session.commit()
    cart = await _reload_cart(session, cart.id)
    return {
        "data": await _cart_response(session, owner, cart),
        "meta": {"request_id": request.state.request_id},
    }


@router.delete(
    "/coupon",
    response_model=CartEnvelope,
    responses={
        status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorEnvelope},
    },
)
async def remove_cart_coupon(
    payload: CartCouponRemoveRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    owner = await _resolve_owner(request, session)
    cart = await _find_cart(session, owner, lock=True)
    if cart is None:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="COUPON_NOT_APPLICABLE",
            message="Giỏ hàng chưa có mã giảm giá để gỡ.",
        )
    _require_cart_version(cart, payload.cart_version)
    cart.coupon_id = None
    cart.coupon = None
    cart.version += 1
    await session.commit()
    cart = await _reload_cart(session, cart.id)
    return {
        "data": await _cart_response(session, owner, cart),
        "meta": {"request_id": request.state.request_id},
    }
