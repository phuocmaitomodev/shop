from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import hash_token
from app.commerce.chat_actions import DatabaseChatActionAdapter
from app.db.session import get_db_session
from app.models.auth import AuthSession, User
from app.rag.chat import (
    ChatHistoryTurn,
    CommerceOwnershipContext,
    CommerceReadRepository,
    DeterministicChatProvider,
    GeminiChatProvider,
    orchestrate_chat,
)
from app.rag.provider import DeterministicEmbeddingProvider, GeminiEmbeddingProvider
from app.rag.commerce_reads import DatabaseCommerceReadRepository
from app.schemas.chat import ChatEnvelope, ChatRequest, ChatResponse
from app.schemas.common import ErrorEnvelope


router = APIRouter(tags=["chat"])


def get_commerce_read_repository(
    session: AsyncSession = Depends(get_db_session),
) -> CommerceReadRepository:
    return DatabaseCommerceReadRepository(session)


async def get_commerce_ownership_context(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> CommerceOwnershipContext | None:
    auth_token = request.cookies.get(settings.auth_cookie_name)
    if auth_token:
        user_id = await session.scalar(
            select(User.id)
            .join(AuthSession, AuthSession.user_id == User.id)
            .where(
                AuthSession.refresh_token_hash == hash_token(auth_token),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > datetime.now(timezone.utc),
                User.is_active.is_(True),
            )
        )
        if user_id is not None:
            return CommerceOwnershipContext(user_id=user_id)

    guest_token = request.cookies.get(settings.guest_cookie_name)
    lookup_token = request.headers.get("X-Order-Lookup-Token")
    guest_hash = (
        hash_token(guest_token)
        if guest_token is not None and 1 <= len(guest_token) <= 200
        else None
    )
    lookup_hash = (
        hash_token(lookup_token)
        if lookup_token is not None and 20 <= len(lookup_token) <= 200
        else None
    )
    if guest_hash is None and lookup_hash is None:
        return None
    return CommerceOwnershipContext(
        guest_token_hash=guest_hash,
        order_lookup_token_hash=lookup_hash,
    )


def _chat_provider(settings: Settings):
    if settings.rag_chat_provider == "gemini":
        assert settings.gemini_api_key is not None
        assert settings.gemini_model is not None
        return GeminiChatProvider(
            api_key=settings.gemini_api_key.get_secret_value(),
            model_name=settings.gemini_model,
        )
    return DeterministicChatProvider()


def _embedding_provider(settings: Settings):
    if settings.rag_embedding_provider == "gemini":
        assert settings.gemini_api_key is not None
        assert settings.gemini_embedding_model is not None
        return GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key.get_secret_value(),
            model_name=settings.gemini_embedding_model,
            dimension=settings.embedding_dimension,
            task_type="RETRIEVAL_QUERY",
        )
    return DeterministicEmbeddingProvider(settings.embedding_dimension)


@router.post(
    "/chat",
    response_model=ChatEnvelope,
    responses={
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": ErrorEnvelope,
            "description": "Tin nhắn hoặc lịch sử không hợp lệ.",
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "model": ErrorEnvelope,
            "description": "Đã vượt giới hạn yêu cầu chat.",
        },
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {
            "model": ErrorEnvelope,
            "description": "Nội dung yêu cầu vượt giới hạn.",
        },
    },
)
async def chat(
    payload: ChatRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _lookup_token: str | None = Header(
        default=None,
        min_length=20,
        max_length=200,
        alias="X-Order-Lookup-Token",
    ),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    commerce_repository: CommerceReadRepository | None = Depends(
        get_commerce_read_repository
    ),
    ownership_context: CommerceOwnershipContext | None = Depends(
        get_commerce_ownership_context
    ),
) -> dict:
    client_host = request.client.host if request.client is not None else "unknown"
    limiter: InMemoryRateLimiter = request.app.state.chat_rate_limiter
    allowed = await limiter.allow(
        f"chat:{client_host}",
        limit=settings.chat_rate_limit_requests,
        window_seconds=settings.chat_rate_limit_window_seconds,
        max_keys=settings.auth_rate_limit_max_keys,
    )
    if not allowed:
        raise AppError(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="RATE_LIMITED",
            message="Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau.",
        )
    if payload.confirmation_token is not None:
        if (
            idempotency_key is None
            or not 8 <= len(idempotency_key.strip()) <= 200
            or payload.client_message_id is None
        ):
            raise AppError(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="IDEMPOTENCY_KEY_REQUIRED",
                message="Lượt xác nhận cần Idempotency-Key và client_message_id.",
            )
    result = await orchestrate_chat(
        session=session,
        message=payload.message.strip(),
        history=tuple(
            ChatHistoryTurn(role=turn.role, content=turn.content.strip())
            for turn in payload.history
        ),
        chat_provider=_chat_provider(settings),
        embedding_provider=_embedding_provider(settings),
        commerce_repository=commerce_repository,
        ownership_context=ownership_context,
        action_context=payload.action_context,
        action_adapter=DatabaseChatActionAdapter(session, request),
        confirmation_token=payload.confirmation_token,
        idempotency_key=idempotency_key,
        client_message_id=payload.client_message_id,
    )
    return {
        "data": ChatResponse(
            answer=result.answer,
            products=[asdict(product) for product in result.products],
            sources=[asdict(source) for source in result.sources],
            status=result.status,
            proposed_action=(
                asdict(result.proposed_action) if result.proposed_action is not None else None
            ),
        ),
        "meta": {"request_id": request.state.request_id},
    }
