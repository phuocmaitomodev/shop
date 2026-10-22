import asyncio
from collections import defaultdict, deque
from time import monotonic

from fastapi import Request, status

from app.core.config import get_settings
from app.core.errors import AppError


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
        max_keys: int = 10_000,
    ) -> bool:
        now = monotonic()
        cutoff = now - window_seconds
        async with self._lock:
            if key not in self._attempts and len(self._attempts) >= max_keys:
                for candidate_key in list(self._attempts):
                    candidate_attempts = self._attempts[candidate_key]
                    while candidate_attempts and candidate_attempts[0] <= cutoff:
                        candidate_attempts.popleft()
                    if not candidate_attempts:
                        del self._attempts[candidate_key]
                if len(self._attempts) >= max_keys:
                    return False
            attempts = self._attempts[key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= limit:
                return False
            attempts.append(now)
            return True


async def enforce_auth_rate_limit(request: Request, scope: str) -> None:
    settings = get_settings()
    client_host = request.client.host if request.client is not None else "unknown"
    limiter: InMemoryRateLimiter = request.app.state.auth_rate_limiter
    allowed = await limiter.allow(
        f"{scope}:{client_host}",
        limit=settings.auth_rate_limit_attempts,
        window_seconds=settings.auth_rate_limit_window_seconds,
        max_keys=settings.auth_rate_limit_max_keys,
    )
    if not allowed:
        raise AppError(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="RATE_LIMITED",
            message="Bạn đã thử quá nhiều lần. Vui lòng thử lại sau.",
        )
