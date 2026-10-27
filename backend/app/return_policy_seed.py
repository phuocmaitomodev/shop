from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import (
    CURRENT_INDEX_EVENT_PAYLOAD_VERSION,
    KnowledgeDocument,
    RagDocument,
    RagIndexJob,
)


RETURN_POLICY_NAMESPACE = UUID("e2456944-f064-46aa-a3d4-666a60702f51")
RETURN_POLICY_CONTENT = """Thời hạn
- Đổi hàng trong 07 ngày kể từ khi giao hàng thành công.
- Trả hàng/hoàn tiền trong 03 ngày kể từ khi giao hàng thành công.
- Khách hàng phải liên hệ shop trước khi gửi hàng.

Điều kiện
- Hàng nguyên vẹn, chưa sử dụng, chưa giặt và chưa sửa.
- Còn tem nhãn/tag; không bẩn, rách, hư hoặc có mùi lạ.
- Đầy đủ phụ kiện và quà tặng; có mã đơn hoặc thông tin mua hàng.
- Shop kiểm tra hàng trước khi duyệt đổi hoặc trả.

Trường hợp hỗ trợ
- Đổi size, màu hoặc mẫu tùy tình trạng tồn kho.
- Lỗi nhà sản xuất, hư hỏng trong vận chuyển hoặc giao sai sản phẩm.

Không áp dụng
- Hàng đã sử dụng, giặt hoặc sửa; mất tem; hư hỏng do sử dụng hoặc bảo quản.
- Danh mục đã thông báo không đổi hoặc yêu cầu quá hạn, trừ trường hợp lỗi hoặc pháp luật có quy định khác.
- Hàng sale/thanh lý áp dụng theo thông báo tại thời điểm mua; không mặc định luôn được hoặc không được đổi.

Chi phí
- Đổi theo nhu cầu: khách chịu phí gửi về và phí giao hàng mới.
- Lỗi nhà sản xuất hoặc giao sai: shop chịu chi phí.
- Hư hỏng vận chuyển: shop chịu chi phí sau khi xác nhận.

Liên hệ
Mộc Store, Zalo 0367962529. Zalo chỉ là thông tin liên hệ; shop không tích hợp Zalo hoặc live chat."""


