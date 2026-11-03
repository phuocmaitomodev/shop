from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConfirmationCreateRequest(BaseModel):
    action: Literal["order_create", "order_cancel", "refund_request"]
    resource_key: str = Field(min_length=1, max_length=160)
    payload: dict[str, Any]


class ConfirmationResponse(BaseModel):
    confirmation_token: str
    expires_at: datetime


class ConfirmationEnvelope(BaseModel):
    data: ConfirmationResponse
    meta: dict[str, str]


class OrderConfirmationPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    cart_id: UUID
    cart_version: int = Field(gt=0)
    recipient_name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=8, max_length=32)
    address_line: str = Field(min_length=1, max_length=500)
    ward: str | None = Field(default=None, max_length=160)
    district: str | None = Field(default=None, max_length=160)
    province: str = Field(min_length=1, max_length=160)
    note: str | None = Field(default=None, max_length=1000)
    payment_method: Literal["cod", "online_demo"]


class OrderCreateRequest(OrderConfirmationPayload):
    confirmation_token: str = Field(min_length=20, max_length=300)


class OrderCancelRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reason: str | None = Field(default=None, max_length=500)
    confirmation_token: str = Field(min_length=20, max_length=300)


class OrderItemResponse(BaseModel):
    product_id: UUID | None
    variant_id: UUID | None
    product_name: str
    product_sku: str
    variant_sku: str
    color_name: str
    size_code: str
    image_url: str | None
    unit_price: int
    quantity: int
    line_total: int


class PaymentResponse(BaseModel):
    method: Literal["cod", "online_demo"]
    status: str
    amount: int
    provider: Literal["demo"] = "demo"
    is_simulation: Literal[True] = True


class PaymentEnvelope(BaseModel):
    data: PaymentResponse
    meta: dict[str, str]


class RefundCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reason_code: Literal[
        "manufacturer_fault", "transit_damage", "wrong_item", "other"
    ]
    reason_detail: str | None = Field(default=None, max_length=1000)
    confirmation_token: str = Field(min_length=20, max_length=300)


class RefundResponse(BaseModel):
    id: UUID
    order_code: str
    reason_code: str
    reason_detail: str | None
    amount: int
    status: str
    provider: Literal["demo"] = "demo"
    is_simulation: Literal[True] = True
    created_at: datetime


class RefundEnvelope(BaseModel):
    data: RefundResponse
    meta: dict[str, str]


class OrderResponse(BaseModel):
    id: UUID
    order_code: str
    status: str
    recipient_name: str
    phone: str
    address_line: str
    ward: str | None
    district: str | None
    province: str
    note: str | None
    subtotal: int
    discount_amount: int
    shipping_fee: int
    total: int
    currency: Literal["VND"] = "VND"
    items: list[OrderItemResponse]
    payment: PaymentResponse
    guest_lookup_token: str | None = None
    created_at: datetime


class OrderEnvelope(BaseModel):
    data: OrderResponse
    meta: dict[str, str]
