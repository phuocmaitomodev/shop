from uuid import UUID

from pydantic import BaseModel


class CategoryResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: str | None
    sort_order: int


class CategoryListEnvelope(BaseModel):
    data: list[CategoryResponse]
    meta: dict[str, str]


class ColorResponse(BaseModel):
    id: UUID
    name: str
    hex_code: str | None


class SizeResponse(BaseModel):
    id: UUID
    code: str
    name: str


class ProductCardResponse(BaseModel):
    id: UUID
    slug: str
    sku: str
    name: str
    image_url: str | None
    price: int
    sale_price: int | None
    effective_price: int
    category: CategoryResponse
    labels: list[str]
    available_sizes: list[str]
    available_colors: list[ColorResponse]
    in_stock: bool


class ProductPageData(BaseModel):
    items: list[ProductCardResponse]
    page: int
    page_size: int
    total: int


class ProductListEnvelope(BaseModel):
    data: ProductPageData
    meta: dict[str, str]


class ProductImageResponse(BaseModel):
    id: UUID
    url: str
    alt_text: str | None
    sort_order: int
    is_primary: bool


class ProductVariantResponse(BaseModel):
    id: UUID
    sku: str
    color: ColorResponse
    size: SizeResponse
    stock_quantity: int
    is_available: bool


class ProductDetailResponse(ProductCardResponse):
    description: str | None
    category: CategoryResponse
    images: list[ProductImageResponse]
    variants: list[ProductVariantResponse]


class ProductDetailEnvelope(BaseModel):
    data: ProductDetailResponse
    meta: dict[str, str]
