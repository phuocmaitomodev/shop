from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import (
    Category,
    Color,
    Product,
    ProductImage,
    ProductVariant,
    Size,
)


SEED_NAMESPACE = UUID("7e945f8d-3377-4f28-a420-88ac1caf613b")
PLACEHOLDER_IMAGE_PATH = "/media/placeholders/catalog-product.svg"


def stable_id(entity: str, key: str) -> UUID:
    return uuid5(SEED_NAMESPACE, f"{entity}:{key}")


@dataclass(frozen=True)
class CategorySeed:
    slug: str
    name: str
    description: str
    sort_order: int

    @property
    def id(self) -> UUID:
        return stable_id("category", self.slug)


@dataclass(frozen=True)
class ColorSeed:
    slug: str
    name: str
    hex_code: str

    @property
    def id(self) -> UUID:
        return stable_id("color", self.slug)


@dataclass(frozen=True)
class SizeSeed:
    code: str
    name: str
    sort_order: int

    @property
    def id(self) -> UUID:
        return stable_id("size", self.code)


@dataclass(frozen=True)
class VariantSeed:
    color_slug: str
    size_code: str
    stock_quantity: int


@dataclass(frozen=True)
class ProductSeed:
    sku: str
    slug: str
    name: str
    description: str
    category_slug: str
    price: int
    sale_price: int | None
    variants: tuple[VariantSeed, ...]
    image_path: str = PLACEHOLDER_IMAGE_PATH

    @property
    def id(self) -> UUID:
        return stable_id("product", self.sku)


@dataclass(frozen=True)
class VerificationReport:
    ok: bool
    counts: dict[str, int]
    errors: tuple[str, ...]


class SeedConflictError(RuntimeError):
    """Raised when a canonical natural key belongs to non-seed data."""


CATEGORIES = (
    CategorySeed("ao-thun", "Áo thun", "Áo thun mặc hằng ngày, dễ phối đồ.", 1),
    CategorySeed("ao-so-mi", "Áo sơ mi", "Áo sơ mi phù hợp công sở và dạo phố.", 2),
    CategorySeed("quan", "Quần", "Quần dài và quần short với nhiều phom dáng.", 3),
    CategorySeed("vay-dam", "Váy đầm", "Váy đầm nữ cho công sở và dịp cuối tuần.", 4),
)

COLORS = (
    ColorSeed("den", "Đen", "#111111"),
    ColorSeed("trang", "Trắng", "#FFFFFF"),
    ColorSeed("xanh-navy", "Xanh navy", "#1F3A5F"),
    ColorSeed("be", "Be", "#D6C3A5"),
    ColorSeed("hong", "Hồng", "#E8A0B4"),
)

SIZES = (
    SizeSeed("XS", "Extra Small", 1),
    SizeSeed("S", "Small", 2),
    SizeSeed("M", "Medium", 3),
    SizeSeed("L", "Large", 4),
    SizeSeed("XL", "Extra Large", 5),
)

