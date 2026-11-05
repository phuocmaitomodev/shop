import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.catalog import (
    Category,
    Color,
    Label,
    Product,
    ProductImage,
    ProductLabel,
    ProductVariant,
    Size,
)


@pytest.fixture
def seeded_catalog(auth_session_factory):
    async def seed():
        async with auth_session_factory() as session:
            shirts = Category(
                name="Áo thun", slug="ao-thun", description="Áo thun nam nữ", sort_order=1
            )
            hidden_category = Category(
                name="Ẩn", slug="an", sort_order=2, is_active=False
            )
            black = Color(name="Đen", slug="den", hex_code="#000000")
            red = Color(name="Đỏ", slug="do", hex_code="#FF0000")
            medium = Size(code="M", name="Medium", sort_order=2)
            large = Size(code="L", name="Large", sort_order=3)
            new_label = Label(code="new", display_name="Mới")
            sale_label = Label(code="sale", display_name="Giảm giá")
            product = Product(
                category=shirts,
                sku="AT-001",
                slug="ao-thun-basic",
                name="Áo thun basic",
                description="Áo thun cotton mềm mại.",
                price=299_000,
                sale_price=249_000,
                published_at=datetime.now(timezone.utc),
            )
            inactive_product = Product(
                category=shirts,
                sku="AT-002",
                slug="ao-thun-an",
                name="Áo thun ẩn",
                price=199_000,
                is_active=False,
            )
            hidden_category_product = Product(
                category=hidden_category,
                sku="AT-003",
                slug="san-pham-danh-muc-an",
                name="Sản phẩm danh mục ẩn",
                price=159_000,
            )
            session.add_all(
                [
                    shirts,
                    hidden_category,
                    black,
                    red,
                    medium,
                    large,
                    new_label,
                    sale_label,
                    product,
                    inactive_product,
                    hidden_category_product,
                ]
            )
            await session.flush()
            session.add_all(
                [
                    ProductImage(
                        product_id=product.id,
                        file_path="/media/products/ao-thun-basic-chinh.jpg",
                        alt_text="Áo thun basic màu đen",
                        sort_order=0,
                        is_primary=True,
                    ),
                    ProductImage(
                        product_id=product.id,
                        file_path="/media/products/ao-thun-basic-sau.jpg",
                        alt_text="Mặt sau áo thun basic",
                        sort_order=1,
                    ),
                    ProductLabel(product_id=product.id, label_id=new_label.id),
                    ProductLabel(product_id=product.id, label_id=sale_label.id),
                    ProductVariant(
                        product_id=product.id,
                        color_id=black.id,
                        size_id=medium.id,
                        variant_sku="AT-001-DEN-M",
                        stock_quantity=5,
                    ),
                    ProductVariant(
                        product_id=product.id,
                        color_id=red.id,
                        size_id=large.id,
                        variant_sku="AT-001-DO-L",
                        stock_quantity=0,
                    ),
                    ProductVariant(
                        product_id=product.id,
                        color_id=red.id,
                        size_id=medium.id,
                        variant_sku="AT-001-DO-M-INACTIVE",
                        stock_quantity=9,
                        is_active=False,
                    ),
                ]
            )
            await session.commit()
            return {
                "product_id": str(product.id),
                "inactive_slug": inactive_product.slug,
                "hidden_category_product_slug": hidden_category_product.slug,
            }

    return asyncio.run(seed())


