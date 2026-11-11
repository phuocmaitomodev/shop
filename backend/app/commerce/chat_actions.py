import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.cart import (
    _effective_price,
    _find_cart,
    _load_sellable_variant,
    _owned_item,
    _require_cart_version,
    _validate_price,
    _validate_stock,
    add_cart_item,
    delete_cart_item,
    update_cart_item,
)
from app.api.v1.orders import (
    _as_utc,
    _canonical_hash,
    _existing_idempotency,
    _order_confirmation_snapshot,
    _owner_guest_hash,
    _owned_order,
    _resolve_mutation_owner,
    _session_key,
    cancel_order,
    create_order,
    create_refund_request,
)
from app.commerce.identity import issue_confirmation_token
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import hash_token
from app.models.commerce import ActionConfirmation, IdempotencyRecord, Order
from app.schemas.cart import (
    CartItemCreateRequest,
    CartItemDeleteRequest,
    CartItemUpdateRequest,
)
from app.schemas.chat import (
    CartAddActionContext,
    CartRemoveActionContext,
    CartUpdateActionContext,
    ChatActionContext,
    OrderCancelActionContext,
    OrderCreateActionContext,
    RefundRequestActionContext,
)
from app.schemas.orders import (
    OrderCancelRequest,
    OrderConfirmationPayload,
    OrderCreateRequest,
    OrderResponse,
    RefundCreateRequest,
    RefundResponse,
)


@dataclass(frozen=True)
class ChatActionProposal:
    action: str
    resource_code: str
    summary: str
    confirmation_token: str
    expires_at: datetime
    requires_confirmation: bool = True


@dataclass(frozen=True)
class ChatActionExecution:
    action: str
    resource_code: str
    summary: str
    result: OrderResponse | RefundResponse | None