_PRODUCT_ROWS = (
    ("AT-001", "ao-thun-cotton-co-ban", "Áo thun cotton cơ bản", "Áo thun cotton mềm, thấm hút tốt, phù hợp mặc hằng ngày.", "ao-thun", 249_000, 199_000),
    ("AT-002", "ao-thun-oversize-pho-thi", "Áo thun oversize phố thị", "Phom oversize thoải mái với chất vải dày vừa, hợp phong cách đường phố.", "ao-thun", 329_000, None),
    ("AT-003", "ao-thun-the-thao-thoang-khi", "Áo thun thể thao thoáng khí", "Vải nhanh khô và thoáng khí dành cho vận động nhẹ hoặc đi bộ.", "ao-thun", 379_000, 319_000),
    ("AT-004", "ao-thun-ke-ngang-hai-quan", "Áo thun kẻ ngang hải quân", "Họa tiết kẻ ngang cổ điển, dễ phối cùng jeans và quần short.", "ao-thun", 299_000, None),
    ("AT-005", "ao-thun-polo-pique", "Áo polo pique tối giản", "Áo polo dệt pique đứng phom, phù hợp đi làm và gặp gỡ cuối tuần.", "ao-thun", 449_000, 399_000),
    ("SM-001", "so-mi-oxford-trang", "Sơ mi Oxford trắng", "Sơ mi Oxford bền màu, cổ button-down và phom regular lịch sự.", "ao-so-mi", 549_000, None),
    ("SM-002", "so-mi-linen-xanh-navy", "Sơ mi linen xanh navy", "Chất linen pha nhẹ và thoáng, thích hợp thời tiết nóng.", "ao-so-mi", 649_000, 579_000),
    ("SM-003", "so-mi-lua-hong-nhat", "Sơ mi lụa hồng nhạt", "Bề mặt mềm rủ, màu hồng nhạt thanh lịch cho trang phục công sở.", "ao-so-mi", 729_000, None),
    ("SM-004", "so-mi-ke-caro-be", "Sơ mi kẻ caro be", "Họa tiết caro nhỏ tông be, có thể mặc riêng hoặc khoác ngoài.", "ao-so-mi", 599_000, 499_000),
    ("SM-005", "so-mi-den-co-tru", "Sơ mi đen cổ trụ", "Thiết kế cổ trụ tối giản, chất vải ít nhăn và dễ chăm sóc.", "ao-so-mi", 579_000, None),
    ("QU-001", "quan-jeans-ong-dung", "Quần jeans ống đứng", "Denim co giãn nhẹ, cạp vừa và ống đứng dễ phối nhiều kiểu áo.", "quan", 699_000, 629_000),
    ("QU-002", "quan-chino-be", "Quần chino màu be", "Quần chino phom gọn với vải cotton twill bền, phù hợp đi làm.", "quan", 649_000, None),
    ("QU-003", "quan-short-the-thao", "Quần short thể thao", "Quần short nhẹ, có túi khóa kéo và cạp chun linh hoạt.", "quan", 359_000, 299_000),
    ("QU-004", "quan-tay-den-xep-ly", "Quần tây đen xếp ly", "Quần tây xếp ly một đường, phom suông và bề mặt ít nhăn.", "quan", 749_000, None),
    ("QU-005", "quan-cargo-xanh-navy", "Quần cargo xanh navy", "Quần cargo nhiều túi, phom rộng vừa cho hoạt động ngoài trời.", "quan", 789_000, 699_000),
    ("VD-001", "dam-midi-hoa-nhi", "Đầm midi hoa nhí", "Đầm midi hoa nhí có eo điều chỉnh, phù hợp dạo phố cuối tuần.", "vay-dam", 849_000, 749_000),
    ("VD-002", "vay-chu-a-mau-den", "Váy chữ A màu đen", "Váy chữ A tối giản, độ dài trên gối và có lớp lót mềm.", "vay-dam", 679_000, None),
    ("VD-003", "dam-linen-mau-be", "Đầm linen màu be", "Đầm linen dáng suông thoáng mát với hai túi tiện dụng.", "vay-dam", 899_000, 799_000),
    ("VD-004", "dam-cong-so-xanh-navy", "Đầm công sở xanh navy", "Đầm cổ vuông thanh lịch, đường chiết eo gọn và vải ít nhăn.", "vay-dam", 949_000, None),
    ("VD-005", "dam-maxi-hong-pastel", "Đầm maxi hồng pastel", "Đầm maxi nhiều tầng nhẹ nhàng, phù hợp kỳ nghỉ và sự kiện ban ngày.", "vay-dam", 1_090_000, 949_000),
)


def _variants_for(index: int) -> tuple[VariantSeed, ...]:
    colors = tuple(color.slug for color in COLORS)
    sizes = tuple(size.code for size in SIZES)
    if index == len(_PRODUCT_ROWS) - 1:
        stocks = (0, 0, 0)
    else:
        stocks = ((index * 3) % 12 + 1, 0, (index * 5) % 9 + 2)
    return tuple(
        VariantSeed(colors[(index + offset) % len(colors)], sizes[(index + offset) % len(sizes)], stock)
        for offset, stock in enumerate(stocks)
    )