@pytest.fixture
def category_filter_catalog(auth_session_factory, seeded_catalog):
    async def seed():
        async with auth_session_factory() as session:
            shirts = await session.scalar(
                select(Category).where(Category.slug == "ao-thun")
            )
            assert shirts is not None

            near_match_category = Category(
                name="Áo thun nam", slug="ao-thun-nam", sort_order=2
            )
            black = await session.scalar(select(Color).where(Color.slug == "den"))
            red = await session.scalar(select(Color).where(Color.slug == "do"))
            medium = await session.scalar(select(Size).where(Size.code == "M"))
            large = await session.scalar(select(Size).where(Size.code == "L"))
            assert black is not None
            assert red is not None
            assert medium is not None
            assert large is not None

            matching_product = Product(
                category=shirts,
                sku="AT-004",
                slug="ao-thun-cotton-cao-cap",
                name="Áo thun cotton cao cấp",
                description="Chất cotton thoáng mát.",
                price=279_000,
            )
            wrong_category_product = Product(
                category=near_match_category,
                sku="AT-005",
                slug="ao-thun-nam-form-rong",
                name="Áo thun cotton nam form rộng",
                description="Chất cotton thoáng mát.",
                price=259_000,
            )
            filter_distractors = [
                (
                    Product(
                        category=shirts,
                        sku="AT-006",
                        slug="ao-thun-lua",
                        name="Áo thun lụa",
                        description="Chất liệu lụa.",
                        price=259_000,
                    ),
                    black,
                    medium,
                ),
                (
                    Product(
                        category=shirts,
                        sku="AT-007",
                        slug="ao-thun-cotton-gia-thap",
                        name="Áo thun cotton giá thấp",
                        description="Chất cotton thoáng mát.",
                        price=239_000,
                    ),
                    black,
                    medium,
                ),
                (
                    Product(
                        category=shirts,
                        sku="AT-008",
                        slug="ao-thun-cotton-gia-cao",
                        name="Áo thun cotton giá cao",
                        description="Chất cotton thoáng mát.",
                        price=281_000,
                    ),
                    black,
                    medium,
                ),
                (
                    Product(
                        category=shirts,
                        sku="AT-009",
                        slug="ao-thun-cotton-mau-do",
                        name="Áo thun cotton màu đỏ",
                        description="Chất cotton thoáng mát.",
                        price=259_000,
                    ),
                    red,
                    medium,
                ),
                (
                    Product(
                        category=shirts,
                        sku="AT-010",
                        slug="ao-thun-cotton-size-l",
                        name="Áo thun cotton size L",
                        description="Chất cotton thoáng mát.",
                        price=259_000,
                    ),
                    black,
                    large,
                ),
            ]
            session.add_all(
                [
                    near_match_category,
                    matching_product,
                    wrong_category_product,
                    *(product for product, _, _ in filter_distractors),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    ProductVariant(
                        product=matching_product,
                        color=black,
                        size=medium,
                        variant_sku="AT-004-DEN-M",
                        stock_quantity=3,
                    ),
                    ProductVariant(
                        product=wrong_category_product,
                        color=black,
                        size=medium,
                        variant_sku="AT-005-DEN-M",
                        stock_quantity=3,
                    ),
                    *(
                        ProductVariant(
                            product=product,
                            color=variant_color,
                            size=variant_size,
                            variant_sku=f"{product.sku}-{variant_color.slug.upper()}-{variant_size.code}",
                            stock_quantity=3,
                        )
                        for product, variant_color, variant_size in filter_distractors
                    ),
                ]
            )
            await session.commit()

    asyncio.run(seed())
    return seeded_catalog


def test_list_categories_returns_only_active_sorted_categories(
    auth_client: TestClient, seeded_catalog
) -> None:
    response = auth_client.get("/api/v1/categories")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == [
        {
            "id": body["data"][0]["id"],
            "name": "Áo thun",
            "slug": "ao-thun",
            "description": "Áo thun nam nữ",
            "sort_order": 1,
        }
    ]
    assert body["meta"]["request_id"]


