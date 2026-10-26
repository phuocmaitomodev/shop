from dataclasses import asdict

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.rate_limit import InMemoryRateLimiter
from app.db.session import get_db_session
from app.rag.chat import (
    ChatHistoryTurn,
    DeterministicChatProvider,
    GeminiChatProvider,
    orchestrate_chat,
)
from app.rag.provider import DeterministicEmbeddingProvider, GeminiEmbeddingProvider
from app.schemas.chat import ChatEnvelope, ChatRequest, ChatResponse
from app.schemas.common import ErrorEnvelope


router = APIRouter(tags=["chat"])


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
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
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
    result = await orchestrate_chat(
        session=session,
        message=payload.message.strip(),
        history=tuple(
            ChatHistoryTurn(role=turn.role, content=turn.content.strip())
            for turn in payload.history
        ),
        chat_provider=_chat_provider(settings),
        embedding_provider=_embedding_provider(settings),
    )
    return {
        "data": ChatResponse(
            answer=result.answer,
            products=[asdict(product) for product in result.products],
            sources=[asdict(source) for source in result.sources],
            status=result.status,
        ),
        "meta": {"request_id": request.state.request_id},
    }
