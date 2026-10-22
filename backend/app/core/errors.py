from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        fields: dict[str, str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields or {}
        self.details = details or {}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    fields: dict[str, str] | None = None,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "fields": fields or {},
                "details": details or {},
            },
            "meta": {"request_id": _request_id(request)},
        },
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        fields=exc.fields,
        details=exc.details,
    )


async def http_error_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    if exc.status_code == 404:
        return _error_response(
            request,
            status_code=404,
            code="NOT_FOUND",
            message="Không tìm thấy tài nguyên.",
        )
    return _error_response(
        request,
        status_code=exc.status_code,
        code="HTTP_ERROR",
        message=str(exc.detail),
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    fields = {
        ".".join(str(part) for part in error["loc"] if part != "body"): error["msg"]
        for error in exc.errors()
    }
    return _error_response(
        request,
        status_code=422,
        code="VALIDATION_ERROR",
        message="Dữ liệu đầu vào không hợp lệ.",
        fields=fields,
    )


def internal_error_response(request: Request) -> JSONResponse:
    return _error_response(
        request,
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="Đã xảy ra lỗi không mong muốn.",
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return internal_error_response(request)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