class DatabaseChatActionAdapter:
    def __init__(self, session: AsyncSession, request: Request) -> None:
        self._session = session
        self._request = request

    async def propose(self, context: ChatActionContext) -> ChatActionProposal:
        if not isinstance(
            context,
            (
                CartAddActionContext,
                CartUpdateActionContext,
                CartRemoveActionContext,
                OrderCreateActionContext,
                OrderCancelActionContext,
                RefundRequestActionContext,
            ),
        ):
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="CHAT_ACTION_UNAVAILABLE",
                message="Hành động chat này chưa sẵn sàng.",
            )

        order_mutation = isinstance(
            context, (OrderCancelActionContext, RefundRequestActionContext)
        )
        owner = await _resolve_mutation_owner(
            self._request, self._session, allow_lookup=order_mutation
        )
        allow_cart_token = self._request.headers.get("X-Order-Lookup-Token") is None
        if isinstance(context, RefundRequestActionContext):
            order_code = await self._session.scalar(
                select(Order.order_code).where(Order.id == context.order_id)
            )
            order = (
                await _owned_order(
                    self._session,
                    owner,
                    order_code,
                    allow_cart_token=allow_cart_token,
                )
                if order_code is not None
                else None
            )
            if order is None or (
                context.order_code is not None and context.order_code != order.order_code
            ):
                raise AppError(
                    status_code=status.HTTP_404_NOT_FOUND,
                    code="ORDER_NOT_FOUND",
                    message="Không tìm thấy đơn hàng.",
                )
            if order.status != "completed" or order.payment_status not in {
                "paid_demo",
                "demo_approved",
            }:
                raise AppError(
                    status_code=status.HTTP_409_CONFLICT,
                    code="REFUND_NOT_ELIGIBLE",
                    message="Đơn hàng chưa đủ điều kiện hoàn tiền mô phỏng.",
                )
            confirmation_payload = {
                "reason_code": context.reason_code,
                "reason_detail": context.reason_detail,
            }
            stored_payload = {
                "action_context": context.model_dump(mode="json"),
                "confirmation_payload": confirmation_payload,
            }
            resource_code = order.order_code
            summary = (
                f"Xác nhận yêu cầu hoàn tiền mô phỏng {order.total:,} VND "
                f"cho đơn {order.order_code}."
            ).replace(",", ".")
        elif isinstance(context, OrderCancelActionContext):
            order_code = await self._session.scalar(
                select(Order.order_code).where(Order.id == context.order_id)
            )
            order = (
                await _owned_order(
                    self._session,
                    owner,
                    order_code,
                    allow_cart_token=allow_cart_token,
                )
                if order_code is not None
                else None
            )
            if order is None or (
                context.order_code is not None and context.order_code != order.order_code
            ):
                raise AppError(
                    status_code=status.HTTP_404_NOT_FOUND,
                    code="ORDER_NOT_FOUND",
                    message="Không tìm thấy đơn hàng.",
                )
            if order.status not in {"pending_confirmation", "confirmed"}:
                raise AppError(
                    status_code=status.HTTP_409_CONFLICT,
                    code="ORDER_STATUS_NOT_CANCELLABLE",
                    message="Đơn hàng không còn ở trạng thái có thể hủy.",
                )
            confirmation_payload = {"reason": context.reason}
            stored_payload = {
                "action_context": context.model_dump(mode="json"),
                "confirmation_payload": confirmation_payload,
            }
            resource_code = order.order_code
            summary = f"Xác nhận hủy đơn {order.order_code}."
        elif isinstance(context, OrderCreateActionContext):
            cart = await _find_cart(self._session, owner, lock=True)
            if cart is None or cart.id != context.cart_id or not cart.items:
                raise AppError(
                    status_code=status.HTTP_404_NOT_FOUND,
                    code="CART_NOT_FOUND",
                    message="Không tìm thấy giỏ hàng để xác nhận.",
                )
            _require_cart_version(cart, context.cart_version)
            snapshot = await _order_confirmation_snapshot(self._session, owner, cart)
            if context.coupon_code != snapshot["coupon_code"]:
                raise AppError(
                    status_code=status.HTTP_409_CONFLICT,
                    code="COUPON_INVALID",
                    message="Mã giảm giá không khớp giỏ hàng hiện tại.",
                )
            order_payload = OrderConfirmationPayload(
                cart_id=context.cart_id,
                cart_version=context.cart_version,
                recipient_name=context.recipient.name,
                phone=context.recipient.phone,
                address_line=context.address.address_line,
                ward=context.address.ward,
                district=context.address.district,
                province=context.address.province,
                note=context.address.note,
                payment_method=context.payment_method,
            ).model_dump(mode="json")
            confirmation_payload = {**order_payload, "server_snapshot": snapshot}
            stored_payload = {
                "action_context": context.model_dump(mode="json"),
                "confirmation_payload": confirmation_payload,
            }
            summary = (
                f"Xác nhận tạo đơn {snapshot['total']:,} VND "
                f"bằng {context.payment_method}."
            ).replace(",", ".")
        elif isinstance(context, CartAddActionContext):
            cart = await _find_cart(self._session, owner, lock=True)
            if cart is None or cart.id != context.cart_id:
                raise AppError(
                    status_code=status.HTTP_404_NOT_FOUND,
                    code="CART_NOT_FOUND",
                    message="Không tìm thấy giỏ hàng để xác nhận.",
                )
            variant = await _load_sellable_variant(self._session, context.variant_id)
            existing_item = next(
                (item for item in cart.items if item.variant_id == variant.id), None
            )
            requested_quantity = context.quantity + (
                existing_item.quantity if existing_item is not None else 0
            )
            _validate_stock(variant, requested_quantity)
            if existing_item is not None:
                _validate_price(existing_item, variant)
            unit_price = _effective_price(variant)
            summary = (
                f"Xác nhận thêm {context.quantity} × {variant.product.name} "
                f"vào giỏ hàng ({unit_price * context.quantity:,} VND)."
            ).replace(",", ".")
            confirmation_payload = context.model_dump(mode="json")
            stored_payload = confirmation_payload
        else:
            cart, item = await _owned_item(
                self._session, owner, context.cart_item_id
            )
            if cart.id != context.cart_id:
                raise AppError(
                    status_code=status.HTTP_404_NOT_FOUND,
                    code="CART_ITEM_NOT_FOUND",
                    message="Không tìm thấy sản phẩm trong giỏ hàng.",
                )
            _require_cart_version(cart, context.cart_version)
            variant = await _load_sellable_variant(self._session, item.variant_id)
            _validate_price(item, variant)
            if isinstance(context, CartUpdateActionContext):
                _validate_stock(variant, context.quantity)
                summary = f"Xác nhận đổi số lượng sản phẩm thành {context.quantity}."
            else:
                summary = "Xác nhận xóa sản phẩm khỏi giỏ hàng."
            confirmation_payload = context.model_dump(mode="json")
            stored_payload = confirmation_payload

        if not isinstance(
            context, (OrderCancelActionContext, RefundRequestActionContext)
        ):
            resource_code = str(cart.id)
        settings = get_settings()
        token = issue_confirmation_token(
            ttl_seconds=settings.action_confirmation_ttl_seconds
        )
        issued_at = token.expires_at - timedelta(
            seconds=settings.action_confirmation_ttl_seconds
        )
        self._session.add(
            ActionConfirmation(
                owner_user_id=owner.user_id,
                owner_guest_token_hash=_owner_guest_hash(owner),
                session_key=_session_key(self._request, owner),
                action=context.action,
                resource_key=resource_code,
                payload_json=stored_payload,
                payload_hash=_canonical_hash(confirmation_payload),
                token_hash=token.digest,
                expires_at=token.expires_at,
                created_at=issued_at,
                updated_at=issued_at,
            )
        )
        await self._session.commit()

        return ChatActionProposal(
            action=context.action,
            resource_code=resource_code,
            summary=summary,
            confirmation_token=token.raw,
            expires_at=token.expires_at,
        )

    async def confirm(
        self,
        *,
        token: str,
        idempotency_key: str,
        client_message_id: UUID,
    ) -> ChatActionExecution:
        owner = await _resolve_mutation_owner(
            self._request, self._session, allow_lookup=True
        )
        confirmation = await self._session.scalar(
            select(ActionConfirmation).where(
                ActionConfirmation.token_hash == hash_token(token)
            )
        )
        if confirmation is None:
            raise self._invalid_confirmation()
        if confirmation.action.startswith("cart_"):
            confirmation = await self._session.scalar(
                select(ActionConfirmation)
                .where(ActionConfirmation.id == confirmation.id)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
            if confirmation is None:
                raise self._invalid_confirmation()
        owner_matches = (
            confirmation.owner_user_id == owner.user_id
            and confirmation.owner_guest_token_hash == _owner_guest_hash(owner)
            and confirmation.session_key == _session_key(self._request, owner)
        )
        stored_confirmation_payload = confirmation.payload_json.get(
            "confirmation_payload", confirmation.payload_json
        )
        payload_matches = hmac.compare_digest(
            confirmation.payload_hash, _canonical_hash(stored_confirmation_payload)
        )
        if not owner_matches or not payload_matches:
            raise self._invalid_confirmation()

        request_hash = _canonical_hash(
            {
                "payload_hash": confirmation.payload_hash,
                "client_message_id": str(client_message_id),
            }
        )
        if confirmation.action.startswith("cart_"):
            existing = await _existing_idempotency(
                self._session,
                owner,
                operation=confirmation.action,
                resource_key=confirmation.resource_key,
                key_hash=hash_token(idempotency_key),
            )
            if existing is not None:
                if not hmac.compare_digest(existing.request_hash, request_hash):
                    raise AppError(
                        status_code=status.HTTP_409_CONFLICT,
                        code="IDEMPOTENCY_KEY_REUSED",
                        message="Idempotency-Key đã được dùng cho dữ liệu khác.",
                    )
                if existing.status == "completed" and existing.response_body:
                    return ChatActionExecution(
                        action=confirmation.action,
                        resource_code=confirmation.resource_key,
                        summary=existing.response_body["summary"],
                        result=None,
                    )

        now = datetime.now(timezone.utc)
        if confirmation.action.startswith("cart_"):
            if (
                confirmation.consumed_at is not None
                or _as_utc(confirmation.expires_at) <= now
            ):
                raise self._invalid_confirmation()
        else:
            action_payload = confirmation.payload_json.get("action_context")
            if not isinstance(action_payload, dict):
                raise self._invalid_confirmation()
            await self._bind_confirmation_attempt(
                confirmation.id, client_message_id, idempotency_key
            )
        if confirmation.action == "order_create":
            context = OrderCreateActionContext.model_validate(
                confirmation.payload_json["action_context"]
            )
            result = await create_order(
                OrderCreateRequest(
                    cart_id=context.cart_id,
                    cart_version=context.cart_version,
                    recipient_name=context.recipient.name,
                    phone=context.recipient.phone,
                    address_line=context.address.address_line,
                    ward=context.address.ward,
                    district=context.address.district,
                    province=context.address.province,
                    note=context.address.note,
                    payment_method=context.payment_method,
                    confirmation_token=token,
                ),
                self._request,
                idempotency_key,
                self._session,
            )
            order = result["data"]
            return ChatActionExecution(
                action=confirmation.action,
                resource_code=order.order_code,
                summary=f"Đã tạo đơn {order.order_code} ({order.total:,} VND).".replace(
                    ",", "."
                ),
                result=order,
            )
        if confirmation.action == "order_cancel":
            context = OrderCancelActionContext.model_validate(
                confirmation.payload_json["action_context"]
            )
            result = await cancel_order(
                confirmation.resource_key,
                OrderCancelRequest(
                    reason=context.reason,
                    confirmation_token=token,
                ),
                self._request,
                idempotency_key,
                self._session,
            )
            order = result["data"]
            return ChatActionExecution(
                action=confirmation.action,
                resource_code=order.order_code,
                summary=f"Đã hủy đơn {order.order_code}.",
                result=order,
            )
        if confirmation.action == "refund_request":
            context = RefundRequestActionContext.model_validate(
                confirmation.payload_json["action_context"]
            )
            result = await create_refund_request(
                confirmation.resource_key,
                RefundCreateRequest(
                    reason_code=context.reason_code,
                    reason_detail=context.reason_detail,
                    confirmation_token=token,
                ),
                self._request,
                idempotency_key,
                self._session,
            )
            refund = result["data"]
            return ChatActionExecution(
                action=confirmation.action,
                resource_code=refund.order_code,
                summary=(
                    f"Đã tạo yêu cầu hoàn tiền mô phỏng "
                    f"{refund.amount:,} VND cho đơn {refund.order_code}."
                ).replace(",", "."),
                result=refund,
            )
        if confirmation.action not in {"cart_add", "cart_update", "cart_remove"}:
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="CHAT_ACTION_UNAVAILABLE",
                message="Hành động chat này chưa sẵn sàng.",
            )

        if confirmation.action == "cart_add":
            context = CartAddActionContext.model_validate(confirmation.payload_json)
            current_cart = await _find_cart(self._session, owner, lock=True)
            if current_cart is None or current_cart.id != context.cart_id:
                raise self._invalid_confirmation()
            variant = await _load_sellable_variant(self._session, context.variant_id)
            existing_item = next(
                (item for item in current_cart.items if item.variant_id == variant.id), None
            )
            requested_quantity = context.quantity + (
                existing_item.quantity if existing_item is not None else 0
            )
            _validate_stock(variant, requested_quantity)
            if existing_item is not None:
                _validate_price(existing_item, variant)
            summary = f"Đã thêm {context.quantity} sản phẩm vào giỏ hàng."
        elif confirmation.action == "cart_update":
            context = CartUpdateActionContext.model_validate(confirmation.payload_json)
            current_cart, item = await _owned_item(
                self._session, owner, context.cart_item_id
            )
            if current_cart.id != context.cart_id:
                raise self._invalid_confirmation()
            _require_cart_version(current_cart, context.cart_version)
            variant = await _load_sellable_variant(self._session, item.variant_id)
            _validate_price(item, variant)
            _validate_stock(variant, context.quantity)
            summary = f"Đã đổi số lượng sản phẩm thành {context.quantity}."
        else:
            context = CartRemoveActionContext.model_validate(confirmation.payload_json)
            current_cart, item = await _owned_item(
                self._session, owner, context.cart_item_id
            )
            if current_cart.id != context.cart_id:
                raise self._invalid_confirmation()
            _require_cart_version(current_cart, context.cart_version)
            variant = await _load_sellable_variant(self._session, item.variant_id)
            _validate_price(item, variant)
            summary = "Đã xóa sản phẩm khỏi giỏ hàng."
        settings = get_settings()
        confirmation.consumed_at = now
        self._session.add(
            IdempotencyRecord(
                owner_user_id=owner.user_id,
                owner_guest_token_hash=_owner_guest_hash(owner),
                operation=confirmation.action,
                resource_key=confirmation.resource_key,
                key_hash=hash_token(idempotency_key),
                request_hash=request_hash,
                status="completed",
                response_body={"summary": summary},
                response_status=status.HTTP_200_OK,
                expires_at=now + timedelta(hours=settings.idempotency_ttl_hours),
            )
        )
        if isinstance(context, CartAddActionContext):
            await add_cart_item(
                CartItemCreateRequest(
                    variant_id=context.variant_id, quantity=context.quantity
                ),
                self._request,
                Response(),
                self._session,
            )
        elif isinstance(context, CartUpdateActionContext):
            await update_cart_item(
                context.cart_item_id,
                CartItemUpdateRequest(
                    quantity=context.quantity, cart_version=context.cart_version
                ),
                self._request,
                self._session,
            )
        else:
            await delete_cart_item(
                context.cart_item_id,
                CartItemDeleteRequest(cart_version=context.cart_version),
                self._request,
                self._session,
            )
        return ChatActionExecution(
            action=confirmation.action,
            resource_code=confirmation.resource_key,
            summary=summary,
            result=None,
        )

    async def _bind_confirmation_attempt(
        self,
        confirmation_id: UUID,
        client_message_id: UUID,
        idempotency_key: str,
    ) -> None:
        confirmation = await self._session.scalar(
            select(ActionConfirmation)
            .where(ActionConfirmation.id == confirmation_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if confirmation is None:
            raise self._invalid_confirmation()
        supplied_message_id = str(client_message_id)
        supplied_key_hash = hash_token(idempotency_key)
        bound_message_id = confirmation.payload_json.get("confirmed_client_message_id")
        bound_key_hash = confirmation.payload_json.get(
            "confirmed_idempotency_key_hash"
        )
        if (
            bound_message_id == supplied_message_id
            and bound_key_hash == supplied_key_hash
        ):
            await self._session.commit()
            return
        if bound_message_id is not None or bound_key_hash is not None:
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="IDEMPOTENCY_KEY_REUSED",
                message="Idempotency-Key đã được dùng cho dữ liệu khác.",
            )
        if confirmation.consumed_at is not None or _as_utc(
            confirmation.expires_at
        ) <= datetime.now(timezone.utc):
            raise self._invalid_confirmation()
        confirmation.payload_json = {
            **confirmation.payload_json,
            "confirmed_client_message_id": supplied_message_id,
            "confirmed_idempotency_key_hash": supplied_key_hash,
        }
        await self._session.commit()

    @staticmethod
    def _invalid_confirmation() -> AppError:
        return AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="CONFIRMATION_INVALID",
            message="Xác nhận không hợp lệ, đã hết hạn hoặc đã được sử dụng.",
        )
