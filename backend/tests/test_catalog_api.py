import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

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
