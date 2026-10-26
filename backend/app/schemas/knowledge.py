from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DocumentType = Literal[
    "faq",
    "size_guide",
    "shipping_policy",
    "return_policy",
    "promotion",
    "guide",
]
IndexStatus = Literal["pending", "indexed", "failed"]
JobStatus = Literal["pending", "processing", "succeeded", "failed"]
IndexEventType = Literal["upsert", "delete"]


class KnowledgeDocumentCreate(BaseModel):
    document_type: DocumentType
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=100_000)
    locale: str = Field(default="vi", min_length=2, max_length=10, pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    is_active: bool = True

    @field_validator("title", "content")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Không được để trống.")
        return value


class KnowledgeDocumentUpdate(BaseModel):
    document_type: DocumentType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=240)
    content: str | None = Field(default=None, min_length=1, max_length=100_000)
    locale: str | None = Field(default=None, min_length=2, max_length=10, pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    is_active: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_nulls(cls, value):
        if isinstance(value, dict):
            null_fields = [field for field, field_value in value.items() if field_value is None]
            if null_fields:
                raise ValueError("Các trường cập nhật không được là null.")
        return value

    @field_validator("title", "content")
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Không được để trống.")
        return value


class KnowledgeDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_type: DocumentType
    title: str
    content: str
    locale: str
    is_active: bool
    version: int
    checksum: str
    index_status: IndexStatus
    latest_index_error: str | None
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentEnvelope(BaseModel):
    data: KnowledgeDocumentResponse
    meta: dict[str, str]


class KnowledgeDocumentPage(BaseModel):
    items: list[KnowledgeDocumentResponse]
    page: int
    page_size: int
    total: int


class KnowledgeDocumentListEnvelope(BaseModel):
    data: KnowledgeDocumentPage
    meta: dict[str, str]


class RagIndexJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_type: Literal["product", "knowledge"]
    source_id: UUID
    source_version: int
    event_type: IndexEventType
    payload_version: int
    status: JobStatus
    attempt_count: int
    available_at: datetime
    locked_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class RagIndexJobEnvelope(BaseModel):
    data: RagIndexJobResponse
    meta: dict[str, str]


class RagIndexJobPage(BaseModel):
    items: list[RagIndexJobResponse]
    page: int
    page_size: int
    total: int


class RagIndexJobListEnvelope(BaseModel):
    data: RagIndexJobPage
    meta: dict[str, str]
