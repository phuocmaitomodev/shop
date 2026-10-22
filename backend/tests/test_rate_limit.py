import pytest

from app.core.rate_limit import InMemoryRateLimiter


@pytest.mark.asyncio
async def test_auth_rate_limiter_rejects_attempts_over_limit() -> None:
    limiter = InMemoryRateLimiter()

    assert await limiter.allow("login:127.0.0.1", limit=1, window_seconds=60)
    assert not await limiter.allow("login:127.0.0.1", limit=1, window_seconds=60)


@pytest.mark.asyncio
async def test_auth_rate_limiter_bounds_distinct_client_keys() -> None:
    limiter = InMemoryRateLimiter()

    assert await limiter.allow(
        "login:client-1", limit=1, window_seconds=60, max_keys=2
    )
    assert await limiter.allow(
        "login:client-2", limit=1, window_seconds=60, max_keys=2
    )
    assert not await limiter.allow(
        "login:client-3", limit=1, window_seconds=60, max_keys=2
    )
