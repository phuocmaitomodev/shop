from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


REFUND_REASON_CODES = (
    "manufacturer_fault",
    "transit_damage",
    "wrong_item",
    "other",
)


class CommerceTimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Cart(CommerceTimestampMixin, Base):
    __tablename__ = "carts"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND guest_token_hash IS NULL AND "
            "guest_expires_at IS NULL) OR "
            "(user_id IS NULL AND guest_token_hash IS NOT NULL AND "
            "guest_expires_at IS NOT NULL)",
            name="owner_mode_valid",
        ),
        CheckConstraint(
            "status IN ('active', 'converted', 'abandoned')", name="status_valid"
        ),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint(
            "guest_expires_at IS NULL OR guest_expires_at > created_at",
            name="guest_expiry_valid",
        ),
        Index("ix_carts_user_status", "user_id", "status"),
        Index(
            "ix_carts_guest_lookup", "guest_token_hash", "guest_expires_at", "status"
        ),
        Index(
            "uq_carts_active_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active' AND user_id IS NOT NULL"),
            sqlite_where=text("status = 'active' AND user_id IS NOT NULL"),
        ),
        Index(
            "uq_carts_active_guest",
            "guest_token_hash",
            unique=True,
            postgresql_where=text(
                "status = 'active' AND guest_token_hash IS NOT NULL"
            ),
            sqlite_where=text("status = 'active' AND guest_token_hash IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    guest_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    guest_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    coupon_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("coupons.id", ondelete="SET NULL"), nullable=True
    )

    items: Mapped[list["CartItem"]] = relationship(
        back_populates="cart", cascade="all, delete-orphan"
    )
    coupon: Mapped["Coupon | None"] = relationship()


class CartItem(CommerceTimestampMixin, Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        UniqueConstraint("cart_id", "variant_id", name="uq_cart_items_cart_variant"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    cart_id: Mapped[UUID] = mapped_column(
        ForeignKey("carts.id", ondelete="CASCADE"), index=True
    )
    variant_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"), index=True
    )
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[int] = mapped_column(BigInteger)

    cart: Mapped[Cart] = relationship(back_populates="items")
    variant = relationship("ProductVariant")


class Coupon(CommerceTimestampMixin, Base):
    __tablename__ = "coupons"
    __table_args__ = (
        CheckConstraint(
            "discount_type IN ('fixed', 'percent')", name="discount_type_valid"
        ),
        CheckConstraint("discount_value > 0", name="discount_value_positive"),
        CheckConstraint(
            "discount_type <> 'percent' OR discount_value <= 100",
            name="percent_value_valid",
        ),
        CheckConstraint(
            "max_discount IS NULL OR max_discount >= 0",
            name="max_discount_non_negative",
        ),
        CheckConstraint("min_subtotal >= 0", name="min_subtotal_non_negative"),
        CheckConstraint(
            "ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at",
            name="active_window_valid",
        ),
        CheckConstraint(
            "usage_limit IS NULL OR usage_limit > 0", name="usage_limit_positive"
        ),
        CheckConstraint(
            "per_user_limit IS NULL OR per_user_limit > 0",
            name="per_user_limit_positive",
        ),
        CheckConstraint("used_count >= 0", name="used_count_non_negative"),
        CheckConstraint(
            "usage_limit IS NULL OR used_count <= usage_limit",
            name="used_count_within_limit",
        ),
        Index("ix_coupons_active_window", "is_active", "starts_at", "ends_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    discount_type: Mapped[str] = mapped_column(String(20))
    discount_value: Mapped[int] = mapped_column(BigInteger)
    max_discount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    min_subtotal: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0"
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_user_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )


Index("uq_coupons_code_lower", func.lower(Coupon.code), unique=True)


class SystemSetting(CommerceTimestampMixin, Base):
    __tablename__ = "system_settings"
    __table_args__ = (
        CheckConstraint(
            "key IN ('shipping_flat_fee', 'free_shipping_threshold')",
            name="key_valid",
        ),
    )

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSON)


class Order(CommerceTimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND guest_lookup_token_hash IS NULL AND "
            "guest_lookup_expires_at IS NULL) OR "
            "(user_id IS NULL AND guest_lookup_token_hash IS NOT NULL AND "
            "guest_lookup_expires_at IS NOT NULL)",
            name="owner_mode_valid",
        ),
        CheckConstraint(
            "guest_lookup_expires_at IS NULL OR guest_lookup_expires_at > created_at",
            name="guest_lookup_expiry_valid",
        ),
        CheckConstraint(
            "status IN ('pending_confirmation', 'confirmed', 'preparing', "
            "'shipping', 'completed', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint(
            "payment_method IN ('cod', 'online_demo')", name="payment_method_valid"
        ),
        CheckConstraint(
            "payment_status IN ('pending', 'cod_due', 'demo_processing', "
            "'demo_approved', 'demo_declined', 'paid_demo', 'cancelled')",
            name="payment_status_valid",
        ),
        CheckConstraint("subtotal >= 0", name="subtotal_non_negative"),
        CheckConstraint("discount_amount >= 0", name="discount_non_negative"),
        CheckConstraint("shipping_fee >= 0", name="shipping_non_negative"),
        CheckConstraint("total >= 0", name="total_non_negative"),
        CheckConstraint(
            "discount_amount <= subtotal", name="discount_not_above_subtotal"
        ),
        CheckConstraint(
            "total = subtotal - discount_amount + shipping_fee",
            name="total_formula_valid",
        ),
        CheckConstraint(
            "(status = 'cancelled' AND cancelled_at IS NOT NULL) OR "
            "(status <> 'cancelled' AND cancelled_at IS NULL)",
            name="cancel_metadata_valid",
        ),
        Index("ix_orders_user_created", "user_id", text("created_at DESC")),
        Index("ix_orders_status_created", "status", text("created_at DESC")),
        Index(
            "ix_orders_guest_lookup",
            "guest_lookup_token_hash",
            "guest_lookup_expires_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_code: Mapped[str] = mapped_column(String(40), unique=True)
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    cart_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("carts.id", ondelete="SET NULL"), nullable=True
    )
    coupon_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("coupons.id", ondelete="RESTRICT"), nullable=True
    )
    guest_lookup_token_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True
    )
    guest_lookup_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recipient_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(32))
    address_line: Mapped[str] = mapped_column(String(500))
    ward: Mapped[str | None] = mapped_column(String(160), nullable=True)
    district: Mapped[str | None] = mapped_column(String(160), nullable=True)
    province: Mapped[str] = mapped_column(String(160))
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), default="pending_confirmation", server_default="pending_confirmation"
    )
    payment_method: Mapped[str] = mapped_column(String(20))
    payment_status: Mapped[str] = mapped_column(
        String(30), default="pending", server_default="pending"
    )
    subtotal: Mapped[int] = mapped_column(BigInteger)
    discount_amount: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0"
    )
    shipping_fee: Mapped[int] = mapped_column(BigInteger)
    total: Mapped[int] = mapped_column(BigInteger)
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("line_total >= 0", name="line_total_non_negative"),
        CheckConstraint(
            "line_total = unit_price * quantity", name="line_total_formula_valid"
        ),
        UniqueConstraint("order_id", "variant_sku", name="uq_order_items_variant_sku"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    variant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True
    )
    product_name: Mapped[str] = mapped_column(String(240))
    product_sku: Mapped[str] = mapped_column(String(80))
    variant_sku: Mapped[str] = mapped_column(String(100))
    color_name: Mapped[str] = mapped_column(String(100))
    size_code: Mapped[str] = mapped_column(String(20))
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    unit_price: Mapped[int] = mapped_column(BigInteger)
    quantity: Mapped[int] = mapped_column(Integer)
    line_total: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    order: Mapped[Order] = relationship(back_populates="items")


