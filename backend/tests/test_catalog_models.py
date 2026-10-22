import asyncio

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.catalog import (
    Category,
    Color,
    Product,
    ProductImage,
    ProductVariant,
    Size,
)


async def _create_catalog_base(session_factory):
    async with session_factory() as session:
        category = Category(name="Áo thun", slug="ao-thun")
        color = Color(name="Đen", slug="den", hex_code="#000000")
        size = Size(code="M", name="Medium", sort_order=2)
        product = Product(
            category=category,
            sku="AT-001",
            slug="ao-thun-basic",
            name="Áo thun basic",
            price=299_000,
            sale_price=249_000,
        )
        session.add_all([category, color, size, product])
        await session.commit()
        return category.id, color.id, size.id, product.id


@pytest.mark.parametrize(
    ("field", "value"),
    [("slug", "ao-thun-basic"), ("sku", "AT-001")],
)
def test_product_slug_and_sku_are_unique(auth_session_factory, field, value) -> None:
    category_id, _, _, _ = asyncio.run(_create_catalog_base(auth_session_factory))

    async def persist_duplicate() -> None:
        async with auth_session_factory() as session:
            duplicate = Product(
                category_id=category_id,
                sku="AT-002",
                slug="ao-thun-khac",
                name="Áo thun khác",
                price=199_000,
            )
            setattr(duplicate, field, value)
            session.add(duplicate)
            with pytest.raises(IntegrityError):
                await session.commit()

    asyncio.run(persist_duplicate())


def test_variant_sku_and_color_size_combination_are_unique(
    auth_session_factory,
) -> None:
    _, color_id, size_id, product_id = asyncio.run(
        _create_catalog_base(auth_session_factory)
    )

    async def persist_variants() -> None:
        async with auth_session_factory() as session:
            session.add(
                ProductVariant(
                    product_id=product_id,
                    color_id=color_id,
                    size_id=size_id,
                    variant_sku="AT-001-DEN-M",
                    stock_quantity=4,
                )
            )
            await session.commit()

        for variant_sku in ("AT-001-DEN-M", "AT-001-DEN-M-OTHER"):
            async with auth_session_factory() as session:
                session.add(
                    ProductVariant(
                        product_id=product_id,
                        color_id=color_id,
                        size_id=size_id,
                        variant_sku=variant_sku,
                        stock_quantity=2,
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.commit()

    asyncio.run(persist_variants())


def test_money_and_stock_constraints_reject_invalid_values(
    auth_session_factory,
) -> None:
    category_id, color_id, size_id, product_id = asyncio.run(
        _create_catalog_base(auth_session_factory)
    )

    async def assert_invalid_rows() -> None:
        async with auth_session_factory() as session:
            session.add(
                Product(
                    category_id=category_id,
                    sku="INVALID-SALE",
                    slug="invalid-sale",
                    name="Giá sai",
                    price=100_000,
                    sale_price=100_000,
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()

        async with auth_session_factory() as session:
            session.add(
                ProductVariant(
                    product_id=product_id,
                    color_id=color_id,
                    size_id=size_id,
                    variant_sku="INVALID-STOCK",
                    stock_quantity=-1,
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    asyncio.run(assert_invalid_rows())


def test_product_allows_at_most_one_primary_image(auth_session_factory) -> None:
    _, _, _, product_id = asyncio.run(_create_catalog_base(auth_session_factory))

    async def persist_primary_images() -> None:
        async with auth_session_factory() as session:
            session.add(
                ProductImage(
                    product_id=product_id,
                    file_path="/media/products/primary-1.jpg",
                    is_primary=True,
                )
            )
            await session.commit()

        async with auth_session_factory() as session:
            session.add(
                ProductImage(
                    product_id=product_id,
                    file_path="/media/products/primary-2.jpg",
                    is_primary=True,
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    asyncio.run(persist_primary_images())
