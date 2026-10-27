import asyncio
import math
import os
from dataclasses import dataclass
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.knowledge import KnowledgeDocument, RagChunk, RagDocument
from app.rag.retrieval import retrieve_knowledge
from tests.integration.database_guard import require_fresh_migrated_database


DATABASE_URL = os.getenv("MIGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="MIGRATION_DATABASE_URL is required for PostgreSQL knowledge retrieval tests",
)
_QUERY_VECTOR = [1.0] + [0.0] * 767
_KEYWORD_VECTOR = [0.0, 1.0] + [0.0] * 766


@dataclass(frozen=True)
class KnowledgeRetrievalFixture:
    session_factory: async_sessionmaker
    source_id: UUID
    document_id: UUID
    chunk_ids: dict[str, UUID]
    eligible_source_ids: set[UUID]


@pytest.fixture(scope="module")
def knowledge_retrieval_fixture():
    assert DATABASE_URL is not None
    require_fresh_migrated_database(DATABASE_URL)
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def seed() -> KnowledgeRetrievalFixture:
        async with session_factory() as session, session.begin():
            await session.execute(
                text(
                    "TRUNCATE rag_chunks, rag_index_jobs, rag_documents, "
                    "knowledge_documents CASCADE"
                )
            )
            chunk_ids: dict[str, UUID] = {}
            next_chunk_id = 1

            async def add_source(
                key: str,
                *,
                document_type: str = "return_policy",
                locale: str = "vi",
                source_active: bool = True,
                projection_active: bool = True,
                index_status: str = "indexed",
                source_version: int = 1,
                projection_version: int | None = None,
                chunk_version: int | None = None,
                chunk_active: bool = True,
                source_type: str = "knowledge",
                chunks: tuple[tuple[str, str, list[float]], ...] | None = None,
            ) -> tuple[KnowledgeDocument, RagDocument]:
                nonlocal next_chunk_id
                source = KnowledgeDocument(
                    document_type=document_type,
                    title=f"Chính sách {key}",
                    content=f"Nội dung {key}",
                    locale=locale,
                    is_active=source_active,
                    version=source_version,
                    checksum=(key + "s").ljust(64, "0")[:64],
                )
                session.add(source)
                await session.flush()
                projection = RagDocument(
                    source_type=source_type,
                    source_id=source.id,
                    title=source.title,
                    content_for_embedding=source.content,
                    source_version=(
                        source_version
                        if projection_version is None
                        else projection_version
                    ),
                    checksum=(key + "d").ljust(64, "0")[:64],
                    index_status=index_status,
                    is_active=projection_active,
                )
                session.add(projection)
                await session.flush()
                chunk_specs = chunks or (
                    ("only", "phí đổi size trong chính sách", _QUERY_VECTOR),
                )
                for index, (chunk_key, content, embedding) in enumerate(chunk_specs):
                    chunk = RagChunk(
                        id=UUID(int=next_chunk_id),
                        rag_document_id=projection.id,
                        chunk_index=index,
                        content=content,
                        chunk_metadata={},
                        embedding=embedding,
                        embedding_model="stub-deterministic-v1",
                        source_version=(
                            projection.source_version
                            if chunk_version is None
                            else chunk_version
                        ),
                        is_active=chunk_active,
                    )
                    session.add(chunk)
                    await session.flush()
                    next_chunk_id += 1
                    chunk_ids[f"{key}:{chunk_key}"] = chunk.id
                return source, projection

            valid_source, valid_projection = await add_source(
                "valid",
                chunks=(
                    (
                        "hybrid",
                        "Phí đổi size",
                        _QUERY_VECTOR,
                    ),
                    (
                        "semantic",
                        "Liên hệ cửa hàng trước khi gửi hàng",
                        _QUERY_VECTOR,
                    ),
                    (
                        "keyword",
                        "Chi tiết phí đổi size theo nhu cầu",
                        _KEYWORD_VECTOR,
                    ),
                    ("crowd-1", "Nội dung semantic một", _QUERY_VECTOR),
                    ("crowd-2", "Nội dung semantic hai", _QUERY_VECTOR),
                    ("crowd-3", "Nội dung semantic ba", _QUERY_VECTOR),
                ),
            )
            eligible_source_ids = {valid_source.id}
            for key, cosine_similarity in (
                ("candidate-a", 0.99),
                ("candidate-b", 0.98),
                ("candidate-c", 0.97),
            ):
                source, _ = await add_source(
                    key,
                    chunks=(
                        (
                            "semantic",
                            f"Nguồn semantic độc lập {key}",
                            [
                                cosine_similarity,
                                math.sqrt(1 - cosine_similarity**2),
                            ]
                            + [0.0] * 766,
                        ),
                    ),
                )
                eligible_source_ids.add(source.id)
            split_source, _ = await add_source(
                "split-winner",
                chunks=(
                    ("vector", "Nội dung thắng semantic", _QUERY_VECTOR),
                    ("keyword", "mauniquekeyword", _KEYWORD_VECTOR),
                ),
            )
            eligible_source_ids.add(split_source.id)
            await add_source("faq", document_type="faq")
            await add_source("inactive-source", source_active=False)
            await add_source("wrong-locale", locale="en")
            await add_source("inactive-projection", projection_active=False)
            await add_source("pending", index_status="pending")
            await add_source("failed", index_status="failed")
            await add_source("stale-source", source_version=2, projection_version=1)
            await add_source("stale-chunk", source_version=2, chunk_version=1)
            await add_source("inactive-chunk", chunk_active=False)
            await add_source("product-projection", source_type="product")

        return KnowledgeRetrievalFixture(
            session_factory=session_factory,
            source_id=valid_source.id,
            document_id=valid_projection.id,
            chunk_ids=chunk_ids,
            eligible_source_ids=eligible_source_ids,
        )

    fixture = asyncio.run(seed())
    try:
        yield fixture
    finally:
        asyncio.run(engine.dispose())