class CouponRedemption(Base):
    __tablename__ = "coupon_redemptions"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND guest_fingerprint IS NULL) OR "
            "(user_id IS NULL AND guest_fingerprint IS NOT NULL)",
            name="owner_mode_valid",
        ),
        CheckConstraint(
            "discount_amount >= 0", name="discount_amount_non_negative"
        ),
        UniqueConstraint("coupon_id", "order_id", name="uq_coupon_redemptions_order"),
        Index("ix_coupon_redemptions_user_created", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    coupon_id: Mapped[UUID] = mapped_column(
        ForeignKey("coupons.id", ondelete="RESTRICT")
    )
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE")
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    guest_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    discount_amount: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint(
            "movement_type IN ('seed', 'admin_adjustment', 'order_reserve', "
            "'order_cancel_restore')",
            name="type_valid",
        ),
        CheckConstraint("quantity_delta <> 0", name="quantity_delta_non_zero"),
        CheckConstraint("stock_after >= 0", name="stock_after_non_negative"),
        CheckConstraint(
            "(movement_type IN ('order_reserve', 'order_cancel_restore') AND "
            "order_id IS NOT NULL) OR "
            "(movement_type IN ('seed', 'admin_adjustment'))",
            name="order_reference_valid",
        ),
        Index("ix_inventory_movements_variant_created", "variant_id", "created_at"),
        Index(
            "uq_inventory_order_transition",
            "order_id",
            "variant_id",
            "movement_type",
            unique=True,
            postgresql_where=text(
                "movement_type IN ('order_reserve', 'order_cancel_restore')"
            ),
            sqlite_where=text(
                "movement_type IN ('order_reserve', 'order_cancel_restore')"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    variant_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT")
    )
    order_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=True
    )
    movement_type: Mapped[str] = mapped_column(String(30))
    quantity_delta: Mapped[int] = mapped_column(Integer)
    stock_after: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PaymentAttempt(CommerceTimestampMixin, Base):
    __tablename__ = "payment_attempts"
    __table_args__ = (
        CheckConstraint("method IN ('cod', 'online_demo')", name="method_valid"),
        CheckConstraint(
            "status IN ('pending', 'cod_due', 'demo_processing', 'demo_approved', "
            "'demo_declined', 'paid_demo', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        CheckConstraint("provider = 'demo'", name="provider_demo_only"),
        UniqueConstraint(
            "order_id",
            "method",
            "idempotency_key_hash",
            name="uq_payment_attempt_idempotency",
        ),
        Index("ix_payment_attempts_order_created", "order_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE")
    )
    method: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(
        String(30), default="pending", server_default="pending"
    )
    amount: Mapped[int] = mapped_column(BigInteger)
    provider: Mapped[str] = mapped_column(
        String(20), default="demo", server_default="demo"
    )
    idempotency_key_hash: Mapped[str] = mapped_column(String(64))


class RefundRequest(CommerceTimestampMixin, Base):
    __tablename__ = "refund_requests"
    __table_args__ = (
        CheckConstraint(
            "(requester_user_id IS NOT NULL AND requester_guest_token_hash IS NULL) "
            "OR (requester_user_id IS NULL AND "
            "requester_guest_token_hash IS NOT NULL)",
            name="requester_mode_valid",
        ),
        CheckConstraint(
            "reason_code IN ('manufacturer_fault', 'transit_damage', "
            "'wrong_item', 'other')",
            name="reason_code_valid",
        ),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        CheckConstraint(
            "status IN ('requested', 'demo_reviewing', 'demo_approved', "
            "'demo_rejected', 'cancelled', 'demo_refunded')",
            name="status_valid",
        ),
        Index("ix_refund_requests_order_created", "order_id", "created_at"),
        Index(
            "uq_refund_requests_one_non_terminal",
            "order_id",
            unique=True,
            postgresql_where=text(
                "status NOT IN ('demo_rejected', 'cancelled', 'demo_refunded')"
            ),
            sqlite_where=text(
                "status NOT IN ('demo_rejected', 'cancelled', 'demo_refunded')"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE")
    )
    requester_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    requester_guest_token_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    reason_code: Mapped[str] = mapped_column(String(60))
    reason_detail: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(
        String(30), default="requested", server_default="requested"
    )


class IdempotencyRecord(CommerceTimestampMixin, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        CheckConstraint(
            "(owner_user_id IS NOT NULL AND owner_guest_token_hash IS NULL) OR "
            "(owner_user_id IS NULL AND owner_guest_token_hash IS NOT NULL)",
            name="owner_mode_valid",
        ),
        CheckConstraint(
            "status IN ('processing', 'completed', 'failed')", name="status_valid"
        ),
        CheckConstraint(
            "response_status IS NULL OR "
            "(response_status >= 100 AND response_status <= 599)",
            name="response_status_valid",
        ),
        CheckConstraint("expires_at > created_at", name="expiry_valid"),
        Index("ix_idempotency_records_expires_at", "expires_at"),
        Index(
            "uq_idempotency_user_scope",
            "owner_user_id",
            "operation",
            "resource_key",
            "key_hash",
            unique=True,
            postgresql_where=text("owner_user_id IS NOT NULL"),
            sqlite_where=text("owner_user_id IS NOT NULL"),
        ),
        Index(
            "uq_idempotency_guest_scope",
            "owner_guest_token_hash",
            "operation",
            "resource_key",
            "key_hash",
            unique=True,
            postgresql_where=text("owner_guest_token_hash IS NOT NULL"),
            sqlite_where=text("owner_guest_token_hash IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    owner_guest_token_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    operation: Mapped[str] = mapped_column(String(60))
    resource_key: Mapped[str] = mapped_column(String(160))
    key_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(20), default="processing", server_default="processing"
    )
    response_body: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ActionConfirmation(CommerceTimestampMixin, Base):
    __tablename__ = "action_confirmations"
    __table_args__ = (
        CheckConstraint(
            "(owner_user_id IS NOT NULL AND owner_guest_token_hash IS NULL) OR "
            "(owner_user_id IS NULL AND owner_guest_token_hash IS NOT NULL)",
            name="owner_mode_valid",
        ),
        CheckConstraint(
            "action IN ('cart_add', 'cart_update', 'cart_remove', 'order_create', "
            "'order_cancel', 'refund_request')",
            name="action_valid",
        ),
        CheckConstraint(
            "expires_at > created_at AND "
            "expires_at <= created_at + interval '5 minutes'",
            name="ttl_valid",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= created_at",
            name="consumed_at_valid",
        ),
        Index("ix_action_confirmations_token_expiry", "token_hash", "expires_at"),
        Index("ix_action_confirmations_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    owner_guest_token_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    session_key: Mapped[str] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(40))
    resource_key: Mapped[str] = mapped_column(String(160))
    payload_json: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
