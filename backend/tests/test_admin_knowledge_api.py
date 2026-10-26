import asyncio
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeDocument, RagDocument, RagIndexJob


def _login_admin(auth_client: TestClient, create_auth_user) -> None:
    create_auth_user("admin-content@example.com", role="admin")
    response = auth_client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin-content@example.com",
            "password": "MatKhau-AnToan-123",
        },
    )
    assert response.status_code == 200


def _create_document(auth_client: TestClient, **overrides) -> dict:
    payload = {
        "document_type": "faq",
        "title": "Phí giao hàng",
        "content": "Phí giao hàng được tính theo cấu hình hiện hành.",
        "locale": "vi",
        "is_active": True,
    }
    payload.update(overrides)
    response = auth_client.post("/api/v1/admin/knowledge-documents", json=payload)
    assert response.status_code == 201
    return response.json()["data"]


def test_admin_creates_knowledge_document_and_outbox_atomically(
    auth_client: TestClient, create_auth_user, auth_session_factory
) -> None:
    _login_admin(auth_client, create_auth_user)

    response = auth_client.post(
        "/api/v1/admin/knowledge-documents",
        json={
            "document_type": "faq",
            "title": "Phí giao hàng",
            "content": "Phí giao hàng được tính theo cấu hình hiện hành.",
            "locale": "vi",
            "is_active": True,
        },
    )

    assert response.status_code == 201
    document = response.json()["data"]
    assert document["document_type"] == "faq"
    assert document["version"] == 1
    assert document["index_status"] == "pending"
    assert document["latest_index_error"] is None

    async def load_rows():
        async with auth_session_factory() as session:
            knowledge = await session.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.id == UUID(document["id"])
                )
            )
            rag_document = await session.scalar(
                select(RagDocument).where(
                    RagDocument.source_type == "knowledge",
                    RagDocument.source_id == knowledge.id,
                )
            )
            jobs = (
                await session.scalars(
                    select(RagIndexJob).where(
                        RagIndexJob.source_type == "knowledge",
                        RagIndexJob.source_id == knowledge.id,
                    )
                )
            ).all()
            return knowledge, rag_document, jobs

    knowledge, rag_document, jobs = asyncio.run(load_rows())
    assert knowledge.checksum == rag_document.checksum
    assert rag_document.source_version == 1
    assert rag_document.content_for_embedding == "Phí giao hàng\n\nPhí giao hàng được tính theo cấu hình hiện hành."
    assert len(jobs) == 1
    assert jobs[0].event_type == "upsert"
    assert jobs[0].status == "pending"
    assert jobs[0].payload == {
        "document_type": "faq",
        "locale": "vi",
        "is_active": True,
    }


