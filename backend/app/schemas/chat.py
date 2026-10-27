from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ChatHistoryRequest(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1000)

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("content must not be blank")
        return normalized


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatHistoryRequest] = Field(default_factory=list, max_length=6)

    @field_validator("message")
    @classmethod
    def reject_blank_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized


class ChatProductResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    image_url: str | None
    effective_price: int
    available_colors: list[str]
    available_sizes: list[str]
    in_stock: bool
    url: str


class ChatSourceResponse(BaseModel):
    source_type: Literal["product", "knowledge"]
    source_id: UUID
    rag_document_id: UUID
    chunk_ids: list[UUID]
    product_id: UUID | None
    knowledge_type: Literal["return_policy"] | None
    title: str


class ChatResponse(BaseModel):
    answer: str
    products: list[ChatProductResponse]
    sources: list[ChatSourceResponse]
    status: Literal[
        "ok", "insufficient_data", "out_of_scope", "provider_unavailable"
    ]


class ChatEnvelope(BaseModel):
    data: ChatResponse
    meta: dict[str, str]
