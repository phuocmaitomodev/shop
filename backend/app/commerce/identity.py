from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Response

from app.core.security import generate_token, hash_token


@dataclass(frozen=True)
class OpaqueToken:
    raw: str
    digest: str
    expires_at: datetime


def _issue_token(*, ttl: timedelta, now: datetime | None = None) -> OpaqueToken:
    if ttl <= timedelta(0):
        raise ValueError("token TTL must be positive")
    issued_at = now or datetime.now(timezone.utc)
    if issued_at.tzinfo is None:
        raise ValueError("token issue time must be timezone-aware")
    raw = generate_token()
    return OpaqueToken(
        raw=raw,
        digest=hash_token(raw),
        expires_at=issued_at + ttl,
    )


def issue_guest_token(
    *, ttl_days: int, now: datetime | None = None
) -> OpaqueToken:
    return _issue_token(ttl=timedelta(days=ttl_days), now=now)


def issue_confirmation_token(
    *, ttl_seconds: int, now: datetime | None = None
) -> OpaqueToken:
    if ttl_seconds > 300:
        raise ValueError("confirmation token TTL cannot exceed 300 seconds")
    return _issue_token(ttl=timedelta(seconds=ttl_seconds), now=now)


def set_guest_cookie(
    response: Response,
    *,
    name: str,
    token: str,
    max_age: int,
    secure: bool,
) -> None:
    if max_age <= 0:
        raise ValueError("guest cookie max_age must be positive")
    response.set_cookie(
        key=name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
