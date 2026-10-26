from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import ChatBodyLimitMiddleware, RequestContextMiddleware
from app.core.rate_limit import InMemoryRateLimiter


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    application = FastAPI(title=settings.app_name)
    application.state.auth_rate_limiter = InMemoryRateLimiter()
    application.state.chat_rate_limiter = InMemoryRateLimiter()
    application.add_middleware(ChatBodyLimitMiddleware)
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(application)
    application.include_router(api_router)
    application.mount(
        "/media/placeholders",
        StaticFiles(directory=Path(__file__).parent / "static" / "placeholders"),
        name="catalog-placeholders",
    )
    return application


app = create_app()