CATALOG_PRODUCTS = tuple(
    ProductSeed(*row, variants=_variants_for(index))
    for index, row in enumerate(_PRODUCT_ROWS)
)

SEED_PUBLISHED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def _upsert_by_id(
    session: AsyncSession, model: type[Any], entity_id: UUID, values: dict[str, Any]
) -> Any:
    entity = await session.get(model, entity_id)
    if entity is None:
        entity = model(id=entity_id, **values)
        session.add(entity)
    else:
        for field, value in values.items():
            setattr(entity, field, value)
    return entity


async def _assert_no_key_conflicts(
    session: AsyncSession,
    model: type[Any],
    key_name: str,
    expected_ids: dict[str, UUID],
    label: str,
) -> None:
    key_column = getattr(model, key_name)
    rows = (
        await session.execute(
            select(model.id, key_column).where(key_column.in_(tuple(expected_ids)))
        )
    ).all()
    for entity_id, key in rows:
        if entity_id != expected_ids[key]:
            raise SeedConflictError(
                f"{label} {key_name} '{key}' belongs to non-seed row {entity_id}"
            )


async def _assert_canonical_ids(
    session: AsyncSession,
    model: type[Any],
    expected: dict[UUID, dict[str, Any]],
    label: str,
) -> None:
    entities = (
        await session.scalars(select(model).where(model.id.in_(tuple(expected))))
    ).all()
    for entity in entities:
        mismatched = [
            field
            for field, value in expected[entity.id].items()
            if getattr(entity, field) != value
        ]
        if mismatched:
            raise SeedConflictError(
                f"canonical {label} id {entity.id} belongs to a row with different "
                f"{', '.join(mismatched)}"
            )


async def _assert_no_seed_conflicts(session: AsyncSession) -> None:
    await _assert_canonical_ids(
        session,
        Category,
        {category.id: {"slug": category.slug} for category in CATEGORIES},
        "category",
    )
    await _assert_canonical_ids(
        session,
        Color,
        {color.id: {"slug": color.slug} for color in COLORS},
        "color",
    )
    await _assert_canonical_ids(
        session,
        Size,
        {size.id: {"code": size.code} for size in SIZES},
        "size",
    )
    await _assert_canonical_ids(
        session,
        Product,
        {
            product.id: {"sku": product.sku, "slug": product.slug}
            for product in CATALOG_PRODUCTS
        },
        "product",
    )
    await _assert_canonical_ids(
        session,
        ProductImage,
        {
            stable_id("image", product.sku): {
                "product_id": product.id,
                "file_path": product.image_path,
            }
            for product in CATALOG_PRODUCTS
        },
        "image",
    )
    expected_variants: dict[UUID, dict[str, Any]] = {}
    for product in CATALOG_PRODUCTS:
        for variant in product.variants:
            variant_key = f"{product.sku}:{variant.color_slug}:{variant.size_code}"
            expected_variants[stable_id("variant", variant_key)] = {
                "product_id": product.id,
                "color_id": stable_id("color", variant.color_slug),
                "size_id": stable_id("size", variant.size_code),
                "variant_sku": "-".join(
                    (product.sku, variant.color_slug.upper(), variant.size_code)
                ),
            }
    await _assert_canonical_ids(
        session, ProductVariant, expected_variants, "variant"
    )

    await _assert_no_key_conflicts(
        session,
        Category,
        "slug",
        {category.slug: category.id for category in CATEGORIES},
        "category",
    )
    await _assert_no_key_conflicts(
        session,
        Color,
        "slug",
        {color.slug: color.id for color in COLORS},
        "color",
    )
    await _assert_no_key_conflicts(
        session,
        Size,
        "code",
        {size.code: size.id for size in SIZES},
        "size",
    )
    await _assert_no_key_conflicts(
        session,
        Product,
        "sku",
        {product.sku: product.id for product in CATALOG_PRODUCTS},
        "product",
    )
    await _assert_no_key_conflicts(
        session,
        Product,
        "slug",
        {product.slug: product.id for product in CATALOG_PRODUCTS},
        "product",
    )
    variant_ids = {}
    for product in CATALOG_PRODUCTS:
        for variant in product.variants:
            sku = "-".join(
                (product.sku, variant.color_slug.upper(), variant.size_code)
            )
            variant_ids[sku] = stable_id(
                "variant", f"{product.sku}:{variant.color_slug}:{variant.size_code}"
            )
    await _assert_no_key_conflicts(
        session, ProductVariant, "variant_sku", variant_ids, "variant"
    )


