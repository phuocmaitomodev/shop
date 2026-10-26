import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.catalog_seed import (
    CATALOG_PRODUCTS,
    CATEGORIES,
    COLORS,
    PLACEHOLDER_IMAGE_PATH,
    SeedConflictError,
    SIZES,
    catalog_snapshot,
    seed_catalog,
    verify_catalog,
    verify_catalog_idempotence,
)
from app.models.catalog import Category, Color, Product, ProductImage, ProductVariant


def test_seed_definition_covers_mvp_catalog_requirements() -> None:
    assert len(CATALOG_PRODUCTS) == 20
    assert len(CATEGORIES) >= 4
    assert len({product.id for product in CATALOG_PRODUCTS}) == 20
    assert len({product.slug for product in CATALOG_PRODUCTS}) == 20
    assert len({product.sku for product in CATALOG_PRODUCTS}) == 20
    assert {product.category_slug for product in CATALOG_PRODUCTS} == {
        category.slug for category in CATEGORIES
    }
    assert all(product.name and product.description for product in CATALOG_PRODUCTS)
    assert all(product.image_path.endswith(".svg") for product in CATALOG_PRODUCTS)
    assert all(product.price > 0 for product in CATALOG_PRODUCTS)
    assert all(product.variants for product in CATALOG_PRODUCTS)
    assert all(
        variant.color_slug in {color.slug for color in COLORS}
        and variant.size_code in {size.code for size in SIZES}
        and variant.stock_quantity >= 0
        for product in CATALOG_PRODUCTS
        for variant in product.variants
    )
    assert any(
        variant.stock_quantity == 0
        for product in CATALOG_PRODUCTS
        for variant in product.variants
    )
    assert any(
        variant.stock_quantity > 0
        for product in CATALOG_PRODUCTS
        for variant in product.variants
    )


def test_seed_is_idempotent_and_preserves_stable_identity(auth_session_factory) -> None:
    async def seed_twice():
        async with auth_session_factory() as session:
            await seed_catalog(session)
            first = await catalog_snapshot(session)
            await seed_catalog(session)
            second = await catalog_snapshot(session)
            counts = {
                "categories": await session.scalar(select(func.count()).select_from(Category)),
                "products": await session.scalar(select(func.count()).select_from(Product)),
                "images": await session.scalar(select(func.count()).select_from(ProductImage)),
                "variants": await session.scalar(select(func.count()).select_from(ProductVariant)),
            }
            return first, second, counts

    first, second, counts = asyncio.run(seed_twice())

    assert first == second
    assert counts == {
        "categories": 4,
        "products": 20,
        "images": 20,
        "variants": 60,
    }


def test_verifier_reports_invalid_required_catalog_data(auth_session_factory) -> None:
    async def corrupt_and_verify():
        async with auth_session_factory() as session:
            await seed_catalog(session)
            product = await session.get(Product, CATALOG_PRODUCTS[0].id)
            assert product is not None
            product.description = ""
            image = await session.scalar(
                select(ProductImage).where(ProductImage.product_id == product.id)
            )
            assert image is not None
            image.file_path = "/media/placeholders/missing.svg"
            await session.flush()
            return await verify_catalog(session)

    report = asyncio.run(corrupt_and_verify())

    assert report.ok is False
    assert any("description" in error for error in report.errors)
    assert any("image" in error for error in report.errors)


def test_seed_collision_rolls_back_without_replacing_existing_data(
    auth_session_factory,
) -> None:
    async def attempt_seed():
        conflicting_id = uuid4()
        async with auth_session_factory() as session:
            session.add(
                Category(
                    id=conflicting_id,
                    name="Dữ liệu có sẵn",
                    slug=CATEGORIES[0].slug,
                    description="Không thuộc seed.",
                )
            )
            await session.commit()

        async with auth_session_factory() as session:
            with pytest.raises(SeedConflictError, match="category slug"):
                await seed_catalog(session)
            await session.rollback()

        async with auth_session_factory() as session:
            rows = (await session.scalars(select(Category))).all()
            return rows

    categories = asyncio.run(attempt_seed())

    assert [(category.name, category.slug) for category in categories] == [
        ("Dữ liệu có sẵn", CATEGORIES[0].slug)
    ]


