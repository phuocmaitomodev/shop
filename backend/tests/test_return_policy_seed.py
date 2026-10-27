import asyncio
import hashlib
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.cli import seed_return_policy as seed_cli
from app.cli import verify_return_policy as verify_cli
from app.models.knowledge import (
    CURRENT_INDEX_EVENT_PAYLOAD_VERSION,
    KnowledgeDocument,
    RagDocument,
    RagIndexJob,
)
from app.return_policy_seed import (
    RETURN_POLICY,
    ReturnPolicySeedConflictError,
    return_policy_snapshot,
    seed_return_policy,
    verify_return_policy,
)


def test_return_policy_seed_is_deterministic_and_idempotent(auth_session_factory) -> None:
    async def seed_twice():
        async with auth_session_factory() as session:
            await seed_return_policy(session)
            first = await return_policy_snapshot(session)
            await session.commit()

        async with auth_session_factory() as session:
            await seed_return_policy(session)
            second = await return_policy_snapshot(session)
            counts = {
                "knowledge_documents": await session.scalar(
                    select(func.count()).select_from(KnowledgeDocument)
                ),
                "rag_documents": await session.scalar(
                    select(func.count()).select_from(RagDocument)
                ),
                "index_jobs": await session.scalar(
                    select(func.count()).select_from(RagIndexJob)
                ),
            }
            return first, second, counts

    first, second, counts = asyncio.run(seed_twice())

    assert first == second
    assert first["document"]["id"] == str(RETURN_POLICY.id)
    assert first["document"]["checksum"] == RETURN_POLICY.checksum
    assert first["rag_document"]["id"] == str(RETURN_POLICY.rag_document_id)
    assert first["jobs"][0]["id"] == str(RETURN_POLICY.job_id(1))
    assert counts == {
        "knowledge_documents": 1,
        "rag_documents": 1,
        "index_jobs": 1,
    }


def test_return_policy_seed_advances_changed_canonical_content_once(
    auth_session_factory,
) -> None:
    async def change_and_reseed():
        async with auth_session_factory() as session:
            await seed_return_policy(session)
            document = await session.get(KnowledgeDocument, RETURN_POLICY.id)
            projection = await session.get(RagDocument, RETURN_POLICY.rag_document_id)
            assert document is not None
            assert projection is not None
            old_content = "Phiên bản policy canonical trước."
            old_checksum = hashlib.sha256(old_content.encode("utf-8")).hexdigest()
            document.content = old_content
            document.checksum = old_checksum
            projection.content_for_embedding = f"{RETURN_POLICY.title}\n\n{old_content}"
            projection.checksum = old_checksum
            projection.index_status = "indexed"
            await session.flush()

            await seed_return_policy(session)
            after_change = await return_policy_snapshot(session)
            await seed_return_policy(session)
            after_rerun = await return_policy_snapshot(session)
            return after_change, after_rerun

    after_change, after_rerun = asyncio.run(change_and_reseed())

    assert after_change == after_rerun
    assert after_change["document"]["version"] == 2
    assert after_change["document"]["content"] == RETURN_POLICY.content
    assert after_change["rag_document"]["source_version"] == 2
    assert after_change["rag_document"]["index_status"] == "pending"
    assert [job["source_version"] for job in after_change["jobs"]] == [1, 2]
    assert after_change["jobs"][1]["id"] == str(RETURN_POLICY.job_id(2))


def test_return_policy_verifier_fails_closed_on_canonical_drift(
    auth_session_factory,
) -> None:
    async def verify_valid_then_corrupt():
        async with auth_session_factory() as session:
            await seed_return_policy(session)
            valid = await verify_return_policy(session)
            document = await session.get(KnowledgeDocument, RETURN_POLICY.id)
            assert document is not None
            document.content = "Nội dung khác nhưng vẫn không rỗng."
            await session.flush()
            invalid = await verify_return_policy(session)
            return valid, invalid

    valid, invalid = asyncio.run(verify_valid_then_corrupt())

    assert valid.ok is True
    assert valid.errors == ()
    assert invalid.ok is False
    assert any("content" in error for error in invalid.errors)


def test_return_policy_verifier_rejects_unsupported_job_payload_version(
    auth_session_factory,
) -> None:
    async def corrupt_and_verify():
        async with auth_session_factory() as session:
            await seed_return_policy(session)
            job = await session.get(RagIndexJob, RETURN_POLICY.job_id(1))
            assert job is not None
            job.payload_version = CURRENT_INDEX_EVENT_PAYLOAD_VERSION + 1
            await session.flush()
            return await verify_return_policy(session)

    report = asyncio.run(corrupt_and_verify())

    assert report.ok is False
    assert any("payload_version" in error for error in report.errors)


def test_return_policy_verifier_rejects_future_version_jobs(
    auth_session_factory,
) -> None:
    async def add_future_job_and_verify():
        async with auth_session_factory() as session:
            await seed_return_policy(session)
            session.add(
                RagIndexJob(
                    source_type="knowledge",
                    source_id=RETURN_POLICY.id,
                    source_version=2,
                    event_type="upsert",
                    payload={
                        "document_type": RETURN_POLICY.document_type,
                        "locale": RETURN_POLICY.locale,
                        "is_active": RETURN_POLICY.is_active,
                    },
                )
            )
            await session.flush()
            return await verify_return_policy(session)

    report = asyncio.run(add_future_job_and_verify())

    assert report.ok is False
    assert any("future" in error for error in report.errors)


