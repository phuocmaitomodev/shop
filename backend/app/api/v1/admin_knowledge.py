import hashlib
import json
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_admin
from app.core.errors import AppError
from app.db.session import get_db_session
from app.models.auth import User
from app.models.knowledge import KnowledgeDocument, RagDocument, RagIndexJob
from app.schemas.common import ErrorEnvelope
from app.schemas.knowledge import (
    DocumentType,
    IndexStatus,
    JobStatus,
    KnowledgeDocumentCreate,
    KnowledgeDocumentEnvelope,
    KnowledgeDocumentListEnvelope,
    KnowledgeDocumentPage,
    KnowledgeDocumentResponse,
    KnowledgeDocumentUpdate,
    RagIndexJobEnvelope,
    RagIndexJobListEnvelope,
    RagIndexJobPage,
    RagIndexJobResponse,
)

router = APIRouter(prefix="/admin", tags=["admin-knowledge"])

AUTH_VALIDATION_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorEnvelope}
}
RESOURCE_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
    status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
    **AUTH_VALIDATION_RESPONSES,
}
JOB_RESOURCE_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
    **AUTH_VALIDATION_RESPONSES,
}


def _checksum(document_type: str, title: str, content: str, locale: str, is_active: bool) -> str:
    canonical = json.dumps(
        [document_type, title, content, locale, is_active],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _embedding_content(title: str, content: str) -> str:
    return f"{title}\n\n{content}"


def _public_index_error(error: str | None) -> str | None:
    if error is None:
        return None
    return "Indexing thất bại. Xem log worker để biết chi tiết."


def _document_response(
    document: KnowledgeDocument,
    rag_document: RagDocument,
    latest_error: str | None = None,
) -> KnowledgeDocumentResponse:
    return KnowledgeDocumentResponse(
        id=document.id,
        document_type=document.document_type,
        title=document.title,
        content=document.content,
        locale=document.locale,
        is_active=document.is_active,
        version=document.version,
        checksum=document.checksum,
        index_status=rag_document.index_status,
        latest_index_error=_public_index_error(latest_error),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _job_response(job: RagIndexJob) -> RagIndexJobResponse:
    return RagIndexJobResponse(
        id=job.id,
        source_type=job.source_type,
        source_id=job.source_id,
        source_version=job.source_version,
        event_type=job.event_type,
        payload_version=job.payload_version,
        status=job.status,
        attempt_count=job.attempt_count,
        available_at=job.available_at,
        locked_at=job.locked_at,
        last_error=_public_index_error(job.last_error),
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _not_found() -> AppError:
    return AppError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="KNOWLEDGE_DOCUMENT_NOT_FOUND",
        message="Không tìm thấy tài liệu kiến thức.",
    )


async def _load_document_bundle(
    session: AsyncSession,
    document_id: UUID,
    *,
    lock: bool = False,
) -> tuple[KnowledgeDocument, RagDocument, str | None]:
    statement = select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
    if lock:
        statement = statement.with_for_update()
    document = await session.scalar(statement)
    if document is None:
        raise _not_found()

    rag_statement = select(RagDocument).where(
        RagDocument.source_type == "knowledge",
        RagDocument.source_id == document.id,
    )
    if lock:
        rag_statement = rag_statement.with_for_update()
    rag_document = await session.scalar(rag_statement)
    if rag_document is None:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="INDEX_STATE_MISSING",
            message="Tài liệu chưa có trạng thái indexing tương ứng.",
        )

    latest_error = await session.scalar(
        select(RagIndexJob.last_error)
        .where(
            RagIndexJob.source_type == "knowledge",
            RagIndexJob.source_id == document.id,
            RagIndexJob.source_version == rag_document.source_version,
        )
        .order_by(RagIndexJob.created_at.desc())
        .limit(1)
    )
    return document, rag_document, latest_error


def _enqueue_version(
    session: AsyncSession,
    document: KnowledgeDocument,
    rag_document: RagDocument,
) -> None:
    rag_document.title = document.title
    rag_document.content_for_embedding = _embedding_content(
        document.title, document.content
    )
    rag_document.source_version = document.version
    rag_document.checksum = document.checksum
    rag_document.index_status = "pending"
    rag_document.is_active = document.is_active
    session.add(
        RagIndexJob(
            source_type="knowledge",
            source_id=document.id,
            source_version=document.version,
            event_type="upsert" if document.is_active else "delete",
            payload={
                "document_type": document.document_type,
                "locale": document.locale,
                "is_active": document.is_active,
            },
        )
    )


@router.post(
    "/knowledge-documents",
    response_model=KnowledgeDocumentEnvelope,
    status_code=status.HTTP_201_CREATED,
    responses=AUTH_VALIDATION_RESPONSES,
)
async def create_knowledge_document(
    payload: KnowledgeDocumentCreate,
    request: Request,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    source_id = uuid4()
    checksum = _checksum(
        payload.document_type,
        payload.title,
        payload.content,
        payload.locale,
        payload.is_active,
    )
    document = KnowledgeDocument(
        id=source_id,
        document_type=payload.document_type,
        title=payload.title,
        content=payload.content,
        locale=payload.locale,
        is_active=payload.is_active,
        version=1,
        checksum=checksum,
    )
    rag_document = RagDocument(
        source_type="knowledge",
        source_id=source_id,
        title=payload.title,
        content_for_embedding=_embedding_content(payload.title, payload.content),
        source_version=1,
        checksum=checksum,
        index_status="pending",
        is_active=payload.is_active,
    )
    job = RagIndexJob(
        source_type="knowledge",
        source_id=source_id,
        source_version=1,
        event_type="upsert" if payload.is_active else "delete",
        payload={
            "document_type": payload.document_type,
            "locale": payload.locale,
            "is_active": payload.is_active,
        },
    )
    session.add_all((document, rag_document, job))
    await session.commit()
    await session.refresh(document)
    await session.refresh(rag_document)
    return {
        "data": _document_response(document, rag_document),
        "meta": {"request_id": request.state.request_id},
    }


@router.get(
    "/knowledge-documents",
    response_model=KnowledgeDocumentListEnvelope,
    responses=AUTH_VALIDATION_RESPONSES,
)
async def list_knowledge_documents(
    request: Request,
    document_type: DocumentType | None = Query(default=None),
    index_status: IndexStatus | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=1_000_000),
    page_size: int = Query(default=20, ge=1, le=100),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    filters = []
    if document_type is not None:
        filters.append(KnowledgeDocument.document_type == document_type)
    if index_status is not None:
        filters.append(RagDocument.index_status == index_status)
    if is_active is not None:
        filters.append(KnowledgeDocument.is_active.is_(is_active))

    base = (
        select(KnowledgeDocument, RagDocument)
        .join(
            RagDocument,
            (RagDocument.source_type == "knowledge")
            & (RagDocument.source_id == KnowledgeDocument.id),
        )
        .where(*filters)
    )
    total = await session.scalar(
        select(func.count()).select_from(base.order_by(None).subquery())
    )
    rows = (
        await session.execute(
            base.order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    source_ids = [document.id for document, _rag in rows]
    latest_errors: dict[UUID, str | None] = {}
    if source_ids:
        current_versions = {
            document.id: rag.source_version for document, rag in rows
        }
        error_rows = (
            await session.execute(
                select(
                    RagIndexJob.source_id,
                    RagIndexJob.source_version,
                    RagIndexJob.last_error,
                )
                .where(
                    RagIndexJob.source_type == "knowledge",
                    RagIndexJob.source_id.in_(source_ids),
                )
                .order_by(
                    RagIndexJob.source_id,
                    RagIndexJob.source_version.desc(),
                    RagIndexJob.created_at.desc(),
                )
            )
        ).all()
        for source_id, source_version, error in error_rows:
            if source_version == current_versions[source_id]:
                latest_errors.setdefault(source_id, error)

    return {
        "data": KnowledgeDocumentPage(
            items=[
                _document_response(document, rag, latest_errors.get(document.id))
                for document, rag in rows
            ],
            page=page,
            page_size=page_size,
            total=total or 0,
        ),
        "meta": {"request_id": request.state.request_id},
    }


@router.get(
    "/knowledge-documents/{document_id}",
    response_model=KnowledgeDocumentEnvelope,
    responses=RESOURCE_RESPONSES,
)
async def get_knowledge_document(
    document_id: UUID,
    request: Request,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    document, rag_document, latest_error = await _load_document_bundle(
        session, document_id
    )
    return {
        "data": _document_response(document, rag_document, latest_error),
        "meta": {"request_id": request.state.request_id},
    }


@router.patch(
    "/knowledge-documents/{document_id}",
    response_model=KnowledgeDocumentEnvelope,
    responses=RESOURCE_RESPONSES,
)
async def update_knowledge_document(
    document_id: UUID,
    payload: KnowledgeDocumentUpdate,
    request: Request,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    document, rag_document, latest_error = await _load_document_bundle(
        session, document_id, lock=True
    )
    changes = payload.model_dump(exclude_unset=True)
    if not any(getattr(document, field) != value for field, value in changes.items()):
        return {
            "data": _document_response(document, rag_document, latest_error),
            "meta": {"request_id": request.state.request_id},
        }

    for field, value in changes.items():
        setattr(document, field, value)
    document.version += 1
    document.checksum = _checksum(
        document.document_type,
        document.title,
        document.content,
        document.locale,
        document.is_active,
    )
    _enqueue_version(session, document, rag_document)
    await session.commit()
    await session.refresh(document)
    await session.refresh(rag_document)
    return {
        "data": _document_response(document, rag_document),
        "meta": {"request_id": request.state.request_id},
    }


@router.delete(
    "/knowledge-documents/{document_id}",
    response_model=KnowledgeDocumentEnvelope,
    responses=RESOURCE_RESPONSES,
)
async def archive_knowledge_document(
    document_id: UUID,
    request: Request,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    document, rag_document, latest_error = await _load_document_bundle(
        session, document_id, lock=True
    )
    if not document.is_active:
        return {
            "data": _document_response(document, rag_document, latest_error),
            "meta": {"request_id": request.state.request_id},
        }

    document.is_active = False
    document.version += 1
    document.checksum = _checksum(
        document.document_type,
        document.title,
        document.content,
        document.locale,
        False,
    )
    _enqueue_version(session, document, rag_document)
    await session.commit()
    await session.refresh(document)
    await session.refresh(rag_document)
    return {
        "data": _document_response(document, rag_document),
        "meta": {"request_id": request.state.request_id},
    }


@router.post(
    "/knowledge-documents/{document_id}/reindex",
    response_model=KnowledgeDocumentEnvelope,
    responses=RESOURCE_RESPONSES,
)
async def reindex_knowledge_document(
    document_id: UUID,
    request: Request,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    document, rag_document, _latest_error = await _load_document_bundle(
        session, document_id, lock=True
    )
    document.version += 1
    _enqueue_version(session, document, rag_document)
    await session.commit()
    await session.refresh(document)
    await session.refresh(rag_document)
    return {
        "data": _document_response(document, rag_document),
        "meta": {"request_id": request.state.request_id},
    }


@router.get(
    "/rag-index-jobs",
    response_model=RagIndexJobListEnvelope,
    responses=AUTH_VALIDATION_RESPONSES,
)
async def list_rag_index_jobs(
    request: Request,
    source_type: Literal["product", "knowledge"] | None = Query(default=None),
    job_status: JobStatus | None = Query(
        default=None,
        alias="status",
    ),
    source_id: UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=1_000_000),
    page_size: int = Query(default=20, ge=1, le=100),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    filters = []
    if source_type is not None:
        filters.append(RagIndexJob.source_type == source_type)
    if job_status is not None:
        filters.append(RagIndexJob.status == job_status)
    if source_id is not None:
        filters.append(RagIndexJob.source_id == source_id)
    total = await session.scalar(
        select(func.count()).select_from(RagIndexJob).where(*filters)
    )
    jobs = (
        await session.scalars(
            select(RagIndexJob)
            .where(*filters)
            .order_by(
                RagIndexJob.created_at.desc(),
                RagIndexJob.source_version.desc(),
                RagIndexJob.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "data": RagIndexJobPage(
            items=[_job_response(job) for job in jobs],
            page=page,
            page_size=page_size,
            total=total or 0,
        ),
        "meta": {"request_id": request.state.request_id},
    }


@router.get(
    "/rag-index-jobs/{job_id}",
    response_model=RagIndexJobEnvelope,
    responses=JOB_RESOURCE_RESPONSES,
)
async def get_rag_index_job(
    job_id: UUID,
    request: Request,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    job = await session.get(RagIndexJob, job_id)
    if job is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="RAG_INDEX_JOB_NOT_FOUND",
            message="Không tìm thấy tác vụ indexing.",
        )
    return {
        "data": _job_response(job),
        "meta": {"request_id": request.state.request_id},
    }
