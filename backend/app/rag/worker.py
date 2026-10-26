import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.knowledge import (
    CURRENT_INDEX_EVENT_PAYLOAD_VERSION,
    RagChunk,
    RagDocument,
    RagIndexJob,
)
from app.rag.provider import (
    EmbeddingProvider,
    PermanentIndexingError,
    RetryableIndexingError,
)


@dataclass(frozen=True)
class WorkerOptions:
    embedding_dimension: int = 768
    lock_timeout_seconds: int = 300
    max_attempts: int = 5
    retry_base_seconds: int = 5
    retry_max_seconds: int = 300
    chunk_size: int = 1000


@dataclass(frozen=True)
class ClaimedJob:
    id: UUID
    locked_at: datetime
    source_type: str
    source_id: UUID
    source_version: int
    event_type: str
    payload_version: int
    attempt_count: int


class RagIndexWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        provider: EmbeddingProvider,
        options: WorkerOptions,
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider
        self._options = options

    async def run_once(self) -> bool:
        claim = await self._claim_next_job()
        if claim is None:
            return False
        try:
            await self._process(claim)
        except RetryableIndexingError as error:
            await self._retry_or_fail(claim, error.public_code)
        except PermanentIndexingError as error:
            await self._fail_permanently(claim, error.public_code)
        return True

    async def _claim_next_job(self) -> ClaimedJob | None:
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(seconds=self._options.lock_timeout_seconds)
        async with self._session_factory() as session, session.begin():
            exhausted_jobs = (
                await session.scalars(
                    select(RagIndexJob)
                    .where(
                        or_(
                            RagIndexJob.status == "pending",
                            and_(
                                RagIndexJob.status == "processing",
                                RagIndexJob.locked_at < stale_before,
                            ),
                        ),
                        RagIndexJob.attempt_count >= self._options.max_attempts,
                    )
                    .with_for_update(skip_locked=True)
                    .limit(100)
                )
            ).all()
            for exhausted_job in exhausted_jobs:
                exhausted_job.status = "failed"
                exhausted_job.locked_at = None
                exhausted_job.last_error = "attempts_exhausted"
                await session.execute(
                    update(RagDocument)
                    .where(
                        RagDocument.source_type == exhausted_job.source_type,
                        RagDocument.source_id == exhausted_job.source_id,
                        RagDocument.source_version == exhausted_job.source_version,
                    )
                    .values(index_status="failed")
                )
            await session.execute(
                update(RagIndexJob)
                .where(
                    RagIndexJob.status == "processing",
                    RagIndexJob.locked_at < stale_before,
                    RagIndexJob.attempt_count < self._options.max_attempts,
                )
                .values(status="pending", locked_at=None, available_at=now)
            )
            job = await session.scalar(
                select(RagIndexJob)
                .where(
                    RagIndexJob.status == "pending",
                    RagIndexJob.available_at <= now,
                    RagIndexJob.attempt_count < self._options.max_attempts,
                )
                .order_by(RagIndexJob.created_at, RagIndexJob.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            job.status = "processing"
            job.locked_at = now
            job.attempt_count += 1
            job.last_error = None
            await session.flush()
            return ClaimedJob(
                id=job.id,
                locked_at=now,
                source_type=job.source_type,
                source_id=job.source_id,
                source_version=job.source_version,
                event_type=job.event_type,
                payload_version=job.payload_version,
                attempt_count=job.attempt_count,
            )

    async def _process(self, claim: ClaimedJob) -> None:
        if claim.payload_version != CURRENT_INDEX_EVENT_PAYLOAD_VERSION:
            await self._fail_permanently(claim, "unsupported_payload_version")
            return
        if claim.event_type == "delete":
            await self._complete_delete(claim)
            return

        async with self._session_factory() as session:
            document = await session.scalar(
                select(RagDocument).where(
                    RagDocument.source_type == claim.source_type,
                    RagDocument.source_id == claim.source_id,
                )
            )
            if document is None:
                await self._fail_permanently(claim, "source_projection_missing")
                return
            if document.source_version > claim.source_version:
                await self._complete_superseded(claim)
                return
            if document.source_version < claim.source_version:
                raise RetryableIndexingError("projection_version_behind")
            if not document.is_active:
                raise PermanentIndexingError("inactive_projection_for_upsert")
            chunks = _chunk_text(document.content_for_embedding, self._options.chunk_size)

        vectors = await self._provider.embed(chunks)
        normalized = _validate_and_normalize_vectors(
            vectors,
            expected_count=len(chunks),
            expected_dimension=self._options.embedding_dimension,
        )

        async with self._session_factory() as session, session.begin():
            job = await self._lock_owned_job(session, claim)
            if job is None:
                return
            document = await session.scalar(
                select(RagDocument)
                .where(
                    RagDocument.source_type == claim.source_type,
                    RagDocument.source_id == claim.source_id,
                )
                .with_for_update()
            )
            if document is None:
                raise PermanentIndexingError("source_projection_missing")
            if document.source_version > claim.source_version:
                self._mark_succeeded(job)
                return
            if document.source_version < claim.source_version:
                raise RetryableIndexingError("projection_version_behind")
            if not document.is_active:
                raise PermanentIndexingError("inactive_projection_for_upsert")
            await session.execute(
                delete(RagChunk).where(RagChunk.rag_document_id == document.id)
            )
            session.add_all(
                [
                    RagChunk(
                        rag_document_id=document.id,
                        chunk_index=index,
                        content=content,
                        chunk_metadata={},
                        embedding=embedding,
                        embedding_model=self._provider.model_name,
                        source_version=claim.source_version,
                    )
                    for index, (content, embedding) in enumerate(zip(chunks, normalized))
                ]
            )
            document.index_status = "indexed"
            self._mark_succeeded(job)

    async def _complete_delete(self, claim: ClaimedJob) -> None:
        async with self._session_factory() as session, session.begin():
            job = await self._lock_owned_job(session, claim)
            if job is None:
                return
            document = await session.scalar(
                select(RagDocument)
                .where(
                    RagDocument.source_type == claim.source_type,
                    RagDocument.source_id == claim.source_id,
                )
                .with_for_update()
            )
            if document is None or document.source_version > claim.source_version:
                self._mark_succeeded(job)
                return
            if document.source_version < claim.source_version:
                raise RetryableIndexingError("projection_version_behind")
            if document.source_version == claim.source_version:
                await session.execute(
                    delete(RagChunk).where(RagChunk.rag_document_id == document.id)
                )
                document.is_active = False
                document.index_status = "indexed"
            self._mark_succeeded(job)

    async def _complete_superseded(self, claim: ClaimedJob) -> None:
        async with self._session_factory() as session, session.begin():
            job = await self._lock_owned_job(session, claim)
            if job is not None:
                self._mark_succeeded(job)

    async def _fail_permanently(self, claim: ClaimedJob, code: str) -> None:
        code = _safe_error_code(code, "permanent_indexing_error")
        async with self._session_factory() as session, session.begin():
            job = await self._lock_owned_job(session, claim)
            if job is None:
                return
            job.status = "failed"
            job.locked_at = None
            job.last_error = code
            await session.execute(
                update(RagDocument)
                .where(
                    RagDocument.source_type == claim.source_type,
                    RagDocument.source_id == claim.source_id,
                    RagDocument.source_version == claim.source_version,
                )
                .values(index_status="failed")
            )

    async def _retry_or_fail(self, claim: ClaimedJob, code: str) -> None:
        code = _safe_error_code(code, "retryable_provider_error")
        if claim.attempt_count >= self._options.max_attempts:
            await self._fail_permanently(claim, "attempts_exhausted")
            return
        delay_seconds = min(
            self._options.retry_base_seconds * (2 ** (claim.attempt_count - 1)),
            self._options.retry_max_seconds,
        )
        async with self._session_factory() as session, session.begin():
            job = await self._lock_owned_job(session, claim)
            if job is None:
                return
            job.status = "pending"
            job.available_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
            job.locked_at = None
            job.last_error = code

    async def _lock_owned_job(
        self, session: AsyncSession, claim: ClaimedJob
    ) -> RagIndexJob | None:
        return await session.scalar(
            select(RagIndexJob)
            .where(
                RagIndexJob.id == claim.id,
                RagIndexJob.status == "processing",
                RagIndexJob.locked_at == claim.locked_at,
            )
            .with_for_update()
        )

    @staticmethod
    def _mark_succeeded(job: RagIndexJob) -> None:
        job.status = "succeeded"
        job.locked_at = None
        job.last_error = None


def _chunk_text(content: str, chunk_size: int) -> list[str]:
    chunks: list[str] = []
    for paragraph in content.splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        chunks.extend(
            paragraph[offset : offset + chunk_size]
            for offset in range(0, len(paragraph), chunk_size)
        )
    if not chunks:
        raise PermanentIndexingError("empty_embedding_content")
    return chunks


def _validate_and_normalize_vectors(
    vectors: list[list[float]], expected_count: int, expected_dimension: int
) -> list[list[float]]:
    if len(vectors) != expected_count:
        raise PermanentIndexingError("embedding_count_mismatch")
    normalized: list[list[float]] = []
    for vector in vectors:
        if len(vector) != expected_dimension or not all(math.isfinite(v) for v in vector):
            raise PermanentIndexingError("invalid_embedding_vector")
        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            raise PermanentIndexingError("invalid_embedding_vector")
        normalized.append([value / magnitude for value in vector])
    return normalized


def _safe_error_code(code: str, fallback: str) -> str:
    if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code):
        return code
    return fallback
