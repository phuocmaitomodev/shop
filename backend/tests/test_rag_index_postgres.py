import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.knowledge import RagDocument, RagIndexJob
from app.rag.provider import DeterministicEmbeddingProvider
from app.rag.worker import RagIndexWorker, WorkerOptions
from tests.integration.database_guard import require_fresh_migrated_database


DATABASE_URL = os.getenv("MIGRATION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="MIGRATION_DATABASE_URL is required for PostgreSQL worker tests",
)


def test_postgres_skip_locked_claims_unlocked_job_without_waiting() -> None:
    assert DATABASE_URL is not None
    require_fresh_migrated_database(DATABASE_URL)

    async def exercise_claims() -> None:
        engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            first_job_id = UUID(int=1)
            second_job_id = UUID(int=2)
            first_source_id = UUID(int=101)
            second_source_id = UUID(int=102)
            async with session_factory() as session, session.begin():
                await session.execute(
                    text("TRUNCATE rag_chunks, rag_index_jobs, rag_documents CASCADE")
                )
                session.add_all(
                    [
                        RagDocument(
                            source_type="knowledge",
                            source_id=first_source_id,
                            title="FAQ bị khóa",
                            content_for_embedding="Nội dung",
                            source_version=1,
                            checksum="a" * 64,
                        ),
                        RagDocument(
                            source_type="knowledge",
                            source_id=second_source_id,
                            title="FAQ không khóa",
                            content_for_embedding="Nội dung",
                            source_version=1,
                            checksum="b" * 64,
                        ),
                        RagIndexJob(
                            id=first_job_id,
                            source_type="knowledge",
                            source_id=first_source_id,
                            source_version=1,
                            event_type="upsert",
                            payload={},
                        ),
                        RagIndexJob(
                            id=second_job_id,
                            source_type="knowledge",
                            source_id=second_source_id,
                            source_version=1,
                            event_type="upsert",
                            payload={},
                        ),
                    ]
                )

            options = WorkerOptions(embedding_dimension=768)
            worker = RagIndexWorker(
                session_factory,
                DeterministicEmbeddingProvider(dimension=768),
                options,
            )
            async with session_factory() as lock_session, lock_session.begin():
                locked_job = await lock_session.scalar(
                    select(RagIndexJob)
                    .where(RagIndexJob.id == first_job_id)
                    .with_for_update()
                )
                assert locked_job is not None
                claim = await asyncio.wait_for(worker._claim_next_job(), timeout=1)
                assert claim is not None
                assert claim.id == second_job_id

            async with session_factory() as session:
                jobs = {
                    job.id: job
                    for job in await session.scalars(
                        select(RagIndexJob).order_by(RagIndexJob.id)
                    )
                }
                assert jobs[first_job_id].status == "pending"
                assert jobs[first_job_id].attempt_count == 0
                assert jobs[second_job_id].status == "processing"
                assert jobs[second_job_id].attempt_count == 1
        finally:
            await engine.dispose()

    asyncio.run(exercise_claims())


def test_postgres_rag_chunk_indexes_match_contract() -> None:
    assert DATABASE_URL is not None

    async def inspect_schema() -> None:
        engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                vector_type = await connection.scalar(
                    text(
                        "SELECT format_type(a.atttypid, a.atttypmod) "
                        "FROM pg_attribute a "
                        "WHERE a.attrelid = 'rag_chunks'::regclass "
                        "AND a.attname = 'embedding'"
                    )
                )
                index_definitions = "\n".join(
                    await connection.scalars(
                        text(
                            "SELECT indexdef FROM pg_indexes "
                            "WHERE schemaname = 'public' AND tablename = 'rag_chunks'"
                        )
                    )
                )
            assert vector_type == "vector(768)"
            assert "USING hnsw" in index_definitions
            assert "vector_cosine_ops" in index_definitions
            assert "USING gin" in index_definitions
            assert "to_tsvector('simple'::regconfig, content)" in index_definitions
        finally:
            await engine.dispose()

    asyncio.run(inspect_schema())


def test_postgres_worker_persists_normalized_vector() -> None:
    assert DATABASE_URL is not None
    require_fresh_migrated_database(DATABASE_URL)

    async def exercise_worker() -> None:
        engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            source_id = uuid4()
            async with session_factory() as session, session.begin():
                await session.execute(
                    text("TRUNCATE rag_chunks, rag_index_jobs, rag_documents CASCADE")
                )
                session.add_all(
                    [
                        RagDocument(
                            source_type="knowledge",
                            source_id=source_id,
                            title="FAQ vector",
                            content_for_embedding="Nội dung vector",
                            source_version=1,
                            checksum="b" * 64,
                        ),
                        RagIndexJob(
                            source_type="knowledge",
                            source_id=source_id,
                            source_version=1,
                            event_type="upsert",
                            payload={},
                        ),
                    ]
                )

            worker = RagIndexWorker(
                session_factory,
                DeterministicEmbeddingProvider(dimension=768),
                WorkerOptions(embedding_dimension=768),
            )
            assert await worker.run_once() is True

            async with session_factory() as session:
                job_status = await session.scalar(select(RagIndexJob.status))
                dimensions = await session.scalar(
                    text("SELECT vector_dims(embedding) FROM rag_chunks")
                )
                norm = await session.scalar(
                    text("SELECT vector_norm(embedding) FROM rag_chunks")
                )
            assert job_status == "succeeded"
            assert dimensions == 768
            assert norm == pytest.approx(1.0, abs=1e-5)
        finally:
            await engine.dispose()

    asyncio.run(exercise_worker())


