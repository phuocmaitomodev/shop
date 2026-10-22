import logging
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.errors import internal_error_response

logger = logging.getLogger("app.request")


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