def _checksum(
    document_type: str, title: str, content: str, locale: str, is_active: bool
) -> str:
    canonical = json.dumps(
        [document_type, title, content, locale, is_active],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ReturnPolicySeed:
    title: str = "Chính sách đổi trả"
    document_type: str = "return_policy"
    locale: str = "vi"
    is_active: bool = True
    content: str = RETURN_POLICY_CONTENT

    @property
    def id(self) -> UUID:
        return uuid5(RETURN_POLICY_NAMESPACE, "knowledge:return-policy")

    @property
    def rag_document_id(self) -> UUID:
        return uuid5(RETURN_POLICY_NAMESPACE, "rag-document:return-policy")

    @property
    def checksum(self) -> str:
        return _checksum(
            self.document_type,
            self.title,
            self.content,
            self.locale,
            self.is_active,
        )

    def job_id(self, version: int) -> UUID:
        return uuid5(RETURN_POLICY_NAMESPACE, f"rag-index-job:return-policy:{version}")


RETURN_POLICY = ReturnPolicySeed()


class ReturnPolicySeedConflictError(RuntimeError):
    """Raised when a canonical identity belongs to unrelated persisted data."""


@dataclass(frozen=True)
class VerificationReport:
    ok: bool
    counts: dict[str, int]
    errors: tuple[str, ...]


def _embedding_content(policy: ReturnPolicySeed) -> str:
    return f"{policy.title}\n\n{policy.content}"


def _job_payload(policy: ReturnPolicySeed) -> dict[str, object]:
    return {
        "document_type": policy.document_type,
        "locale": policy.locale,
        "is_active": policy.is_active,
    }


async def seed_return_policy(
    session: AsyncSession, policy: ReturnPolicySeed = RETURN_POLICY
) -> None:
    """Create the canonical return-policy source, projection and outbox event."""
    canonical_changed = False
    document = await session.get(KnowledgeDocument, policy.id)
    document_created = document is None
    natural_match = await session.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.document_type == policy.document_type,
            KnowledgeDocument.title == policy.title,
            KnowledgeDocument.locale == policy.locale,
        )
    )
    if natural_match is not None and natural_match.id != policy.id:
        raise ReturnPolicySeedConflictError(
            f"canonical return policy belongs to non-seed row {natural_match.id}"
        )
    if document is None:
        document = KnowledgeDocument(
            id=policy.id,
            document_type=policy.document_type,
            title=policy.title,
            content=policy.content,
            locale=policy.locale,
            is_active=policy.is_active,
            version=1,
            checksum=policy.checksum,
        )
        session.add(document)
    elif document.document_type != policy.document_type or document.locale != policy.locale:
        raise ReturnPolicySeedConflictError(
            f"canonical return policy id {policy.id} has unexpected data"
        )
    elif (
        document.title != policy.title
        or document.content != policy.content
        or document.is_active != policy.is_active
        or document.checksum != policy.checksum
    ):
        document.title = policy.title
        document.content = policy.content
        document.is_active = policy.is_active
        document.checksum = policy.checksum
        document.version += 1
        canonical_changed = True

    projection = await session.get(RagDocument, policy.rag_document_id)
    source_projection = await session.scalar(
        select(RagDocument).where(
            RagDocument.source_type == "knowledge",
            RagDocument.source_id == policy.id,
        )
    )
    if source_projection is not None and source_projection.id != policy.rag_document_id:
        raise ReturnPolicySeedConflictError(
            f"canonical return policy projection belongs to row {source_projection.id}"
        )
    if projection is None:
        if not document_created:
            raise ReturnPolicySeedConflictError(
                "canonical return policy projection is missing"
            )
        projection = RagDocument(
            id=policy.rag_document_id,
            source_type="knowledge",
            source_id=policy.id,
            title=policy.title,
            content_for_embedding=_embedding_content(policy),
            source_version=document.version,
            checksum=policy.checksum,
            index_status="pending",
            is_active=policy.is_active,
        )
        session.add(projection)
    elif projection.source_type != "knowledge" or projection.source_id != policy.id:
        raise ReturnPolicySeedConflictError(
            f"canonical return policy projection id {policy.rag_document_id} has unexpected data"
        )
    elif canonical_changed:
        projection.title = policy.title
        projection.content_for_embedding = _embedding_content(policy)
        projection.source_version = document.version
        projection.checksum = policy.checksum
        projection.index_status = "pending"
        projection.is_active = policy.is_active
    elif (
        projection.title != policy.title
        or projection.content_for_embedding != _embedding_content(policy)
        or projection.source_version != document.version
        or projection.checksum != policy.checksum
        or projection.is_active != policy.is_active
    ):
        raise ReturnPolicySeedConflictError(
            f"canonical return policy projection id {policy.rag_document_id} has unexpected data"
        )

    job_id = policy.job_id(document.version)
    job = await session.get(RagIndexJob, job_id)
    if job is None:
        if not document_created and not canonical_changed:
            raise ReturnPolicySeedConflictError(
                "canonical return policy current-version job is missing"
            )
        session.add(
            RagIndexJob(
                id=job_id,
                source_type="knowledge",
                source_id=policy.id,
                source_version=document.version,
                event_type="upsert",
                payload=_job_payload(policy),
            )
        )
    elif (
        job.source_type != "knowledge"
        or job.source_id != policy.id
        or job.source_version != document.version
        or job.event_type != "upsert"
        or job.payload != _job_payload(policy)
        or job.payload_version != CURRENT_INDEX_EVENT_PAYLOAD_VERSION
    ):
        raise ReturnPolicySeedConflictError(
            f"canonical return policy job id {job_id} has unexpected data"
        )

    await session.flush()


async def return_policy_snapshot(session: AsyncSession) -> dict[str, object]:
    document = await session.get(KnowledgeDocument, RETURN_POLICY.id)
    projection = await session.get(RagDocument, RETURN_POLICY.rag_document_id)
    jobs = (
        await session.scalars(
            select(RagIndexJob)
            .where(
                RagIndexJob.source_type == "knowledge",
                RagIndexJob.source_id == RETURN_POLICY.id,
            )
            .order_by(RagIndexJob.source_version, RagIndexJob.id)
        )
    ).all()
    return {
        "document": None
        if document is None
        else {
            "id": str(document.id),
            "version": document.version,
            "checksum": document.checksum,
            "title": document.title,
            "content": document.content,
            "locale": document.locale,
            "is_active": document.is_active,
        },
        "rag_document": None
        if projection is None
        else {
            "id": str(projection.id),
            "source_version": projection.source_version,
            "checksum": projection.checksum,
            "title": projection.title,
            "content_for_embedding": projection.content_for_embedding,
            "index_status": projection.index_status,
            "is_active": projection.is_active,
        },
        "jobs": [
            {
                "id": str(job.id),
                "source_version": job.source_version,
                "event_type": job.event_type,
                "payload": job.payload,
                "status": job.status,
            }
            for job in jobs
        ],
    }