async def seed_catalog(session: AsyncSession) -> None:
    """Make the canonical demo catalog converge to one stable state."""
    await _assert_no_seed_conflicts(session)
    for category in CATEGORIES:
        await _upsert_by_id(
            session,
            Category,
            category.id,
            {
                "slug": category.slug,
                "name": category.name,
                "description": category.description,
                "sort_order": category.sort_order,
                "is_active": True,
            },
        )
    for color in COLORS:
        await _upsert_by_id(
            session,
            Color,
            color.id,
            {
                "slug": color.slug,
                "name": color.name,
                "hex_code": color.hex_code,
                "is_active": True,
            },
        )
    for size in SIZES:
        await _upsert_by_id(
            session,
            Size,
            size.id,
            {
                "code": size.code,
                "name": size.name,
                "sort_order": size.sort_order,
                "is_active": True,
            },
        )
    await session.flush()

    category_ids = {category.slug: category.id for category in CATEGORIES}
    color_ids = {color.slug: color.id for color in COLORS}
    size_ids = {size.code: size.id for size in SIZES}
    for product in CATALOG_PRODUCTS:
        await _upsert_by_id(
            session,
            Product,
            product.id,
            {
                "category_id": category_ids[product.category_slug],
                "sku": product.sku,
                "slug": product.slug,
                "name": product.name,
                "description": product.description,
                "price": product.price,
                "sale_price": product.sale_price,
                "is_active": True,
                "published_at": SEED_PUBLISHED_AT,
                "deleted_at": None,
            },
        )
        await _upsert_by_id(
            session,
            ProductImage,
            stable_id("image", product.sku),
            {
                "product_id": product.id,
                "file_path": product.image_path,
                "alt_text": f"Ảnh minh họa {product.name}",
                "sort_order": 0,
                "is_primary": True,
            },
        )
        for variant in product.variants:
            variant_key = f"{product.sku}:{variant.color_slug}:{variant.size_code}"
            await _upsert_by_id(
                session,
                ProductVariant,
                stable_id("variant", variant_key),
                {
                    "product_id": product.id,
                    "color_id": color_ids[variant.color_slug],
                    "size_id": size_ids[variant.size_code],
                    "variant_sku": "-".join(
                        (product.sku, variant.color_slug.upper(), variant.size_code)
                    ),
                    "stock_quantity": variant.stock_quantity,
                    "is_active": True,
                    "version": 1,
                },
            )
    await session.flush()


