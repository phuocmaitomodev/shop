import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.exc import IntegrityError

from app.models.knowledge import KnowledgeDocument, RagChunk, RagDocument, RagIndexJob


def _constraint_names(model, constraint_type):
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if isinstance(constraint, constraint_type)
    }


def test_rag_chunk_metadata_declares_postgres_retrieval_indexes() -> None:
    indexes = {index.name: index for index in RagChunk.__table__.indexes}

    assert indexes["ix_rag_chunks_embedding_hnsw"].dialect_options["postgresql"][
        "using"
    ] == "hnsw"
    assert indexes["ix_rag_chunks_embedding_hnsw"].dialect_options["postgresql"][
        "ops"
    ] == {"embedding": "vector_cosine_ops"}
    assert indexes["ix_rag_chunks_content_fts"].dialect_options["postgresql"][
        "using"
    ] == "gin"


def test_knowledge_and_index_models_publish_stable_contract() -> None:
    assert {
        "ck_knowledge_documents_document_type_valid",
        "ck_knowledge_documents_version_positive",
    } <= _constraint_names(KnowledgeDocument, CheckConstraint)
    assert "uq_rag_document_source" in _constraint_names(
        RagDocument, UniqueConstraint
    )
    assert "uq_rag_index_job_source_version" in _constraint_names(
        RagIndexJob, UniqueConstraint
    )

    jobs = RagIndexJob.__table__
    assert {
        "event_type",
        "payload",
        "payload_version",
        "attempt_count",
        "available_at",
        "locked_at",
        "last_error",
    } <= set(jobs.columns.keys())
    assert {
        "ck_rag_index_jobs_event_type_valid",
        "ck_rag_index_jobs_payload_version_positive",
        "ck_rag_index_jobs_attempt_count_non_negative",
    } <= _constraint_names(RagIndexJob, CheckConstraint)


def test_knowledge_document_type_and_versions_are_constrained(
    auth_session_factory,
) -> None:
    async def persist_invalid_documents() -> None:
        for document in (
            KnowledgeDocument(
                document_type="unknown",
                title="Nội dung không hợp lệ",
                content="Không được lưu.",
                checksum="a" * 64,
            ),
            KnowledgeDocument(
                document_type="faq",
                title="Phiên bản không hợp lệ",
                content="Không được lưu.",
                version=0,
                checksum="b" * 64,
            ),
        ):
            async with auth_session_factory() as session:
                session.add(document)
                with pytest.raises(IntegrityError):
                    await session.commit()

    asyncio.run(persist_invalid_documents())


def test_rag_document_and_job_idempotency_are_constrained(
    auth_session_factory,
) -> None:
    source_id = uuid4()

    async def persist_duplicates() -> None:
        async with auth_session_factory() as session:
            session.add_all(
                [
                    RagDocument(
                        source_type="knowledge",
                        source_id=source_id,
                        title="FAQ",
                        content_for_embedding="Nội dung",
                        source_version=1,
                        checksum="a" * 64,
                    ),
                    RagDocument(
                        source_type="knowledge",
                        source_id=source_id,
                        title="FAQ khác",
                        content_for_embedding="Nội dung khác",
                        source_version=2,
                        checksum="b" * 64,
                    ),
                ]
            )
            with pytest.raises(IntegrityError):
                await session.commit()

        async with auth_session_factory() as session:
            session.add_all(
                [
                    RagIndexJob(
                        source_type="knowledge",
                        source_id=source_id,
                        source_version=1,
                        event_type="upsert",
                        payload={"document_type": "faq"},
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
            with pytest.raises(IntegrityError):
                await session.commit()

    asyncio.run(persist_duplicates())


def test_outbox_rejects_invalid_state_and_retry_metadata(auth_session_factory) -> None:
    async def persist_invalid_jobs() -> None:
        invalid_jobs = (
            RagIndexJob(
                source_type="knowledge",
                source_id=uuid4(),
                source_version=1,
                event_type="replace_everything",
                payload={},
            ),
            RagIndexJob(
                source_type="knowledge",
                source_id=uuid4(),
                source_version=1,
                event_type="upsert",
                payload={},
                payload_version=0,
            ),
            RagIndexJob(
                source_type="knowledge",
                source_id=uuid4(),
                source_version=1,
                event_type="upsert",
                payload={},
                attempt_count=-1,
            ),
        )
        for job in invalid_jobs:
            async with auth_session_factory() as session:
                session.add(job)
                with pytest.raises(IntegrityError):
                    await session.commit()

    asyncio.run(persist_invalid_jobs())