async def verify_return_policy(session: AsyncSession) -> VerificationReport:
    """Verify exact canonical source/projection/current-job state without repairing it."""
    errors: list[str] = []
    document = await session.get(KnowledgeDocument, RETURN_POLICY.id)
    projection = await session.get(RagDocument, RETURN_POLICY.rag_document_id)
    jobs = (
        await session.scalars(
            select(RagIndexJob).where(
                RagIndexJob.source_type == "knowledge",
                RagIndexJob.source_id == RETURN_POLICY.id,
            )
        )
    ).all()
    natural_documents = (
        await session.scalars(
            select(KnowledgeDocument).where(
                KnowledgeDocument.document_type == RETURN_POLICY.document_type,
                KnowledgeDocument.title == RETURN_POLICY.title,
                KnowledgeDocument.locale == RETURN_POLICY.locale,
            )
        )
    ).all()
    counts = {
        "knowledge_documents": len(natural_documents),
        "rag_documents": 0 if projection is None else 1,
        "index_jobs": len(jobs),
    }

    if len(natural_documents) != 1 or document is None:
        errors.append("canonical knowledge document is missing or duplicated")
    else:
        expected_document = {
            "document_type": RETURN_POLICY.document_type,
            "title": RETURN_POLICY.title,
            "content": RETURN_POLICY.content,
            "locale": RETURN_POLICY.locale,
            "is_active": RETURN_POLICY.is_active,
            "checksum": RETURN_POLICY.checksum,
        }
        for field, expected in expected_document.items():
            if getattr(document, field) != expected:
                errors.append(f"knowledge document {field} is not canonical")
        if document.version < 1:
            errors.append("knowledge document version is not positive")

    if projection is None:
        errors.append("canonical RAG projection is missing")
    elif document is not None:
        expected_projection = {
            "source_type": "knowledge",
            "source_id": RETURN_POLICY.id,
            "title": RETURN_POLICY.title,
            "content_for_embedding": _embedding_content(RETURN_POLICY),
            "source_version": document.version,
            "checksum": RETURN_POLICY.checksum,
            "is_active": RETURN_POLICY.is_active,
        }
        for field, expected in expected_projection.items():
            if getattr(projection, field) != expected:
                errors.append(f"RAG projection {field} is not canonical")
        if projection.index_status not in {"pending", "indexed"}:
            errors.append("RAG projection is neither pending nor indexed")

    if document is not None:
        job_versions = sorted(job.source_version for job in jobs)
        if job_versions != list(range(1, document.version + 1)):
            errors.append("historical index jobs are not contiguous through current version")
        for job in jobs:
            if job.source_version > document.version:
                errors.append("future-version index job exists")
                continue
            expected_historical_job = {
                "id": RETURN_POLICY.job_id(job.source_version),
                "payload_version": CURRENT_INDEX_EVENT_PAYLOAD_VERSION,
            }
            for field, expected in expected_historical_job.items():
                if getattr(job, field) != expected:
                    errors.append(
                        f"index job version {job.source_version} {field} is not canonical"
                    )
            payload_active = (
                job.payload.get("is_active") if isinstance(job.payload, dict) else None
            )
            if not isinstance(payload_active, bool):
                errors.append(
                    f"index job version {job.source_version} payload is not canonical"
                )
                continue
            expected_payload = {
                "document_type": RETURN_POLICY.document_type,
                "locale": RETURN_POLICY.locale,
                "is_active": payload_active,
            }
            if job.payload != expected_payload:
                errors.append(
                    f"index job version {job.source_version} payload is not canonical"
                )
            expected_event_type = "upsert" if payload_active else "delete"
            if job.event_type != expected_event_type:
                errors.append(
                    f"index job version {job.source_version} event_type is not canonical"
                )

        current_jobs = [job for job in jobs if job.source_version == document.version]
        if len(current_jobs) != 1:
            errors.append("canonical current-version index job is missing or duplicated")
        else:
            current_job = current_jobs[0]
            expected_job = {
                "id": RETURN_POLICY.job_id(document.version),
                "event_type": "upsert",
                "payload": _job_payload(RETURN_POLICY),
                "payload_version": CURRENT_INDEX_EVENT_PAYLOAD_VERSION,
            }
            for field, expected in expected_job.items():
                if getattr(current_job, field) != expected:
                    errors.append(f"current index job {field} is not canonical")
            if current_job.status == "failed":
                errors.append("current index job has failed")

    return VerificationReport(ok=not errors, counts=counts, errors=tuple(errors))
