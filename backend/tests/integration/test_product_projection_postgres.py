import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.catalog import Category, Product
from app.models.knowledge import RagChunk, RagDocument, RagIndexJob
from app.rag.product_projection import sync_product_projections
from app.rag.provider import DeterministicEmbeddingProvider
from app.rag.worker import RagIndexWorker, WorkerOptions


DATABASE_URL = os.getenv("MIGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="MIGRATION_DATABASE_URL is required for PostgreSQL projection tests",
)


def test_postgres_product_projection_reindex_is_idempotent_and_indexable() -> None:
    assert DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        product_id = uuid4()
        category_id = uuid4()
        try:
            async with session_factory() as session, session.begin():
                await session.execute(
                    text(
                        "TRUNCATE rag_chunks, rag_index_jobs, rag_documents, "
                        "products, categories CASCADE"
                    )
                )
                session.add_all(
                    [
                        Category(
                            id=category_id,
                            name="Áo khoác",
                            slug="ao-khoac",
                            is_active=True,
                        ),
                        Product(
                            id=product_id,
                            category_id=category_id,
                            sku="AK-PG-001",
                            slug="ao-khoac-gio-pg",
                            name="Áo khoác gió nhẹ",
                            description="Chống gió nhẹ cho chuyến đi cuối tuần.",
                            price=1_290_000,
                            sale_price=990_000,
                            is_active=True,
                        ),
                    ]
                )

            async with session_factory() as session, session.begin():
                first = await sync_product_projections(session)
            async with session_factory() as session, session.begin():
                second = await sync_product_projections(session)

            assert first.created == 1
            assert second.created == 0
            assert second.updated == 0
            assert second.deactivated == 0

            worker = RagIndexWorker(
                session_factory,
                DeterministicEmbeddingProvider(dimension=768),
                WorkerOptions(embedding_dimension=768),
            )
            assert await worker.run_once() is True
            assert await worker.run_once() is False

            async with session_factory() as session:
                projection = await session.scalar(
                    select(RagDocument).where(RagDocument.source_id == product_id)
                )
                chunk = await session.scalar(
                    select(RagChunk).join(
                        RagDocument, RagDocument.id == RagChunk.rag_document_id
                    )
                )
                job_count = await session.scalar(
                    select(func.count()).select_from(RagIndexJob)
                )
                dimensions = await session.scalar(
                    text("SELECT vector_dims(embedding) FROM rag_chunks")
                )
                norm = await session.scalar(
                    text("SELECT vector_norm(embedding) FROM rag_chunks")
                )

            assert projection is not None
            assert projection.index_status == "indexed"
            assert projection.content_for_embedding == (
                "Tên sản phẩm: Áo khoác gió nhẹ\n"
                "Danh mục: Áo khoác\n"
                "Mô tả: Chống gió nhẹ cho chuyến đi cuối tuần."
            )
            assert "1290000" not in projection.content_for_embedding
            assert "990000" not in projection.content_for_embedding
            assert chunk is not None
            assert chunk.embedding_model == "stub-deterministic-v1"
            assert job_count == 1
            assert dimensions == 768
            assert norm == pytest.approx(1.0, abs=1e-5)
        finally:
            await engine.dispose()

    asyncio.run(exercise())