def test_return_policy_seed_and_verifier_cli_exit_fail_closed(
    auth_session_factory, monkeypatch
) -> None:
    monkeypatch.setattr(seed_cli, "SessionLocal", auth_session_factory)
    monkeypatch.setattr(verify_cli, "SessionLocal", auth_session_factory)

    assert asyncio.run(seed_cli.run()) == 0
    assert asyncio.run(verify_cli.run()) == 0

    async def corrupt() -> None:
        async with auth_session_factory() as session:
            projection = await session.get(RagDocument, RETURN_POLICY.rag_document_id)
            assert projection is not None
            projection.index_status = "failed"
            await session.commit()

    asyncio.run(corrupt())

    assert asyncio.run(verify_cli.run()) == 1


def test_first_return_policy_seed_rolls_back_atomically_on_projection_collision(
    auth_session_factory, monkeypatch
) -> None:
    async def create_collision() -> None:
        async with auth_session_factory() as session:
            session.add(
                RagDocument(
                    id=RETURN_POLICY.rag_document_id,
                    source_type="product",
                    source_id=uuid4(),
                    title="Dữ liệu không thuộc seed",
                    content_for_embedding="Không được thay thế.",
                    source_version=1,
                    checksum="0" * 64,
                    index_status="pending",
                    is_active=True,
                )
            )
            await session.commit()

    asyncio.run(create_collision())
    monkeypatch.setattr(seed_cli, "SessionLocal", auth_session_factory)

    assert asyncio.run(seed_cli.run()) == 1

    async def load_state():
        async with auth_session_factory() as session:
            document = await session.get(KnowledgeDocument, RETURN_POLICY.id)
            projection = await session.get(RagDocument, RETURN_POLICY.rag_document_id)
            jobs = (
                await session.scalars(
                    select(RagIndexJob).where(
                        RagIndexJob.source_id == RETURN_POLICY.id
                    )
                )
            ).all()
            return document, projection, jobs

    document, projection, jobs = asyncio.run(load_state())
    assert document is None
    assert projection is not None
    assert projection.title == "Dữ liệu không thuộc seed"
    assert jobs == []


def test_return_policy_seed_rejects_partial_persisted_source_state(
    auth_session_factory,
) -> None:
    async def persist_partial_then_seed() -> None:
        async with auth_session_factory() as session:
            session.add(
                KnowledgeDocument(
                    id=RETURN_POLICY.id,
                    document_type=RETURN_POLICY.document_type,
                    title=RETURN_POLICY.title,
                    content=RETURN_POLICY.content,
                    locale=RETURN_POLICY.locale,
                    is_active=RETURN_POLICY.is_active,
                    version=1,
                    checksum=RETURN_POLICY.checksum,
                )
            )
            await session.commit()

        async with auth_session_factory() as session:
            with pytest.raises(ReturnPolicySeedConflictError, match="projection"):
                await seed_return_policy(session)

    asyncio.run(persist_partial_then_seed())


def test_return_policy_verifier_requires_contiguous_historical_jobs(
    auth_session_factory,
) -> None:
    async def remove_historical_job_and_verify():
        async with auth_session_factory() as session:
            await seed_return_policy(session)
            document = await session.get(KnowledgeDocument, RETURN_POLICY.id)
            projection = await session.get(RagDocument, RETURN_POLICY.rag_document_id)
            assert document is not None
            assert projection is not None
            document.content = "Phiên bản canonical cũ."
            document.checksum = "0" * 64
            projection.content_for_embedding = "Phiên bản canonical cũ."
            projection.checksum = "0" * 64
            await session.flush()
            await seed_return_policy(session)

            historical_job = await session.get(RagIndexJob, RETURN_POLICY.job_id(1))
            assert historical_job is not None
            await session.delete(historical_job)
            await session.flush()
            return await verify_return_policy(session)

    report = asyncio.run(remove_historical_job_and_verify())

    assert report.ok is False
    assert any("historical" in error for error in report.errors)


def test_return_policy_verifier_rejects_corrupted_historical_job_payload(
    auth_session_factory,
) -> None:
    async def corrupt_historical_job_and_verify():
        async with auth_session_factory() as session:
            await seed_return_policy(session)
            document = await session.get(KnowledgeDocument, RETURN_POLICY.id)
            projection = await session.get(RagDocument, RETURN_POLICY.rag_document_id)
            assert document is not None
            assert projection is not None
            document.content = "Phiên bản canonical cũ."
            document.checksum = "0" * 64
            projection.content_for_embedding = "Phiên bản canonical cũ."
            projection.checksum = "0" * 64
            await session.flush()
            await seed_return_policy(session)

            historical_job = await session.get(RagIndexJob, RETURN_POLICY.job_id(1))
            assert historical_job is not None
            historical_job.event_type = "delete"
            historical_job.payload = {
                "document_type": "shipping_policy",
                "locale": "en",
                "is_active": True,
            }
            await session.flush()
            return await verify_return_policy(session)

    report = asyncio.run(corrupt_historical_job_and_verify())

    assert report.ok is False
    assert any("payload" in error for error in report.errors)
    assert any("event_type" in error for error in report.errors)