def test_postgres_expired_lease_fences_old_worker() -> None:
    assert DATABASE_URL is not None
    require_fresh_migrated_database(DATABASE_URL)

    async def exercise_lease_fence() -> None:
        engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            source_id = uuid4()
            async with session_factory() as session, session.begin():
                await session.execute(
                    text("TRUNCATE rag_chunks, rag_index_jobs, rag_documents CASCADE")
                )
                session.add_all(
                    [
                        RagDocument(
                            source_type="knowledge",
                            source_id=source_id,
                            title="FAQ lease",
                            content_for_embedding="Nội dung",
                            source_version=1,
                            checksum="c" * 64,
                        ),
                        RagIndexJob(
                            source_type="knowledge",
                            source_id=source_id,
                            source_version=1,
                            event_type="upsert",
                            payload={},
                        ),
                    ]
                )

            options = WorkerOptions(
                embedding_dimension=768,
                lock_timeout_seconds=1,
            )
            old_worker = RagIndexWorker(
                session_factory,
                DeterministicEmbeddingProvider(dimension=768),
                options,
            )
            new_worker = RagIndexWorker(
                session_factory,
                DeterministicEmbeddingProvider(dimension=768),
                options,
            )
            old_claim = await old_worker._claim_next_job()
            assert old_claim is not None

            async with session_factory() as session, session.begin():
                await session.execute(
                    update(RagIndexJob)
                    .where(RagIndexJob.id == old_claim.id)
                    .values(
                        locked_at=datetime.now(timezone.utc) - timedelta(minutes=1)
                    )
                )

            new_claim = await new_worker._claim_next_job()
            assert new_claim is not None
            assert new_claim.id == old_claim.id
            assert new_claim.locked_at != old_claim.locked_at

            await old_worker._fail_permanently(old_claim, "obsolete_worker_failure")

            async with session_factory() as session:
                job = await session.get(RagIndexJob, old_claim.id)
                document = await session.scalar(select(RagDocument))
                assert job is not None
                assert job.status == "processing"
                assert job.locked_at == new_claim.locked_at
                assert job.last_error is None
                assert document is not None
                assert document.index_status == "pending"
        finally:
            await engine.dispose()

    asyncio.run(exercise_lease_fence())


def test_postgres_recovery_skips_locked_stale_job() -> None:
    assert DATABASE_URL is not None
    require_fresh_migrated_database(DATABASE_URL)

    async def exercise_recovery_contention() -> None:
        engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            stale_job_id = UUID(int=11)
            pending_job_id = UUID(int=12)
            async with session_factory() as session, session.begin():
                await session.execute(
                    text("TRUNCATE rag_chunks, rag_index_jobs, rag_documents CASCADE")
                )
                session.add_all(
                    [
                        RagIndexJob(
                            id=stale_job_id,
                            source_type="knowledge",
                            source_id=UUID(int=111),
                            source_version=1,
                            event_type="upsert",
                            payload={},
                            status="processing",
                            attempt_count=1,
                            locked_at=datetime.now(timezone.utc)
                            - timedelta(minutes=10),
                        ),
                        RagIndexJob(
                            id=pending_job_id,
                            source_type="knowledge",
                            source_id=UUID(int=112),
                            source_version=1,
                            event_type="upsert",
                            payload={},
                        ),
                    ]
                )

            worker = RagIndexWorker(
                session_factory,
                DeterministicEmbeddingProvider(dimension=768),
                WorkerOptions(embedding_dimension=768, lock_timeout_seconds=60),
            )
            async with session_factory() as lock_session, lock_session.begin():
                locked_job = await lock_session.scalar(
                    select(RagIndexJob)
                    .where(RagIndexJob.id == stale_job_id)
                    .with_for_update()
                )
                assert locked_job is not None
                claim = await asyncio.wait_for(worker._claim_next_job(), timeout=1)
                assert claim is not None
                assert claim.id == pending_job_id

            async with session_factory() as session:
                stale_job = await session.get(RagIndexJob, stale_job_id)
                assert stale_job is not None
                assert stale_job.status == "processing"
                assert stale_job.attempt_count == 1
        finally:
            await engine.dispose()

    asyncio.run(exercise_recovery_contention())
