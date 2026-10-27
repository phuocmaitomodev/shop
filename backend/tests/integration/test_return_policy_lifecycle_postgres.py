import asyncio
import hashlib
import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.knowledge import KnowledgeDocument, RagDocument, RagIndexJob
from app.rag.chat import DeterministicChatProvider, orchestrate_chat
from app.rag.provider import DeterministicEmbeddingProvider
from app.rag.worker import RagIndexWorker, WorkerOptions
from app.return_policy_seed import RETURN_POLICY, seed_return_policy
from tests.integration.database_guard import require_fresh_migrated_database


DATABASE_URL = os.getenv("MIGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="MIGRATION_DATABASE_URL is required for the return-policy lifecycle test",
)


def test_return_policy_seed_update_reindex_and_archive_lifecycle() -> None:
    assert DATABASE_URL is not None
    require_fresh_migrated_database(DATABASE_URL)

    async def exercise() -> None:
        engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        worker = RagIndexWorker(
            session_factory,
            DeterministicEmbeddingProvider(dimension=768),
            WorkerOptions(embedding_dimension=768),
        )
        embedding_provider = DeterministicEmbeddingProvider(dimension=768)

        async def ask(message: str):
            async with session_factory() as session:
                return await orchestrate_chat(
                    session=session,
                    message=message,
                    history=(),
                    chat_provider=DeterministicChatProvider(),
                    embedding_provider=embedding_provider,
                )

        try:
            async with session_factory() as session:
                await seed_return_policy(session)
                await session.commit()

            assert await worker.run_once() is True
            initial = await ask("Đổi hàng trong bao nhiêu ngày?")
            assert initial.status == "ok"
            assert initial.products == []
            assert "07 ngày" in initial.answer
            assert initial.sources[0].knowledge_type == "return_policy"

            async with session_factory() as session:
                document = await session.get(KnowledgeDocument, RETURN_POLICY.id)
                projection = await session.get(RagDocument, RETURN_POLICY.rag_document_id)
                assert document is not None
                assert projection is not None
                stale_content = "Phiên bản policy trước khi cập nhật."
                stale_checksum = hashlib.sha256(stale_content.encode()).hexdigest()
                document.content = stale_content
                document.checksum = stale_checksum
                projection.content_for_embedding = stale_content
                projection.checksum = stale_checksum
                projection.index_status = "indexed"
                await session.flush()
                await seed_return_policy(session)
                await session.commit()

            assert await worker.run_once() is True
            updated = await ask("Tôi có thể trả hàng và hoàn tiền trong mấy ngày?")
            assert updated.status == "ok"
            assert "03 ngày" in updated.answer
            assert updated.products == []

            async with session_factory() as session:
                document = await session.get(KnowledgeDocument, RETURN_POLICY.id)
                projection = await session.get(RagDocument, RETURN_POLICY.rag_document_id)
                assert document is not None
                assert projection is not None
                assert document.version == 2
                assert projection.source_version == 2
                assert projection.index_status == "indexed"
                assert updated.sources[0].chunk_ids

                document.version += 1
                document.is_active = False
                projection.source_version = document.version
                projection.is_active = False
                projection.index_status = "pending"
                session.add(
                    RagIndexJob(
                        source_type="knowledge",
                        source_id=RETURN_POLICY.id,
                        source_version=document.version,
                        event_type="delete",
                        payload={
                            "document_type": RETURN_POLICY.document_type,
                            "locale": RETURN_POLICY.locale,
                            "is_active": False,
                        },
                    )
                )
                await session.commit()

            assert await worker.run_once() is True
            archived = await ask("Đổi hàng trong bao nhiêu ngày?")
            assert archived.status == "insufficient_data"
            assert archived.products == []
            assert archived.sources == []
        finally:
            await engine.dispose()

    asyncio.run(exercise())