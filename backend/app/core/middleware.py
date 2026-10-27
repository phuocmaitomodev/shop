import logging
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import internal_error_response

logger = logging.getLogger("app.request")
MAX_CHAT_BODY_BYTES = 32_768


class ChatBodyLimitMiddleware:
    """Bound the public chat body before FastAPI parses JSON."""

    def __init__(self, app: ASGIApp, max_body_bytes: int = MAX_CHAT_BODY_BYTES) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != "/api/v1/chat":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_body_bytes:
                    await self._reject(scope, send)
                    return
            except ValueError:
                await self._reject(scope, send)
                return

        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                await self._reject(scope, send)
                return
            body = message.get("body", b"")
            total += len(body)
            if total > self.max_body_bytes:
                await self._reject(scope, send)
                return
            chunks.append(body)
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if replayed:
                return {"type": "http.request", "body": b"", "more_body": False}
            replayed = True
            return {
                "type": "http.request",
                "body": b"".join(chunks),
                "more_body": False,
            }

        await self.app(scope, replay, send)

    async def _reject(self, scope: Scope, send: Send) -> None:
        request_id = scope.get("state", {}).get("request_id", "unknown")
        response = JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "REQUEST_TOO_LARGE",
                    "message": "Nội dung yêu cầu quá lớn.",
                    "fields": {},
                    "details": {},
                },
                "meta": {"request_id": request_id},
            },
        )
        await response(scope, receive=lambda: None, send=send)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception:
            logger.error(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                },
            )
            response = internal_error_response(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
            },
        )
        return response
