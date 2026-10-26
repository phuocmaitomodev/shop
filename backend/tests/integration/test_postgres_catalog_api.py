import asyncio
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.session import get_db_session
from app.main import create_app
from app.models.catalog import Category, Color, Product, ProductVariant, Size
from tests.integration.database_guard import (
    mark_fresh_migrated_database,
    require_fresh_migrated_database,
)


DATABASE_URL = os.getenv("CATALOG_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="CATALOG_TEST_DATABASE_URL is required for PostgreSQL catalog API tests",
)


@pytest.fixture(scope="module")
def postgres_catalog_client():
    assert DATABASE_URL is not None
    assert DATABASE_URL.startswith("postgresql+asyncpg://")

    async def validate_test_database() -> None:
        validation_engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
        try:
            async with validation_engine.connect() as connection:
                database_name = await connection.scalar(text("SELECT current_database()"))
                public_tables = set(
                    await connection.scalars(
                        text(
                            "SELECT tablename FROM pg_catalog.pg_tables "
                            "WHERE schemaname = 'public'"
                        )
                    )
                )
            if database_name is None or not database_name.endswith("_test"):
                raise RuntimeError(
                    "CATALOG_TEST_DATABASE_URL must target a dedicated database whose "
                    "name ends with '_test'"
                )
            if public_tables:
                raise RuntimeError(
                    "CATALOG_TEST_DATABASE_URL must target a fresh database without "
                    "public tables"
                )
        finally:
            await validation_engine.dispose()

    asyncio.run(validate_test_database())

    backend_dir = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["DATABASE_URL"] = DATABASE_URL
    migration = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=backend_dir,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert migration.returncode == 0, migration.stdout + migration.stderr
    mark_fresh_migrated_database(DATABASE_URL)
    require_fresh_migrated_database(DATABASE_URL)

    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def seed() -> None:
        async with session_factory() as session, session.begin():
            await session.execute(
                text(
                    "TRUNCATE product_labels, product_images, product_variants, "
                    "products, labels, colors, sizes, categories CASCADE"
                )
            )
            shirts = Category(name="Áo thun", slug="ao-thun", sort_order=1)
            dresses = Category(name="Váy", slug="vay", sort_order=2)
            black = Color(name="Đen", slug="den", hex_code="#000000")
            red = Color(name="Đỏ", slug="do", hex_code="#FF0000")
            medium = Size(code="M", name="Medium", sort_order=1)
            large = Size(code="L", name="Large", sort_order=2)
            session.add_all([shirts, dresses, black, red, medium, large])
            await session.flush()

            products = [
                Product(
                    category_id=shirts.id,
                    sku="PG-AT-001",
                    slug="ao-cotton-basic",
                    name="Áo cotton basic",
                    description="Chất liệu cotton mềm mại",
                    price=300_000,
                    sale_price=250_000,
                    published_at=datetime.now(timezone.utc),
                ),
                Product(
                    category_id=shirts.id,
                    sku="PG-AT-002",
                    slug="ao-premium",
                    name="Áo premium",
                    description="Áo cao cấp",
                    price=500_000,
                    published_at=datetime.now(timezone.utc),
                ),
                Product(
                    category_id=dresses.id,
                    sku="PG-V-001",
                    slug="vay-den",
                    name="Váy đen",
                    description="Váy dự tiệc thanh lịch",
                    price=400_000,
                    sale_price=350_000,
                    published_at=datetime.now(timezone.utc),
                ),
                Product(
                    category_id=shirts.id,
                    sku="PG-AT-003",
                    slug="ao-het-hang",
                    name="Áo hết hàng",
                    description="Mẫu cotton đã hết hàng",
                    price=100_000,
                    published_at=datetime.now(timezone.utc),
                ),
            ]
            session.add_all(products)
            await session.flush()
            session.add_all(
                [
                    ProductVariant(
                        product_id=products[0].id,
                        color_id=black.id,
                        size_id=medium.id,
                        variant_sku="PG-AT-001-DEN-M",
                        stock_quantity=5,
                    ),
                    ProductVariant(
                        product_id=products[1].id,
                        color_id=red.id,
                        size_id=large.id,
                        variant_sku="PG-AT-002-DO-L",
                        stock_quantity=3,
                    ),
                    ProductVariant(
                        product_id=products[2].id,
                        color_id=black.id,
                        size_id=large.id,
                        variant_sku="PG-V-001-DEN-L",
                        stock_quantity=2,
                    ),
                    ProductVariant(
                        product_id=products[3].id,
                        color_id=black.id,
                        size_id=medium.id,
                        variant_sku="PG-AT-003-DEN-M",
                        stock_quantity=0,
                    ),
                ]
            )

    asyncio.run(seed())

    async def override_session():
        async with session_factory() as session:
            yield session

    application = create_app()
    application.dependency_overrides[get_db_session] = override_session
    try:
        with TestClient(application) as client:
            yield client
    finally:
        application.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_postgres_catalog_search_and_pagination(postgres_catalog_client: TestClient) -> None:
    first_page = postgres_catalog_client.get(
        "/api/v1/products", params={"page": 1, "page_size": 2}
    )
    second_page = postgres_catalog_client.get(
        "/api/v1/products", params={"page": 2, "page_size": 2}
    )
    search = postgres_catalog_client.get("/api/v1/products", params={"q": "COTTON"})

    assert first_page.status_code == 200
    assert first_page.json()["data"]["total"] == 4
    assert [item["slug"] for item in first_page.json()["data"]["items"]] == [
        "ao-cotton-basic",
        "ao-het-hang",
    ]
    assert [item["slug"] for item in second_page.json()["data"]["items"]] == [
        "ao-premium",
        "vay-den",
    ]
    assert [item["slug"] for item in search.json()["data"]["items"]] == [
        "ao-cotton-basic",
        "ao-het-hang",
    ]