async def catalog_snapshot(session: AsyncSession) -> tuple[tuple[Any, ...], ...]:
    """Return identity and business fields owned by this seed, excluding timestamps."""
    product_ids = tuple(product.id for product in CATALOG_PRODUCTS)
    rows: list[tuple[Any, ...]] = []
    queries = (
        select(
            Category.id,
            Category.slug,
            Category.name,
            Category.description,
            Category.sort_order,
            Category.is_active,
        )
        .where(Category.id.in_(tuple(category.id for category in CATEGORIES)))
        .order_by(Category.id),
        select(Color.id, Color.slug, Color.name, Color.hex_code, Color.is_active)
        .where(Color.id.in_(tuple(color.id for color in COLORS)))
        .order_by(Color.id),
        select(Size.id, Size.code, Size.name, Size.sort_order, Size.is_active)
        .where(Size.id.in_(tuple(size.id for size in SIZES)))
        .order_by(Size.id),
        select(
            Product.id,
            Product.category_id,
            Product.sku,
            Product.slug,
            Product.name,
            Product.description,
            Product.price,
            Product.sale_price,
            Product.is_active,
            Product.published_at,
            Product.deleted_at,
        ).where(Product.id.in_(product_ids)).order_by(Product.id),
        select(
            ProductImage.id,
            ProductImage.product_id,
            ProductImage.file_path,
            ProductImage.alt_text,
            ProductImage.sort_order,
            ProductImage.is_primary,
        ).where(ProductImage.product_id.in_(product_ids)).order_by(ProductImage.id),
        select(
            ProductVariant.id,
            ProductVariant.product_id,
            ProductVariant.color_id,
            ProductVariant.size_id,
            ProductVariant.variant_sku,
            ProductVariant.stock_quantity,
            ProductVariant.is_active,
            ProductVariant.version,
        ).where(ProductVariant.product_id.in_(product_ids)).order_by(ProductVariant.id),
    )
    for query in queries:
        rows.append(tuple(tuple(row) for row in (await session.execute(query)).all()))
    return tuple(rows)


