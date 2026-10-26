import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from app.models.knowledge import RagChunk, RagDocument, RagIndexJob
from app.rag.provider import DeterministicEmbeddingProvider, RetryableIndexingError
from app.rag.worker import ClaimedJob, RagIndexWorker, WorkerOptions


def test_worker_indexes_pending_job_once(auth_session_factory) -> None:
    source_id = uuid4()

    async def exercise_worker() -> None:
        async with auth_session_factory() as session:
            document = RagDocument(
                source_type="knowledge",
                source_id=source_id,
                title="Chính sách đổi trả",
                content_for_embedding="Đổi trả trong 30 ngày.\nSản phẩm phải còn tem.",
                source_version=1,
                checksum="a" * 64,
            )
            job = RagIndexJob(
                source_type="knowledge",
                source_id=source_id,
                source_version=1,
                event_type="upsert",
                payload={},
            )
            session.add_all([document, job])
            await session.commit()
            job_id = job.id

        worker = RagIndexWorker(
            auth_session_factory,
            DeterministicEmbeddingProvider(dimension=768),
            WorkerOptions(embedding_dimension=768),
        )
        assert await worker.run_once() is True
        assert await worker.run_once() is False

        async with auth_session_factory() as session:
            stored_job = await session.get(RagIndexJob, job_id)
            stored_document = await session.scalar(
                select(RagDocument).where(RagDocument.source_id == source_id)
            )
            chunk_count = await session.scalar(select(func.count()).select_from(RagChunk))

        assert stored_job is not None
        assert stored_job.status == "succeeded"
        assert stored_job.attempt_count == 1
        assert stored_job.locked_at is None
        assert stored_document is not None
        assert stored_document.index_status == "indexed"
        assert chunk_count == 2

    asyncio.run(exercise_worker())