def test_seed_placeholder_is_served_as_an_image(auth_client) -> None:
    response = auth_client.get(PLACEHOLDER_IMAGE_PATH)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")


def test_idempotence_verifier_reseeds_and_confirms_unchanged_snapshot(
    auth_session_factory,
) -> None:
    async def verify_twice():
        async with auth_session_factory() as session:
            await seed_catalog(session)
            await session.commit()
        async with auth_session_factory() as session:
            report = await verify_catalog_idempotence(session)
            await session.commit()
            return report

    report = asyncio.run(verify_twice())

    assert report.ok is True
    assert report.errors == ()
    assert report.counts == {
        "categories": 4,
        "products": 20,
        "images": 20,
        "variants": 60,
    }


def test_verifier_rejects_inactive_variant_options(auth_session_factory) -> None:
    async def deactivate_and_verify():
        async with auth_session_factory() as session:
            await seed_catalog(session)
            color = await session.get(Color, COLORS[0].id)
            assert color is not None
            color.is_active = False
            await session.flush()
            return await verify_catalog(session)

    report = asyncio.run(deactivate_and_verify())

    assert report.ok is False
    assert any("color" in error for error in report.errors)


def test_seed_rejects_existing_row_that_uses_a_canonical_uuid(
    auth_session_factory,
) -> None:
    async def attempt_seed():
        async with auth_session_factory() as session:
            session.add(
                Category(
                    id=CATEGORIES[0].id,
                    name="Dữ liệu không thuộc seed",
                    slug="danh-muc-khac",
                    description="Phải được giữ nguyên.",
                )
            )
            await session.commit()

        async with auth_session_factory() as session:
            with pytest.raises(SeedConflictError, match="canonical category id"):
                await seed_catalog(session)
            await session.rollback()

        async with auth_session_factory() as session:
            return await session.get(Category, CATEGORIES[0].id)

    category = asyncio.run(attempt_seed())

    assert category is not None
    assert category.slug == "danh-muc-khac"
    assert category.name == "Dữ liệu không thuộc seed"


def test_verifier_rejects_missing_category_description(auth_session_factory) -> None:
    async def corrupt_and_verify():
        async with auth_session_factory() as session:
            await seed_catalog(session)
            category = await session.get(Category, CATEGORIES[0].id)
            assert category is not None
            category.description = ""
            await session.flush()
            return await verify_catalog(session)

    report = asyncio.run(corrupt_and_verify())

    assert report.ok is False
    assert any("category description" in error for error in report.errors)


def test_seed_rejects_canonical_image_id_with_different_identity_fields(
    auth_session_factory,
) -> None:
    async def replace_image_identity():
        async with auth_session_factory() as session:
            await seed_catalog(session)
            image = await session.scalar(
                select(ProductImage).where(
                    ProductImage.product_id == CATALOG_PRODUCTS[0].id
                )
            )
            assert image is not None
            image.file_path = "/media/products/unrelated.svg"
            image.is_primary = False
            await session.commit()

        async with auth_session_factory() as session:
            with pytest.raises(SeedConflictError, match="canonical image id"):
                await seed_catalog(session)
            await session.rollback()

    asyncio.run(replace_image_identity())


def test_verifier_rejects_changed_canonical_business_values(
    auth_session_factory,
) -> None:
    async def mutate_and_verify():
        async with auth_session_factory() as session:
            await seed_catalog(session)
            product = await session.get(Product, CATALOG_PRODUCTS[0].id)
            assert product is not None
            product.name = "Tên khác nhưng vẫn hợp lệ"
            product.description = "Mô tả khác nhưng vẫn không rỗng."
            product.price = 888_000
            product.sale_price = 777_000
            variant = await session.scalar(
                select(ProductVariant).where(
                    ProductVariant.product_id == CATALOG_PRODUCTS[0].id
                )
            )
            assert variant is not None
            variant.stock_quantity += 7
            await session.flush()
            return await verify_catalog(session)

    report = asyncio.run(mutate_and_verify())

    assert report.ok is False
    assert any("canonical product fields" in error for error in report.errors)
    assert any("canonical stock" in error for error in report.errors)