@pytest.mark.parametrize(
    ("params", "expected_slugs"),
    [
        ({"category": "ao-thun"}, ["ao-cotton-basic", "ao-het-hang", "ao-premium"]),
        ({"min_price": 300_000}, ["ao-premium", "vay-den"]),
        ({"max_price": 250_000}, ["ao-cotton-basic", "ao-het-hang"]),
        ({"color": "den"}, ["ao-cotton-basic", "vay-den"]),
        ({"size": "M"}, ["ao-cotton-basic"]),
    ],
)
def test_postgres_catalog_individual_filters(
    postgres_catalog_client: TestClient,
    params: dict[str, str | int],
    expected_slugs: list[str],
) -> None:
    response = postgres_catalog_client.get("/api/v1/products", params=params)

    assert response.status_code == 200
    assert response.json()["data"]["total"] == len(expected_slugs)
    assert [item["slug"] for item in response.json()["data"]["items"]] == expected_slugs


def test_postgres_catalog_combines_filters_on_one_available_variant(
    postgres_catalog_client: TestClient,
) -> None:
    response = postgres_catalog_client.get(
        "/api/v1/products",
        params={
            "q": "áo",
            "category": "ao-thun",
            "min_price": 400_000,
            "max_price": 600_000,
            "color": "do",
            "size": "L",
        },
    )

    assert response.status_code == 200
    assert [item["slug"] for item in response.json()["data"]["items"]] == [
        "ao-premium"
    ]

    mismatched_variant = postgres_catalog_client.get(
        "/api/v1/products",
        params={"category": "ao-thun", "color": "den", "size": "L"},
    )
    assert mismatched_variant.status_code == 200
    assert mismatched_variant.json()["data"]["items"] == []


def test_postgres_catalog_card_exposes_category_and_stock_state(
    postgres_catalog_client: TestClient,
) -> None:
    response = postgres_catalog_client.get("/api/v1/products")

    assert response.status_code == 200
    items = {item["slug"]: item for item in response.json()["data"]["items"]}
    assert items["ao-cotton-basic"]["category"]["slug"] == "ao-thun"
    assert items["ao-cotton-basic"]["in_stock"] is True
    assert items["ao-het-hang"]["in_stock"] is False


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": 1_000_001},
        {"page_size": 0},
        {"page_size": 101},
        {"min_price": -1},
        {"max_price": 9_223_372_036_854_775_808},
        {"min_price": 500_000, "max_price": 100_000},
    ],
)
def test_postgres_catalog_rejects_invalid_query_parameters(
    postgres_catalog_client: TestClient, params: dict[str, int]
) -> None:
    response = postgres_catalog_client.get("/api/v1/products", params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["meta"]["request_id"]


def test_postgres_catalog_detail_and_missing_slug(
    postgres_catalog_client: TestClient,
) -> None:
    detail = postgres_catalog_client.get("/api/v1/products/ao-cotton-basic")
    missing = postgres_catalog_client.get("/api/v1/products/khong-ton-tai")

    assert detail.status_code == 200
    product = detail.json()["data"]
    assert product["category"]["slug"] == "ao-thun"
    assert product["in_stock"] is True
    assert product["variants"] == [
        {
            "id": product["variants"][0]["id"],
            "sku": "PG-AT-001-DEN-M",
            "color": {
                "id": product["variants"][0]["color"]["id"],
                "name": "Đen",
                "hex_code": "#000000",
            },
            "size": {
                "id": product["variants"][0]["size"]["id"],
                "code": "M",
                "name": "Medium",
            },
            "stock_quantity": 5,
            "is_available": True,
        }
    ]
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