def test_retryable_failure_is_scheduled_then_succeeds(auth_session_factory) -> None:
    class RetryOnceProvider(DeterministicEmbeddingProvider):
        def __init__(self) -> None:
            super().__init__(dimension=768)
            self.calls = 0

        async def embed(self, texts):
            self.calls += 1
            if self.calls == 1:
                raise RetryableIndexingError("provider_temporarily_unavailable")
            return await super().embed(texts)

    async def exercise_worker() -> None:
        source_id = uuid4()
        async with auth_session_factory() as session:
            session.add_all(
                [
                    RagDocument(
                        source_type="knowledge",
                        source_id=source_id,
                        title="FAQ",
                        content_for_embedding="Nội dung FAQ",
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
            await session.commit()

        provider = RetryOnceProvider()
        worker = RagIndexWorker(
            auth_session_factory,
            provider,
            WorkerOptions(
                embedding_dimension=768,
                max_attempts=3,
                retry_base_seconds=7,
            ),
        )
        before = datetime.now(timezone.utc)
        assert await worker.run_once() is True

        async with auth_session_factory() as session:
            job = await session.scalar(select(RagIndexJob))
            assert job is not None
            assert job.status == "pending"
            assert job.locked_at is None
            assert job.last_error == "provider_temporarily_unavailable"
            available_at = job.available_at.replace(tzinfo=timezone.utc)
            # SQLite's database clock is second-precision; PostgreSQL preserves
            # sub-second precision. Both schedule from the database clock.
            assert available_at >= before + timedelta(seconds=6)
            await session.execute(
                update(RagIndexJob).values(
                    available_at=datetime.now(timezone.utc) - timedelta(seconds=1)
                )
            )
            await session.commit()

        assert await worker.run_once() is True
        async with auth_session_factory() as session:
            job = await session.scalar(select(RagIndexJob))
            assert job is not None
            assert job.status == "succeeded"
            assert job.attempt_count == 2

    asyncio.run(exercise_worker())


def test_stale_processing_job_is_reclaimed(auth_session_factory) -> None:
    async def exercise_worker() -> None:
        source_id = uuid4()
        async with auth_session_factory() as session:
            session.add_all(
                [
                    RagDocument(
                        source_type="knowledge",
                        source_id=source_id,
                        title="Hướng dẫn size",
                        content_for_embedding="Chọn size theo số đo.",
                        source_version=1,
                        checksum="c" * 64,
                    ),
                    RagIndexJob(
                        source_type="knowledge",
                        source_id=source_id,
                        source_version=1,
                        event_type="upsert",
                        payload={},
                        status="processing",
                        attempt_count=1,
                        locked_at=datetime.now(timezone.utc) - timedelta(minutes=10),
                    ),
                ]
            )
            await session.commit()

        worker = RagIndexWorker(
            auth_session_factory,
            DeterministicEmbeddingProvider(dimension=768),
            WorkerOptions(embedding_dimension=768, lock_timeout_seconds=60),
        )
        assert await worker.run_once() is True

        async with auth_session_factory() as session:
            job = await session.scalar(select(RagIndexJob))
            assert job is not None
            assert job.status == "succeeded"
            assert job.attempt_count == 2

    asyncio.run(exercise_worker())


def test_unsupported_payload_version_fails_without_provider_call(
    auth_session_factory,
) -> None:
    class ProviderMustNotRun(DeterministicEmbeddingProvider):
        async def embed(self, texts):
            raise AssertionError("provider must not be called")

    async def exercise_worker() -> None:
        source_id = uuid4()
        async with auth_session_factory() as session:
            session.add_all(
                [
                    RagDocument(
                        source_type="knowledge",
                        source_id=source_id,
                        title="FAQ",
                        content_for_embedding="Nội dung",
                        source_version=1,
                        checksum="d" * 64,
                    ),
                    RagIndexJob(
                        source_type="knowledge",
                        source_id=source_id,
                        source_version=1,
                        event_type="upsert",
                        payload={},
                        payload_version=2,
                    ),
                ]
            )
            await session.commit()

        worker = RagIndexWorker(
            auth_session_factory,
            ProviderMustNotRun(dimension=768),
            WorkerOptions(embedding_dimension=768),
        )
        assert await worker.run_once() is True

        async with auth_session_factory() as session:
            job = await session.scalar(select(RagIndexJob))
            document = await session.scalar(select(RagDocument))
            assert job is not None
            assert job.status == "failed"
            assert job.last_error == "unsupported_payload_version"
            assert document is not None
            assert document.index_status == "failed"

    asyncio.run(exercise_worker())


def test_exhausted_retryable_failure_becomes_permanent(auth_session_factory) -> None:
    class AlwaysUnavailable(DeterministicEmbeddingProvider):
        async def embed(self, texts):
            raise RetryableIndexingError("provider_temporarily_unavailable")

    async def exercise_worker() -> None:
        source_id = uuid4()
        async with auth_session_factory() as session:
            session.add_all(
                [
                    RagDocument(
                        source_type="knowledge",
                        source_id=source_id,
                        title="FAQ",
                        content_for_embedding="Nội dung",
                        source_version=1,
                        checksum="e" * 64,
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
            await session.commit()

        worker = RagIndexWorker(
            auth_session_factory,
            AlwaysUnavailable(dimension=768),
            WorkerOptions(embedding_dimension=768, max_attempts=1),
        )
        assert await worker.run_once() is True

        async with auth_session_factory() as session:
            job = await session.scalar(select(RagIndexJob))
            assert job is not None
            assert job.status == "failed"
            assert job.last_error == "attempts_exhausted"

    asyncio.run(exercise_worker())


def test_stale_delete_cannot_remove_newer_chunks(auth_session_factory) -> None:
    async def exercise_worker() -> None:
        source_id = uuid4()
        async with auth_session_factory() as session:
            document = RagDocument(
                source_type="knowledge",
                source_id=source_id,
                title="Chính sách mới",
                content_for_embedding="Phiên bản mới",
                source_version=2,
                checksum="f" * 64,
                index_status="indexed",
            )
            session.add(document)
            await session.flush()
            session.add_all(
                [
                    RagChunk(
                        rag_document_id=document.id,
                        chunk_index=0,
                        content="Phiên bản mới",
                        chunk_metadata={},
                        embedding=[0.0] * 767 + [1.0],
                        embedding_model="stub-deterministic-v1",
                        source_version=2,
                    ),
                    RagIndexJob(
                        source_type="knowledge",
                        source_id=source_id,
                        source_version=1,
                        event_type="delete",
                        payload={},
                    ),
                ]
            )
            await session.commit()

        worker = RagIndexWorker(
            auth_session_factory,
            DeterministicEmbeddingProvider(dimension=768),
            WorkerOptions(embedding_dimension=768),
        )
        assert await worker.run_once() is True

        async with auth_session_factory() as session:
            document = await session.scalar(select(RagDocument))
            chunk_count = await session.scalar(select(func.count()).select_from(RagChunk))
            job = await session.scalar(select(RagIndexJob))
            assert document is not None
            assert document.is_active is True
            assert chunk_count == 1
            assert job is not None
            assert job.status == "succeeded"

    asyncio.run(exercise_worker())


def test_provider_error_text_is_not_persisted(auth_session_factory) -> None:
    class UnsafeProvider(DeterministicEmbeddingProvider):
        async def embed(self, texts):
            raise RetryableIndexingError("token=super-secret-value")

    async def exercise_worker() -> None:
        source_id = uuid4()
        async with auth_session_factory() as session:
            session.add_all(
                [
                    RagDocument(
                        source_type="knowledge",
                        source_id=source_id,
                        title="FAQ",
                        content_for_embedding="Nội dung",
                        source_version=1,
                        checksum="1" * 64,
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
            await session.commit()

        worker = RagIndexWorker(
            auth_session_factory,
            UnsafeProvider(dimension=768),
            WorkerOptions(embedding_dimension=768),
        )
        assert await worker.run_once() is True

        async with auth_session_factory() as session:
            job = await session.scalar(select(RagIndexJob))
            assert job is not None
            assert job.last_error == "retryable_provider_error"
            assert "secret" not in job.last_error

    asyncio.run(exercise_worker())


def test_stale_job_at_attempt_limit_is_failed_not_reclaimed(auth_session_factory) -> None:
    async def exercise_worker() -> None:
        source_id = uuid4()
        async with auth_session_factory() as session:
            session.add_all(
                [
                    RagDocument(
                        source_type="knowledge",
                        source_id=source_id,
                        title="FAQ",
                        content_for_embedding="Nội dung",
                        source_version=1,
                        checksum="2" * 64,
                    ),
                    RagIndexJob(
                        source_type="knowledge",
                        source_id=source_id,
                        source_version=1,
                        event_type="upsert",
                        payload={},
                        status="processing",
                        attempt_count=2,
                        locked_at=datetime.now(timezone.utc) - timedelta(minutes=10),
                    ),
                ]
            )
            await session.commit()

        worker = RagIndexWorker(
            auth_session_factory,
            DeterministicEmbeddingProvider(dimension=768),
            WorkerOptions(
                embedding_dimension=768,
                max_attempts=2,
                lock_timeout_seconds=60,
            ),
        )
        assert await worker.run_once() is False

        async with auth_session_factory() as session:
            job = await session.scalar(select(RagIndexJob))
            document = await session.scalar(select(RagDocument))
            assert job is not None
            assert job.status == "failed"
            assert job.attempt_count == 2
            assert job.last_error == "attempts_exhausted"
            assert document is not None
            assert document.index_status == "failed"

    asyncio.run(exercise_worker())


def test_pending_job_at_attempt_limit_is_failed_not_claimed(auth_session_factory) -> None:
    async def exercise_worker() -> None:
        source_id = uuid4()
        async with auth_session_factory() as session:
            session.add_all(
                [
                    RagDocument(
                        source_type="knowledge",
                        source_id=source_id,
                        title="FAQ",
                        content_for_embedding="Nội dung",
                        source_version=1,
                        checksum="3" * 64,
                    ),
                    RagIndexJob(
                        source_type="knowledge",
                        source_id=source_id,
                        source_version=1,
                        event_type="upsert",
                        payload={},
                        status="pending",
                        attempt_count=2,
                    ),
                ]
            )
            await session.commit()

        worker = RagIndexWorker(
            auth_session_factory,
            DeterministicEmbeddingProvider(dimension=768),
            WorkerOptions(embedding_dimension=768, max_attempts=2),
        )
        assert await worker.run_once() is False

        async with auth_session_factory() as session:
            job = await session.scalar(select(RagIndexJob))
            assert job is not None
            assert job.status == "failed"
            assert job.attempt_count == 2
            assert job.last_error == "attempts_exhausted"

    asyncio.run(exercise_worker())


@pytest.mark.parametrize("event_type", ["upsert", "delete"])
def test_job_newer_than_projection_is_retried(
    auth_session_factory, event_type: str
) -> None:
    async def exercise_worker() -> None:
        source_id = uuid4()
        async with auth_session_factory() as session:
            session.add_all(
                [
                    RagDocument(
                        source_type="knowledge",
                        source_id=source_id,
                        title="FAQ",
                        content_for_embedding="Nội dung",
                        source_version=1,
                        checksum="4" * 64,
                    ),
                    RagIndexJob(
                        source_type="knowledge",
                        source_id=source_id,
                        source_version=2,
                        event_type=event_type,
                        payload={},
                    ),
                ]
            )
            await session.commit()

        worker = RagIndexWorker(
            auth_session_factory,
            DeterministicEmbeddingProvider(dimension=768),
            WorkerOptions(embedding_dimension=768),
        )
        assert await worker.run_once() is True

        async with auth_session_factory() as session:
            job = await session.scalar(select(RagIndexJob))
            document = await session.scalar(select(RagDocument))
            assert job is not None
            assert job.status == "pending"
            assert job.last_error == "projection_version_behind"
            assert document is not None
            assert document.index_status == "pending"

    asyncio.run(exercise_worker())


def test_attempt_count_fences_old_claim_when_lease_timestamp_is_reused(
    auth_session_factory,
) -> None:
    async def exercise_old_claim() -> None:
        source_id = uuid4()
        locked_at = datetime.now(timezone.utc)
        async with auth_session_factory() as session:
            document = RagDocument(
                source_type="knowledge",
                source_id=source_id,
                title="FAQ",
                content_for_embedding="Nội dung",
                source_version=1,
                checksum="5" * 64,
            )
            job = RagIndexJob(
                source_type="knowledge",
                source_id=source_id,
                source_version=1,
                event_type="upsert",
                payload={},
                status="processing",
                attempt_count=2,
                locked_at=locked_at,
            )
            session.add_all([document, job])
            await session.commit()
            job_id = job.id

        old_claim = ClaimedJob(
            id=job_id,
            locked_at=locked_at,
            source_type="knowledge",
            source_id=source_id,
            source_version=1,
            event_type="upsert",
            payload_version=1,
            attempt_count=1,
        )
        worker = RagIndexWorker(
            auth_session_factory,
            DeterministicEmbeddingProvider(dimension=768),
            WorkerOptions(embedding_dimension=768),
        )
        await worker._fail_permanently(old_claim, "obsolete_worker_failure")

        async with auth_session_factory() as session:
            stored_job = await session.get(RagIndexJob, job_id)
            stored_document = await session.scalar(select(RagDocument))
            assert stored_job is not None
            assert stored_job.status == "processing"
            assert stored_job.attempt_count == 2
            assert stored_job.last_error is None
            assert stored_document is not None
            assert stored_document.index_status == "pending"

    asyncio.run(exercise_old_claim())


def test_provider_timeout_is_scheduled_as_retryable(auth_session_factory) -> None:
    class HangingProvider(DeterministicEmbeddingProvider):
        async def embed(self, texts):
            await asyncio.sleep(60)
            return await super().embed(texts)

    async def exercise_timeout() -> None:
        source_id = uuid4()
        async with auth_session_factory() as session:
            session.add_all(
                [
                    RagDocument(
                        source_type="knowledge",
                        source_id=source_id,
                        title="FAQ",
                        content_for_embedding="Nội dung",
                        source_version=1,
                        checksum="6" * 64,
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
            await session.commit()

        worker = RagIndexWorker(
            auth_session_factory,
            HangingProvider(dimension=768),
            WorkerOptions(
                embedding_dimension=768,
                provider_timeout_seconds=0.01,
            ),
        )
        assert await worker.run_once() is True

        async with auth_session_factory() as session:
            job = await session.scalar(select(RagIndexJob))
            assert job is not None
            assert job.status == "pending"
            assert job.last_error == "provider_timeout"

    asyncio.run(exercise_timeout())
