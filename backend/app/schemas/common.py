from typing import Any

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    fields: dict[str, str]
    details: dict[str, Any]


class ErrorMeta(BaseModel):
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody
    meta: ErrorMeta