def test_list_products_returns_public_product_cards(
    auth_client: TestClient, seeded_catalog
) -> None:
    response = auth_client.get("/api/v1/products")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["page"] == 1
    assert body["data"]["page_size"] == 20
    assert body["data"]["total"] == 1
    assert len(body["data"]["items"]) == 1
    product = body["data"]["items"][0]
    assert product == {
        "id": seeded_catalog["product_id"],
        "slug": "ao-thun-basic",
        "sku": "AT-001",
        "name": "Áo thun basic",
        "image_url": "/media/products/ao-thun-basic-chinh.jpg",
        "price": 299_000,
        "sale_price": 249_000,
        "effective_price": 249_000,
        "category": {
            "id": product["category"]["id"],
            "name": "Áo thun",
            "slug": "ao-thun",
            "description": "Áo thun nam nữ",
            "sort_order": 1,
        },
        "labels": ["Giảm giá", "Mới"],
        "available_sizes": ["M"],
        "available_colors": [
            {"id": product["available_colors"][0]["id"], "name": "Đen", "hex_code": "#000000"}
        ],
        "in_stock": True,
    }
    assert isinstance(product["price"], int)
    assert "created_at" not in product
    assert "deleted_at" not in product


def test_list_products_filters_by_exact_active_category_slug(
    auth_client: TestClient, category_filter_catalog
) -> None:
    response = auth_client.get("/api/v1/products", params={"category": "ao-thun"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 7
    assert {item["slug"] for item in data["items"]} == {
        "ao-thun-basic",
        "ao-thun-cotton-cao-cap",
        "ao-thun-cotton-gia-cao",
        "ao-thun-cotton-gia-thap",
        "ao-thun-cotton-mau-do",
        "ao-thun-cotton-size-l",
        "ao-thun-lua",
    }
    assert {item["category"]["slug"] for item in data["items"]} == {"ao-thun"}
    assert category_filter_catalog["inactive_slug"] not in {
        item["slug"] for item in data["items"]
    }


def test_category_filter_composes_with_search_price_variant_and_pagination(
    auth_client: TestClient, category_filter_catalog
) -> None:
    response = auth_client.get(
        "/api/v1/products",
        params={
            "category": "ao-thun",
            "q": "cotton",
            "min_price": 240_000,
            "max_price": 280_000,
            "color": "den",
            "size": "M",
            "page": 2,
            "page_size": 1,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["page"] == 2
    assert data["page_size"] == 1
    assert data["total"] == 2
    assert len(data["items"]) == 1
    assert data["items"][0]["slug"] == "ao-thun-cotton-cao-cap"
    assert data["items"][0]["category"]["slug"] == "ao-thun"


@pytest.mark.parametrize("category", ["khong-ton-tai", "an"])
def test_unknown_or_inactive_category_returns_empty_paginated_result(
    auth_client: TestClient, category_filter_catalog, category: str
) -> None:
    response = auth_client.get("/api/v1/products", params={"category": category})

    assert response.status_code == 200
    assert response.json()["data"] == {
        "items": [],
        "page": 1,
        "page_size": 20,
        "total": 0,
    }


def test_product_detail_returns_images_labels_and_active_variant_stock(
    auth_client: TestClient, seeded_catalog
) -> None:
    response = auth_client.get("/api/v1/products/ao-thun-basic")

    assert response.status_code == 200
    product = response.json()["data"]
    assert product["description"] == "Áo thun cotton mềm mại."
    assert product["category"]["slug"] == "ao-thun"
    assert [image["is_primary"] for image in product["images"]] == [True, False]
    assert product["labels"] == ["Giảm giá", "Mới"]
    assert [variant["sku"] for variant in product["variants"]] == [
        "AT-001-DEN-M",
        "AT-001-DO-L",
    ]
    assert product["variants"][0]["color"]["name"] == "Đen"
    assert product["variants"][0]["size"]["code"] == "M"
    assert product["variants"][0]["stock_quantity"] == 5
    assert product["variants"][0]["is_available"] is True
    assert product["variants"][1]["stock_quantity"] == 0
    assert product["variants"][1]["is_available"] is False
    assert "version" not in product["variants"][0]
    assert "is_active" not in product["variants"][0]


@pytest.mark.parametrize(
    "slug",
    ["khong-ton-tai", "ao-thun-an", "san-pham-danh-muc-an"],
)
def test_product_detail_returns_not_found_for_missing_or_inactive_product(
    auth_client: TestClient, seeded_catalog, slug: str
) -> None:
    response = auth_client.get(f"/api/v1/products/{slug}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
    assert response.json()["meta"]["request_id"]