def test_knowledge_admin_endpoints_enforce_rbac_and_validation(
    auth_client: TestClient, create_auth_user
) -> None:
    payload = {"document_type": "faq", "title": "FAQ", "content": "Nội dung hợp lệ"}
    unauthenticated = auth_client.post(
        "/api/v1/admin/knowledge-documents", json=payload
    )
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "AUTH_REQUIRED"

    create_auth_user("customer-content@example.com")
    assert auth_client.post(
        "/api/v1/auth/login",
        json={
            "email": "customer-content@example.com",
            "password": "MatKhau-AnToan-123",
        },
    ).status_code == 200
    forbidden = auth_client.get("/api/v1/admin/knowledge-documents")
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "ADMIN_REQUIRED"

    auth_client.cookies.clear()
    _login_admin(auth_client, create_auth_user)
    invalid = auth_client.post(
        "/api/v1/admin/knowledge-documents",
        json={"document_type": "unknown", "title": "  ", "content": "  "},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    document = _create_document(auth_client)
    null_update = auth_client.patch(
        f"/api/v1/admin/knowledge-documents/{document['id']}",
        json={"title": None},
    )
    assert null_update.status_code == 422
    assert null_update.json()["error"]["code"] == "VALIDATION_ERROR"


def test_checksum_is_unambiguous_when_fields_contain_separator(
    auth_client: TestClient, create_auth_user
) -> None:
    _login_admin(auth_client, create_auth_user)
    first = _create_document(
        auth_client,
        title="Bảng size\x1fNam",
        content="Nội dung hướng dẫn",
    )
    second = _create_document(
        auth_client,
        title="Bảng size",
        content="Nam\x1fNội dung hướng dẫn",
    )

    assert first["checksum"] != second["checksum"]


def test_admin_lists_filters_and_reads_knowledge_documents(
    auth_client: TestClient, create_auth_user
) -> None:
    _login_admin(auth_client, create_auth_user)
    first = _create_document(auth_client)
    _create_document(
        auth_client,
        document_type="promotion",
        title="Khuyến mãi",
        content="Ưu đãi theo dữ liệu hiện hành.",
        is_active=False,
    )

    response = auth_client.get(
        "/api/v1/admin/knowledge-documents",
        params={"document_type": "faq", "index_status": "pending", "is_active": True},
    )
    assert response.status_code == 200
    page = response.json()["data"]
    assert page["page"] == 1
    assert page["page_size"] == 20
    assert page["total"] == 1
    assert [item["id"] for item in page["items"]] == [first["id"]]

    detail = auth_client.get(f"/api/v1/admin/knowledge-documents/{first['id']}")
    assert detail.status_code == 200
    assert detail.json()["data"] == first
    missing = auth_client.get(
        "/api/v1/admin/knowledge-documents/00000000-0000-0000-0000-000000000000"
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "KNOWLEDGE_DOCUMENT_NOT_FOUND"


def test_admin_update_enqueues_one_new_version_and_noop_is_idempotent(
    auth_client: TestClient, create_auth_user, auth_session_factory
) -> None:
    _login_admin(auth_client, create_auth_user)
    original = _create_document(auth_client)

    updated = auth_client.patch(
        f"/api/v1/admin/knowledge-documents/{original['id']}",
        json={"content": "Phí giao hàng mới được cập nhật."},
    )
    assert updated.status_code == 200
    updated_data = updated.json()["data"]
    assert updated_data["version"] == 2
    assert updated_data["index_status"] == "pending"
    assert updated_data["checksum"] != original["checksum"]

    noop = auth_client.patch(
        f"/api/v1/admin/knowledge-documents/{original['id']}",
        json={"content": "Phí giao hàng mới được cập nhật."},
    )
    assert noop.status_code == 200
    assert noop.json()["data"]["version"] == 2

    async def load_jobs():
        async with auth_session_factory() as session:
            return (
                await session.scalars(
                    select(RagIndexJob)
                    .where(RagIndexJob.source_id == UUID(original["id"]))
                    .order_by(RagIndexJob.source_version)
                )
            ).all()

    jobs = asyncio.run(load_jobs())
    assert [(job.source_version, job.event_type) for job in jobs] == [
        (1, "upsert"),
        (2, "upsert"),
    ]


def test_admin_archive_and_reindex_create_durable_delete_versions(
    auth_client: TestClient, create_auth_user
) -> None:
    _login_admin(auth_client, create_auth_user)
    original = _create_document(auth_client)

    archived = auth_client.delete(f"/api/v1/admin/knowledge-documents/{original['id']}")
    assert archived.status_code == 200
    assert archived.json()["data"]["is_active"] is False
    assert archived.json()["data"]["version"] == 2

    repeated_archive = auth_client.delete(
        f"/api/v1/admin/knowledge-documents/{original['id']}"
    )
    assert repeated_archive.status_code == 200
    assert repeated_archive.json()["data"]["version"] == 2

    reindexed = auth_client.post(
        f"/api/v1/admin/knowledge-documents/{original['id']}/reindex"
    )
    assert reindexed.status_code == 200
    assert reindexed.json()["data"]["version"] == 3

    jobs_response = auth_client.get(
        "/api/v1/admin/rag-index-jobs",
        params={"source_type": "knowledge", "status": "pending"},
    )
    assert jobs_response.status_code == 200
    jobs = jobs_response.json()["data"]
    assert jobs["total"] == 3
    assert [item["source_version"] for item in jobs["items"]] == [3, 2, 1]
    assert [item["event_type"] for item in jobs["items"]] == [
        "delete",
        "delete",
        "upsert",
    ]
    assert [item["payload_version"] for item in jobs["items"]] == [1, 1, 1]

    job_detail = auth_client.get(
        f"/api/v1/admin/rag-index-jobs/{jobs['items'][0]['id']}"
    )
    assert job_detail.status_code == 200
    assert job_detail.json()["data"] == jobs["items"][0]


def test_document_status_exposes_latest_index_error(
    auth_client: TestClient, create_auth_user, auth_session_factory
) -> None:
    _login_admin(auth_client, create_auth_user)
    document = _create_document(auth_client)

    async def mark_failed():
        async with auth_session_factory() as session:
            rag_document = await session.scalar(
                select(RagDocument).where(RagDocument.source_id == UUID(document["id"]))
            )
            job = await session.scalar(
                select(RagIndexJob).where(RagIndexJob.source_id == UUID(document["id"]))
            )
            rag_document.index_status = "failed"
            job.status = "failed"
            job.attempt_count = 3
            job.last_error = (
                "Embedding provider timeout; token=super-secret-provider-token "
                + "x" * 600
            )
            await session.commit()

    asyncio.run(mark_failed())
    response = auth_client.get(f"/api/v1/admin/knowledge-documents/{document['id']}")
    assert response.status_code == 200
    assert response.json()["data"]["index_status"] == "failed"
    public_error = response.json()["data"]["latest_index_error"]
    assert public_error == "Indexing thất bại. Xem log worker để biết chi tiết."

    jobs = auth_client.get(
        "/api/v1/admin/rag-index-jobs", params={"status": "failed"}
    )
    assert jobs.status_code == 200
    assert "super-secret-provider-token" not in jobs.json()["data"]["items"][0][
        "last_error"
    ]

    reindexed = auth_client.post(
        f"/api/v1/admin/knowledge-documents/{document['id']}/reindex"
    )
    assert reindexed.status_code == 200
    assert reindexed.json()["data"]["latest_index_error"] is None
    current = auth_client.get(
        f"/api/v1/admin/knowledge-documents/{document['id']}"
    )
    assert current.status_code == 200
    assert current.json()["data"]["latest_index_error"] is None
    documents = auth_client.get("/api/v1/admin/knowledge-documents")
    assert documents.status_code == 200
    assert documents.json()["data"]["items"][0]["latest_index_error"] is None


def test_create_rolls_back_all_rows_when_commit_fails(
    auth_client: TestClient,
    create_auth_user,
    auth_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _login_admin(auth_client, create_auth_user)

    async def fail_commit(session):
        await session.flush()
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    response = auth_client.post(
        "/api/v1/admin/knowledge-documents",
        json={
            "document_type": "faq",
            "title": "Không được lưu",
            "content": "Transaction phải rollback.",
        },
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    monkeypatch.undo()

    async def count_rows():
        async with auth_session_factory() as session:
            return (
                await session.scalar(select(func.count()).select_from(KnowledgeDocument)),
                await session.scalar(select(func.count()).select_from(RagDocument)),
                await session.scalar(select(func.count()).select_from(RagIndexJob)),
            )

    assert asyncio.run(count_rows()) == (0, 0, 0)
