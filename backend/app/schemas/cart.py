from uuid import UUID

from pydantic import BaseModel, Field


class CartItemCreateRequest(BaseModel):
    variant_id: UUID
    quantity: int = Field(ge=1, le=1_000_000)


class CartItemUpdateRequest(BaseModel):
    quantity: int = Field(ge=1, le=1_000_000)
    cart_version: int = Field(ge=1)


class CartItemDeleteRequest(BaseModel):
    cart_version: int = Field(ge=1)


class CartCouponRequest(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    cart_version: int = Field(ge=1)


class CartCouponRemoveRequest(BaseModel):
    cart_version: int = Field(ge=1)


class CartItemResponse(BaseModel):
    item_id: UUID
    variant_id: UUID
    product_id: UUID
    product_slug: str
    product_name: str
    variant_sku: str
    color_name: str
    size_code: str
    quantity: int
    stock_quantity: int
    is_available: bool
    unit_price: int
    previous_unit_price: int
    price_changed: bool
    line_total: int


class CartResponse(BaseModel):
    cart_id: UUID | None
    version: int
    items: list[CartItemResponse]
    item_count: int
    coupon_code: str | None
    subtotal: int
    discount_amount: int
    shipping_fee: int
    total: int
    currency: str


class CartEnvelope(BaseModel):
    data: CartResponse
    meta: dict[str, str]
