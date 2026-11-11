from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.orders import OrderResponse, RefundResponse


class ChatHistoryRequest(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1000)

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("content must not be blank")
        return normalized


class StrictActionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CartAddActionContext(StrictActionContext):
    action: Literal["cart_add"]
    cart_id: UUID
    variant_id: UUID
    quantity: int = Field(ge=1, le=1_000_000)


class CartUpdateActionContext(StrictActionContext):
    action: Literal["cart_update"]
    cart_id: UUID
    cart_item_id: UUID
    cart_version: int = Field(ge=1)
    quantity: int = Field(ge=1, le=1_000_000)


class CartRemoveActionContext(StrictActionContext):
    action: Literal["cart_remove"]
    cart_id: UUID
    cart_item_id: UUID
    cart_version: int = Field(ge=1)


class ChatRecipient(StrictActionContext):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=8, max_length=32)


class ChatAddress(StrictActionContext):
    address_line: str = Field(min_length=1, max_length=500)
    ward: str | None = Field(default=None, max_length=160)
    district: str | None = Field(default=None, max_length=160)
    province: str = Field(min_length=1, max_length=160)
    note: str | None = Field(default=None, max_length=1000)


class OrderCreateActionContext(StrictActionContext):
    action: Literal["order_create"]
    cart_id: UUID
    cart_version: int = Field(ge=1)
    recipient: ChatRecipient
    address: ChatAddress
    payment_method: Literal["cod", "online_demo"]
    coupon_code: str | None = Field(default=None, min_length=1, max_length=80)


class OrderCancelActionContext(StrictActionContext):
    action: Literal["order_cancel"]
    order_id: UUID
    order_code: str | None = Field(default=None, min_length=1, max_length=40)
    reason: str | None = Field(default=None, max_length=500)


class RefundRequestActionContext(StrictActionContext):
    action: Literal["refund_request"]
    order_id: UUID
    order_code: str | None = Field(default=None, min_length=1, max_length=40)
    reason_code: Literal[
        "manufacturer_fault", "transit_damage", "wrong_item", "other"
    ]
    reason_detail: str | None = Field(default=None, max_length=1000)


ChatActionContext = Annotated[
    CartAddActionContext
    | CartUpdateActionContext
    | CartRemoveActionContext
    | OrderCreateActionContext
    | OrderCancelActionContext
    | RefundRequestActionContext,
    Field(discriminator="action"),
]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatHistoryRequest] = Field(default_factory=list, max_length=6)
    action_context: ChatActionContext | None = None
    confirmation_token: str | None = Field(default=None, min_length=20, max_length=300)
    client_message_id: UUID | None = None

    @model_validator(mode="after")
    def validate_confirmation_shape(self) -> "ChatRequest":
        if self.confirmation_token is not None and self.client_message_id is None:
            raise ValueError("client_message_id is required for confirmation")
        if self.confirmation_token is not None and self.action_context is not None:
            raise ValueError("confirmation must not include action_context")
        if self.confirmation_token is None and self.client_message_id is not None:
            raise ValueError("client_message_id is only accepted for confirmation")
        return self

    @field_validator("message")
    @classmethod
    def reject_blank_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized


class ChatProductResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    image_url: str | None
    effective_price: int
    available_colors: list[str]
    available_sizes: list[str]
    in_stock: bool
    url: str


class ChatSourceResponse(BaseModel):
    source_type: Literal["product", "knowledge"]
    source_id: UUID
    rag_document_id: UUID
    chunk_ids: list[UUID]
    product_id: UUID | None
    knowledge_type: Literal["return_policy"] | None
    title: str


class ProposedActionResponse(BaseModel):
    action: Literal[
        "cart_add",
        "cart_update",
        "cart_remove",
        "order_create",
        "order_cancel",
        "refund_request",
    ]
    resource_code: str
    summary: str
    requires_confirmation: Literal[True]
    confirmation_token: str
    expires_at: datetime


class StrictActionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrderCreateActionResult(StrictActionResult):
    action: Literal["order_create"]
    order: OrderResponse


class OrderCancelActionResult(StrictActionResult):
    action: Literal["order_cancel"]
    order: OrderResponse


class RefundRequestActionResult(StrictActionResult):
    action: Literal["refund_request"]
    refund: RefundResponse


ChatActionResult = Annotated[
    OrderCreateActionResult
    | OrderCancelActionResult
    | RefundRequestActionResult,
    Field(discriminator="action"),
]


class ChatResponse(BaseModel):
    answer: str
    products: list[ChatProductResponse]
    sources: list[ChatSourceResponse]
    status: Literal[
        "ok", "insufficient_data", "out_of_scope", "provider_unavailable"
    ]
    proposed_action: ProposedActionResponse | None = None
    action_result: ChatActionResult | None = None


class ChatEnvelope(BaseModel):
    data: ChatResponse
    meta: dict[str, str]
