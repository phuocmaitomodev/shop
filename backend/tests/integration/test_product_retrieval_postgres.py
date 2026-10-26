import asyncio
import os
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.catalog import (
    Category,
    Color,
    Product,
    ProductImage,
    ProductVariant,
    Size,
)
from app.models.knowledge import RagChunk, RagDocument
from app.api.v1 import chat as chat_api
from app.db.session import get_db_session
from app.main import create_app
from app.rag.retrieval import ProductRetrievalFilters, retrieve_products
from tests.integration.database_guard import require_fresh_migrated_database


DATABASE_URL = os.getenv("MIGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="MIGRATION_DATABASE_URL is required for PostgreSQL retrieval tests",
)
_QUERY_VECTOR = [1.0] + [0.0] * 767
_SECONDARY_VECTOR = [0.0, 1.0] + [0.0] * 766


@dataclass(frozen=True)
class RetrievalFixture:
    session_factory: async_sessionmaker
    product_ids: dict[str, UUID]
    target_variant_id: UUID


@pytest.fixture(scope="module")
def retrieval_fixture():
    assert DATABASE_URL is not None
    require_fresh_migrated_database(DATABASE_URL)
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def seed() -> RetrievalFixture:
        async with session_factory() as session, session.begin():
            await session.execute(
                text(
                    "TRUNCATE rag_chunks, rag_index_jobs, rag_documents, "
                    "product_labels, product_images, product_variants, products, "
                    "labels, colors, sizes, categories CASCADE"
                )
            )
            shirts = Category(name="Áo", slug="ao", is_active=True)
            dresses = Category(name="Váy", slug="vay", is_active=True)
            black = Color(name="Đen", slug="den", is_active=True)
            red = Color(name="Đỏ", slug="do", is_active=True)
            medium = Size(code="M", name="Medium", sort_order=1, is_active=True)
            large = Size(code="L", name="Large", sort_order=2, is_active=True)
            session.add_all([shirts, dresses, black, red, medium, large])
            await session.flush()

            product_ids: dict[str, UUID] = {}
            target_variant_id = UUID(int=0)

            async def add_product(
                key: str,
                *,
                category: Category = shirts,
                price: int = 1_000,
                sale_price: int | None = None,
                variants: tuple[tuple[Color, Size, int], ...] = ((black, medium, 5),),
                document_active: bool = True,
                index_status: str = "indexed",
                chunk_active: bool = True,
                document_version: int = 1,
                chunk_version: int = 1,
                chunk_count: int = 1,
                embedding: list[float] = _SECONDARY_VECTOR,
            ) -> None:
                nonlocal target_variant_id
                product = Product(
                    category_id=category.id,
                    sku=f"RAG-{key.upper()}",
                    slug=key,
                    name=f"Sản phẩm {key}",
                    description=f"Mô tả semantic {key}",
                    price=price,
                    sale_price=sale_price,
                    is_active=True,
                )
                session.add(product)
                await session.flush()
                product_ids[key] = product.id
                session.add(
                    ProductImage(
                        product_id=product.id,
                        file_path=f"/media/{key}.svg",
                        sort_order=0,
                        is_primary=True,
                    )
                )
                for index, (color, size, stock) in enumerate(variants):
                    variant = ProductVariant(
                        product_id=product.id,
                        color_id=color.id,
                        size_id=size.id,
                        variant_sku=f"RAG-{key.upper()}-{index}",
                        stock_quantity=stock,
                        is_active=True,
                    )
                    session.add(variant)
                    await session.flush()
                    if key == "target" and index == 0:
                        target_variant_id = variant.id
                document = RagDocument(
                    source_type="product",
                    source_id=product.id,
                    title=product.name,
                    content_for_embedding=product.description or product.name,
                    source_version=document_version,
                    checksum=key.ljust(64, "0")[:64],
                    index_status=index_status,
                    is_active=document_active,
                )
                session.add(document)
                await session.flush()
                session.add_all(
                    [
                        RagChunk(
                            rag_document_id=document.id,
                            chunk_index=chunk_index,
                            content=(
                                f"{product.description or product.name} {chunk_index}"
                            ),
                            chunk_metadata={},
                            embedding=embedding,
                            embedding_model="stub-deterministic-v1",
                            source_version=chunk_version,
                            is_active=chunk_active,
                        )
                        for chunk_index in range(chunk_count)
                    ]
                )

            await add_product(
                "target",
                sale_price=900,
                chunk_count=3,
                embedding=_QUERY_VECTOR,
            )
            await add_product("wrong-category", category=dresses, sale_price=900)
            await add_product("below-min", price=800)
            await add_product("above-max", price=1_100)
            await add_product("wrong-color", variants=((red, medium, 5),))
            await add_product("wrong-size", variants=((black, large, 5),))
            await add_product(
                "split-variant",
                variants=((black, large, 5), (red, medium, 5)),
            )
            await add_product("inactive-document", document_active=False)
            await add_product("non-indexed-document", index_status="pending")
            await add_product("inactive-chunk", chunk_active=False)
            await add_product(
                "stale-chunk", document_version=2, chunk_version=1
            )

        return RetrievalFixture(session_factory, product_ids, target_variant_id)

    fixture = asyncio.run(seed())
    try:
        yield fixture
    finally:
        asyncio.run(engine.dispose())


def _slugs(fixture: RetrievalFixture, filters: ProductRetrievalFilters) -> set[str]:
    async def retrieve() -> set[str]:
        async with fixture.session_factory() as session:
            products = await retrieve_products(
                session, _QUERY_VECTOR, filters, limit=20
            )
            return {product.slug for product in products}

    return asyncio.run(retrieve())