async def verify_catalog(session: AsyncSession) -> VerificationReport:
    """Validate canonical identities, required fields, relations, money, and stock."""
    errors: list[str] = []
    product_ids = tuple(product.id for product in CATALOG_PRODUCTS)
    category_ids = {category.slug: category.id for category in CATEGORIES}
    color_ids = {color.slug: color.id for color in COLORS}
    size_ids = {size.code: size.id for size in SIZES}

    categories = {
        category.id: category
        for category in (
            await session.scalars(
                select(Category).where(
                    Category.id.in_(tuple(category_ids.values()))
                )
            )
        ).all()
    }
    colors = {
        color.id: color
        for color in (
            await session.scalars(
                select(Color).where(Color.id.in_(tuple(color_ids.values())))
            )
        ).all()
    }
    sizes = {
        size.id: size
        for size in (
            await session.scalars(
                select(Size).where(Size.id.in_(tuple(size_ids.values())))
            )
        ).all()
    }
    products = {
        product.id: product
        for product in (
            await session.scalars(select(Product).where(Product.id.in_(product_ids)))
        ).all()
    }
    images = (
        await session.scalars(
            select(ProductImage).where(ProductImage.product_id.in_(product_ids))
        )
    ).all()
    variants = (
        await session.scalars(
            select(ProductVariant).where(ProductVariant.product_id.in_(product_ids))
        )
    ).all()
    image_by_product = {image.product_id: image for image in images}
    variant_by_sku = {variant.variant_sku: variant for variant in variants}

    if len(categories) < 4:
        errors.append(f"expected at least 4 canonical categories, found {len(categories)}")
    if len(products) < 20:
        errors.append(f"expected at least 20 canonical products, found {len(products)}")

    for expected in CATEGORIES:
        actual = categories.get(expected.id)
        if actual is None:
            errors.append(f"missing category {expected.slug}")
        elif (
            actual.name != expected.name
            or actual.slug != expected.slug
            or actual.sort_order != expected.sort_order
            or not actual.is_active
        ):
            errors.append(f"invalid category {expected.slug}")
        elif actual.description != expected.description:
            errors.append(f"invalid category description for {expected.slug}")

    for expected in COLORS:
        actual = colors.get(expected.id)
        if (
            actual is None
            or actual.slug != expected.slug
            or actual.name != expected.name
            or actual.hex_code != expected.hex_code
            or not actual.is_active
        ):
            errors.append(f"invalid color {expected.slug}")

    for expected in SIZES:
        actual = sizes.get(expected.id)
        if (
            actual is None
            or actual.code != expected.code
            or actual.name != expected.name
            or actual.sort_order != expected.sort_order
            or not actual.is_active
        ):
            errors.append(f"invalid size {expected.code}")

    for expected in CATALOG_PRODUCTS:
        actual = products.get(expected.id)
        if actual is None:
            errors.append(f"missing product {expected.sku}")
            continue
        if actual.slug != expected.slug or actual.sku != expected.sku:
            errors.append(f"unstable slug/SKU for product {expected.sku}")
        if not actual.name:
            errors.append(f"missing name for product {expected.sku}")
        if not actual.description or not actual.description.strip():
            errors.append(f"missing description for product {expected.sku}")
        if (
            actual.name != expected.name
            or actual.description != expected.description
            or actual.price != expected.price
            or actual.sale_price != expected.sale_price
        ):
            errors.append(f"invalid canonical product fields for {expected.sku}")
        if actual.category_id != category_ids[expected.category_slug]:
            errors.append(f"invalid category relationship for product {expected.sku}")
        if actual.price <= 0 or (
            actual.sale_price is not None
            and not 0 < actual.sale_price < actual.price
        ):
            errors.append(f"invalid price for product {expected.sku}")
        if not actual.is_active or actual.deleted_at is not None:
            errors.append(f"product {expected.sku} is not publicly visible")

        image = image_by_product.get(expected.id)
        if (
            image is None
            or image.file_path != expected.image_path
            or image.alt_text != f"Ảnh minh họa {expected.name}"
            or image.sort_order != 0
            or not image.is_primary
        ):
            errors.append(f"invalid primary image for product {expected.sku}")

        for expected_variant in expected.variants:
            variant_sku = "-".join(
                (
                    expected.sku,
                    expected_variant.color_slug.upper(),
                    expected_variant.size_code,
                )
            )
            variant = variant_by_sku.get(variant_sku)
            if variant is None:
                errors.append(f"missing variant {variant_sku}")
                continue
            if (
                variant.product_id != expected.id
                or variant.color_id != color_ids[expected_variant.color_slug]
                or variant.size_id != size_ids[expected_variant.size_code]
            ):
                errors.append(f"invalid relationship for variant {variant_sku}")
            if variant.stock_quantity < 0:
                errors.append(f"invalid stock for variant {variant_sku}")
            if variant.stock_quantity != expected_variant.stock_quantity:
                errors.append(f"invalid canonical stock for variant {variant_sku}")
            if not variant.is_active or variant.version <= 0:
                errors.append(f"inactive or invalid version for variant {variant_sku}")

    if len(images) != len(CATALOG_PRODUCTS):
        errors.append(
            f"expected exactly {len(CATALOG_PRODUCTS)} seed images, found {len(images)}"
        )
    expected_variant_count = sum(
        len(product.variants) for product in CATALOG_PRODUCTS
    )
    if len(variants) != expected_variant_count:
        errors.append(
            f"expected exactly {expected_variant_count} seed variants, found {len(variants)}"
        )

    duplicate_product_slugs = (
        await session.execute(
            select(Product.slug)
            .group_by(Product.slug)
            .having(func.count(Product.id) > 1)
        )
    ).all()
    if duplicate_product_slugs:
        errors.append("duplicate product slugs detected")

    counts = {
        "categories": len(categories),
        "products": len(products),
        "images": len(images),
        "variants": len(variants),
    }
    return VerificationReport(not errors, counts, tuple(errors))


async def verify_catalog_idempotence(session: AsyncSession) -> VerificationReport:
    """Run the seed once more and prove that its owned state does not change."""
    before_report = await verify_catalog(session)
    before = await catalog_snapshot(session)
    await seed_catalog(session)
    after = await catalog_snapshot(session)
    after_report = await verify_catalog(session)

    errors = list(before_report.errors)
    errors.extend(error for error in after_report.errors if error not in errors)
    if before != after:
        errors.append("catalog snapshot changed after reseeding")
    return VerificationReport(not errors, after_report.counts, tuple(errors))
