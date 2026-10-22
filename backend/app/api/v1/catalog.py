from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError
from app.db.session import get_db_session
from app.models.catalog import Category, Product, ProductLabel, ProductVariant
from app.schemas.catalog import (
    CategoryListEnvelope,
    CategoryResponse,
    ColorResponse,
    ProductCardResponse,
    ProductDetailEnvelope,
    ProductDetailResponse,
    ProductImageResponse,
    ProductListEnvelope,
    ProductPageData,
    ProductVariantResponse,
    SizeResponse,
)
from app.schemas.common import ErrorEnvelope

router = APIRouter(tags=["catalog"])


def _request_meta(request: Request) -> dict[str, str]:
    return {"request_id": request.state.request_id}


def _category_response(category: Category) -> CategoryResponse:
    return CategoryResponse(
        id=category.id,
        name=category.name,
        slug=category.slug,
        description=category.description,
        sort_order=category.sort_order,
    )


def _active_variants(product: Product) -> list[ProductVariant]:
    return sorted(
        (
            variant
            for variant in product.variants
            if variant.is_active and variant.color.is_active and variant.size.is_active
        ),
        key=lambda variant: variant.variant_sku,
    )


def _labels(product: Product) -> list[str]:
    return sorted(link.label.display_name for link in product.label_links)


def _images(product: Product):
    return sorted(product.images, key=lambda image: (image.sort_order, str(image.id)))


def _card_response(product: Product) -> ProductCardResponse:
    images = _images(product)
    primary_image = next((image for image in images if image.is_primary), None)
    if primary_image is None and images:
        primary_image = images[0]

    available_variants = [
        variant for variant in _active_variants(product) if variant.stock_quantity > 0
    ]
    sizes_by_id = {variant.size.id: variant.size for variant in available_variants}
    colors_by_id = {variant.color.id: variant.color for variant in available_variants}

    return ProductCardResponse(
        id=product.id,
        slug=product.slug,
        sku=product.sku,
        name=product.name,
        image_url=primary_image.file_path if primary_image is not None else None,
        price=product.price,
        sale_price=product.sale_price,
        effective_price=product.sale_price if product.sale_price is not None else product.price,
        labels=_labels(product),
        available_sizes=[
            size.code
            for size in sorted(sizes_by_id.values(), key=lambda size: size.sort_order)
        ],
        available_colors=[
            ColorResponse(id=color.id, name=color.name, hex_code=color.hex_code)
            for color in sorted(colors_by_id.values(), key=lambda color: color.name)
        ],
    )


def _product_load_options():
    return (
        selectinload(Product.category),
        selectinload(Product.images),
        selectinload(Product.variants).selectinload(ProductVariant.color),
        selectinload(Product.variants).selectinload(ProductVariant.size),
        selectinload(Product.label_links).selectinload(ProductLabel.label),
    )


@router.get("/categories", response_model=CategoryListEnvelope)
async def list_categories(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    categories = (
        await session.scalars(
            select(Category)
            .where(Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.name, Category.id)
        )
    ).all()
    return {
        "data": [_category_response(category) for category in categories],
        "meta": _request_meta(request),
    }


@router.get(
    "/products",
    response_model=ProductListEnvelope,
    responses={
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": ErrorEnvelope,
            "description": "Dữ liệu phân trang không hợp lệ.",
        }
    },
)
async def list_products(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    public_filter = (
        Product.is_active.is_(True),
        Product.deleted_at.is_(None),
        Category.is_active.is_(True),
    )
    total = await session.scalar(
        select(func.count())
        .select_from(Product)
        .join(Category, Category.id == Product.category_id)
        .where(*public_filter)
    )
    products = (
        await session.scalars(
            select(Product)
            .join(Category, Category.id == Product.category_id)
            .where(*public_filter)
            .options(*_product_load_options())
            .order_by(Product.name, Product.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "data": ProductPageData(
            items=[_card_response(product) for product in products],
            page=page,
            page_size=page_size,
            total=total or 0,
        ),
        "meta": _request_meta(request),
    }


@router.get(
    "/products/{slug}",
    response_model=ProductDetailEnvelope,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorEnvelope,
            "description": "Không tìm thấy sản phẩm đang hoạt động.",
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": ErrorEnvelope,
            "description": "Slug không hợp lệ.",
        },
    },
)
async def get_product_detail(
    slug: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    product = await session.scalar(
        select(Product)
        .join(Category, Category.id == Product.category_id)
        .where(
            Product.slug == slug,
            Product.is_active.is_(True),
            Product.deleted_at.is_(None),
            Category.is_active.is_(True),
        )
        .options(*_product_load_options())
    )
    if product is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="PRODUCT_NOT_FOUND",
            message="Không tìm thấy sản phẩm.",
        )

    card = _card_response(product)
    detail = ProductDetailResponse(
        **card.model_dump(),
        description=product.description,
        category=_category_response(product.category),
        images=[
            ProductImageResponse(
                id=image.id,
                url=image.file_path,
                alt_text=image.alt_text,
                sort_order=image.sort_order,
                is_primary=image.is_primary,
            )
            for image in _images(product)
        ],
        variants=[
            ProductVariantResponse(
                id=variant.id,
                sku=variant.variant_sku,
                color=ColorResponse(
                    id=variant.color.id,
                    name=variant.color.name,
                    hex_code=variant.color.hex_code,
                ),
                size=SizeResponse(
                    id=variant.size.id,
                    code=variant.size.code,
                    name=variant.size.name,
                ),
                stock_quantity=variant.stock_quantity,
                is_available=variant.stock_quantity > 0,
            )
            for variant in _active_variants(product)
        ],
    )
    return {"data": detail, "meta": _request_meta(request)}