def test_category_filter_is_independent(retrieval_fixture: RetrievalFixture) -> None:
    slugs = _slugs(retrieval_fixture, ProductRetrievalFilters(category="ao"))

    assert "target" in slugs
    assert "wrong-category" not in slugs


def test_min_price_filter_is_independent(retrieval_fixture: RetrievalFixture) -> None:
    slugs = _slugs(retrieval_fixture, ProductRetrievalFilters(min_price=900))

    assert "target" in slugs
    assert "above-max" in slugs
    assert "below-min" not in slugs


def test_max_price_filter_is_independent(retrieval_fixture: RetrievalFixture) -> None:
    slugs = _slugs(retrieval_fixture, ProductRetrievalFilters(max_price=1_000))

    assert "target" in slugs
    assert "below-min" in slugs
    assert "above-max" not in slugs


def test_color_filter_is_independent(retrieval_fixture: RetrievalFixture) -> None:
    slugs = _slugs(retrieval_fixture, ProductRetrievalFilters(color="den"))

    assert "target" in slugs
    assert "wrong-color" not in slugs


def test_size_filter_is_independent(retrieval_fixture: RetrievalFixture) -> None:
    slugs = _slugs(retrieval_fixture, ProductRetrievalFilters(size="m"))

    assert "target" in slugs
    assert "wrong-size" not in slugs


def test_combined_color_size_requires_one_in_stock_variant(
    retrieval_fixture: RetrievalFixture,
) -> None:
    slugs = _slugs(
        retrieval_fixture,
        ProductRetrievalFilters(color="den", size="m"),
    )

    assert "target" in slugs
    assert "split-variant" not in slugs


def test_retrieval_excludes_ineligible_documents_and_chunks(
    retrieval_fixture: RetrievalFixture,
) -> None:
    slugs = _slugs(retrieval_fixture, ProductRetrievalFilters())

    assert "target" in slugs
    assert "inactive-document" not in slugs
    assert "non-indexed-document" not in slugs
    assert "inactive-chunk" not in slugs
    assert "stale-chunk" not in slugs


def test_entity_limit_is_not_consumed_by_multiple_chunks_from_one_product(
    retrieval_fixture: RetrievalFixture,
) -> None:
    async def retrieve_twice():
        async with retrieval_fixture.session_factory() as session:
            first = await retrieve_products(session, _QUERY_VECTOR, limit=2)
            second = await retrieve_products(session, _QUERY_VECTOR, limit=2)
            return first, second

    first, second = asyncio.run(retrieve_twice())

    assert len(first) == 2
    assert len({product.product_id for product in first}) == 2
    assert [product.product_id for product in first] == [
        product.product_id for product in second
    ]
    assert all(product.product_id == product.source_id for product in first)
    assert all(len(product.chunk_ids) == 1 for product in first)


def test_chat_api_integrates_orchestration_with_postgres_hydration(
    retrieval_fixture: RetrievalFixture, monkeypatch
) -> None:
    class FixedEmbeddingProvider:
        async def embed(self, texts):
            assert texts == ["sản phẩm màu đen size M dưới 1000"]
            return [_QUERY_VECTOR]

    async def override_session():
        async with retrieval_fixture.session_factory() as session:
            yield session

    monkeypatch.setattr(
        chat_api, "_embedding_provider", lambda _settings: FixedEmbeddingProvider()
    )
    application = create_app()
    application.dependency_overrides[get_db_session] = override_session
    with TestClient(application) as client:
        response = client.post(
            "/api/v1/chat",
            json={"message": "Tìm sản phẩm màu đen size M dưới 1000"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ok"
    returned_ids = {UUID(product["id"]) for product in data["products"]}
    assert returned_ids <= {
        retrieval_fixture.product_ids["target"],
        retrieval_fixture.product_ids["below-min"],
        retrieval_fixture.product_ids["wrong-category"],
    }
    assert returned_ids == {
        UUID(source["product_id"]) for source in data["sources"]
    }
    assert all(product["url"].startswith("/san-pham/") for product in data["products"])


def test_price_and_stock_are_hydrated_live_without_reindex(
    retrieval_fixture: RetrievalFixture,
) -> None:
    async def update_and_retrieve():
        async with retrieval_fixture.session_factory() as reader:
            cached_product = await reader.get(
                Product, retrieval_fixture.product_ids["target"]
            )
            cached_variant = await reader.get(
                ProductVariant, retrieval_fixture.target_variant_id
            )
            assert cached_product is not None
            assert cached_variant is not None
            initial = await retrieve_products(
                reader,
                _QUERY_VECTOR,
                ProductRetrievalFilters(category="ao"),
                limit=20,
            )
            initial_target = next(
                product for product in initial if product.slug == "target"
            )
            assert initial_target.effective_price == 900
            assert initial_target.in_stock is True

            async with retrieval_fixture.session_factory() as writer, writer.begin():
                await writer.execute(
                    update(Product)
                    .where(Product.id == retrieval_fixture.product_ids["target"])
                    .values(sale_price=700)
                )
                await writer.execute(
                    update(ProductVariant)
                    .where(ProductVariant.id == retrieval_fixture.target_variant_id)
                    .values(stock_quantity=0)
                )

            assert cached_product.sale_price == 900
            assert cached_variant.stock_quantity == 5
            refreshed = await retrieve_products(
                reader,
                _QUERY_VECTOR,
                ProductRetrievalFilters(category="ao"),
                limit=20,
            )
            return next(
                product for product in refreshed if product.slug == "target"
            )

    target = asyncio.run(update_and_retrieve())

    assert target.effective_price == 700
    assert target.in_stock is False
    assert target.available_colors == ()
    assert target.available_sizes == ()
    assert target.variants[0].stock_quantity == 0