def test_hybrid_retrieval_filters_fuses_deduplicates_and_orders_deterministically(
    knowledge_retrieval_fixture: KnowledgeRetrievalFixture,
) -> None:
    async def retrieve_twice():
        async with knowledge_retrieval_fixture.session_factory() as session:
            first = await retrieve_knowledge(
                session,
                "phí đổi size",
                _QUERY_VECTOR,
                limit=3,
                candidate_limit=20,
                similarity_threshold=0.75,
                rrf_k=60,
            )
            second = await retrieve_knowledge(
                session,
                "phí đổi size",
                _QUERY_VECTOR,
                limit=3,
                candidate_limit=20,
                similarity_threshold=0.75,
                rrf_k=60,
            )
            return first, second

    first, second = asyncio.run(retrieve_twice())

    assert first == second
    assert len(first) == 3
    assert {result.source_id for result in first} <= (
        knowledge_retrieval_fixture.eligible_source_ids
    )
    result = first[0]
    assert result.source_id == knowledge_retrieval_fixture.source_id
    assert result.rag_document_id == knowledge_retrieval_fixture.document_id
    assert result.title == "Chính sách valid"
    assert result.chunk_ids[0] == knowledge_retrieval_fixture.chunk_ids["valid:hybrid"]
    assert len(result.chunk_ids) == len(set(result.chunk_ids))
    assert "phí đổi size" in result.content.lower()
    assert 2 / 65 <= result.score < 2 / 60


def test_top_k_is_applied_to_unique_sources_before_multi_chunk_deduplication(
    knowledge_retrieval_fixture: KnowledgeRetrievalFixture,
) -> None:
    async def retrieve():
        async with knowledge_retrieval_fixture.session_factory() as session:
            return await retrieve_knowledge(
                session,
                "truy vấn không trùng từ khóa corpus",
                _QUERY_VECTOR,
                limit=3,
                candidate_limit=20,
                similarity_threshold=0.75,
                rrf_k=60,
            )

    results = asyncio.run(retrieve())

    assert len(results) == 3
    assert len({result.source_id for result in results}) == 3
    assert {result.source_id for result in results} <= (
        knowledge_retrieval_fixture.eligible_source_ids
    )


def test_rrf_combines_vector_and_keyword_ranks_from_different_source_chunks(
    knowledge_retrieval_fixture: KnowledgeRetrievalFixture,
) -> None:
    async def retrieve():
        async with knowledge_retrieval_fixture.session_factory() as session:
            return await retrieve_knowledge(
                session,
                "mauniquekeyword",
                _QUERY_VECTOR,
                limit=1,
                candidate_limit=20,
                similarity_threshold=0.75,
                rrf_k=60,
            )

    results = asyncio.run(retrieve())

    assert len(results) == 1
    result = results[0]
    assert result.source_id in knowledge_retrieval_fixture.eligible_source_ids
    assert set(result.chunk_ids) == {
        knowledge_retrieval_fixture.chunk_ids["split-winner:vector"],
        knowledge_retrieval_fixture.chunk_ids["split-winner:keyword"],
    }
    assert result.score > 1 / 61
