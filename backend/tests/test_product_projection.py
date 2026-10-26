import asyncio
from uuid import uuid4

from sqlalchemy import func, select

from app.cli.reindex_products import run_reindex
from app.models.catalog import Category, Product
from app.models.knowledge import RagDocument, RagIndexJob
from app.rag.product_projection import sync_product_projections


def _category() -> Category:
    return Category(
        id=uuid4(),
        name="Áo thun",
        slug="ao-thun",
        description="Danh mục có giá không được đưa vào vector: 199000 VND",
        is_active=True,
    )


def _product(category: Category) -> Product:
    return Product(
        id=uuid4(),
        category_id=category.id,
        sku="AT-DYNAMIC-999000",
        slug="ao-thun-thoang-khi",
        name="Áo thun thoáng khí",
        description="Vải mềm nhẹ phù hợp vận động hằng ngày.",
        price=999_000,
        sale_price=799_000,
        is_active=True,
    )


def test_sync_creates_semantic_only_product_projection_and_is_idempotent(
    auth_session_factory,
) -> None:
    async def exercise() -> None:
        category = _category()
        product = _product(category)
        async with auth_session_factory() as session, session.begin():
            session.add_all([category, product])

        async with auth_session_factory() as session, session.begin():
            first = await sync_product_projections(session)
        async with auth_session_factory() as session, session.begin():
            second = await sync_product_projections(session)

        async with auth_session_factory() as session:
            projection = await session.scalar(
                select(RagDocument).where(RagDocument.source_id == product.id)
            )
            jobs = (
                await session.scalars(
                    select(RagIndexJob).where(RagIndexJob.source_id == product.id)
                )
            ).all()

        assert first.created == 1
        assert first.updated == 0
        assert first.deactivated == 0
        assert second.created == 0
        assert second.updated == 0
        assert second.deactivated == 0
        assert projection is not None
        assert projection.source_type == "product"
        assert projection.title == product.name
        assert projection.content_for_embedding == (
            "Tên sản phẩm: Áo thun thoáng khí\n"
            "Danh mục: Áo thun\n"
            "Mô tả: Vải mềm nhẹ phù hợp vận động hằng ngày."
        )
        assert projection.source_version == 1
        assert projection.index_status == "pending"
        assert projection.is_active is True
        assert "999000" not in projection.content_for_embedding
        assert "799000" not in projection.content_for_embedding
        assert product.sku not in projection.content_for_embedding
        assert len(jobs) == 1
        assert jobs[0].event_type == "upsert"
        assert jobs[0].source_version == 1
        assert jobs[0].payload == {"category_slug": "ao-thun"}

    asyncio.run(exercise())


def test_sync_versions_semantic_changes_and_deactivates_non_public_products(
    auth_session_factory,
) -> None:
    async def exercise() -> None:
        category = _category()
        product = _product(category)
        async with auth_session_factory() as session, session.begin():
            session.add_all([category, product])
        async with auth_session_factory() as session, session.begin():
            await sync_product_projections(session)

        async with auth_session_factory() as session, session.begin():
            stored = await session.get(Product, product.id)
            assert stored is not None
            stored.description = "Chất liệu mới dùng cho thời tiết nóng."
        async with auth_session_factory() as session, session.begin():
            changed = await sync_product_projections(session)

        async with auth_session_factory() as session:
            projection = await session.scalar(
                select(RagDocument).where(RagDocument.source_id == product.id)
            )
            assert projection is not None
            assert projection.source_version == 2
            assert projection.is_active is True
            assert "Chất liệu mới" in projection.content_for_embedding

        async with auth_session_factory() as session, session.begin():
            stored = await session.get(Product, product.id)
            assert stored is not None
            stored.is_active = False
        async with auth_session_factory() as session, session.begin():
            deactivated = await sync_product_projections(session)

        async with auth_session_factory() as session:
            projection = await session.scalar(
                select(RagDocument).where(RagDocument.source_id == product.id)
            )
            jobs = (
                await session.scalars(
                    select(RagIndexJob)
                    .where(RagIndexJob.source_id == product.id)
                    .order_by(RagIndexJob.source_version)
                )
            ).all()

        assert changed.updated == 1
        assert deactivated.deactivated == 1
        assert projection is not None
        assert projection.source_version == 3
        assert projection.is_active is False
        assert projection.index_status == "pending"
        assert [job.event_type for job in jobs] == ["upsert", "upsert", "delete"]
        assert [job.source_version for job in jobs] == [1, 2, 3]

    asyncio.run(exercise())


def test_sync_deactivates_orphaned_product_projection(auth_session_factory) -> None:
    async def exercise() -> None:
        source_id = uuid4()
        async with auth_session_factory() as session, session.begin():
            session.add(
                RagDocument(
                    source_type="product",
                    source_id=source_id,
                    title="Sản phẩm đã xóa",
                    content_for_embedding="Tên sản phẩm: Sản phẩm đã xóa",
                    source_version=4,
                    checksum="a" * 64,
                    index_status="indexed",
                    is_active=True,
                )
            )

        async with auth_session_factory() as session, session.begin():
            result = await sync_product_projections(session)

        async with auth_session_factory() as session:
            projection = await session.scalar(
                select(RagDocument).where(RagDocument.source_id == source_id)
            )
            job_count = await session.scalar(
                select(func.count())
                .select_from(RagIndexJob)
                .where(RagIndexJob.source_id == source_id)
            )

        assert result.deactivated == 1
        assert projection is not None
        assert projection.source_version == 5
        assert projection.is_active is False
        assert projection.index_status == "pending"
        assert job_count == 1

    asyncio.run(exercise())


def test_reindex_command_commits_projection_sync(auth_session_factory) -> None:
    async def exercise() -> None:
        category = _category()
        product = _product(category)
        async with auth_session_factory() as session, session.begin():
            session.add_all([category, product])

        result = await run_reindex(auth_session_factory)

        async with auth_session_factory() as session:
            projection = await session.scalar(
                select(RagDocument).where(RagDocument.source_id == product.id)
            )
        assert result.created == 1
        assert projection is not None

    asyncio.run(exercise())
