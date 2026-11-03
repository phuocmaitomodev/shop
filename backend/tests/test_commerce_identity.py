from datetime import datetime, timezone

import pytest
from fastapi import Response

from app.commerce.identity import (
    issue_confirmation_token,
    issue_guest_token,
    set_guest_cookie,
)
from app.core.security import hash_token


def test_guest_token_is_opaque_hashed_and_expiring(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.commerce.identity.generate_token", lambda: "opaque-test-token"
    )
    now = datetime(2026, 11, 3, 4, 0, tzinfo=timezone.utc)

    token = issue_guest_token(ttl_days=30, now=now)

    assert token.raw == "opaque-test-token"
    assert token.digest == hash_token(token.raw)
    assert token.digest != token.raw
    assert token.expires_at == datetime(2026, 12, 3, 4, 0, tzinfo=timezone.utc)


def test_confirmation_token_rejects_ttl_above_five_minutes() -> None:
    with pytest.raises(ValueError, match="300 seconds"):
        issue_confirmation_token(ttl_seconds=301)


def test_guest_cookie_is_http_only_lax_and_bounded() -> None:
    response = Response()

    set_guest_cookie(
        response,
        name="shop_guest",
        token="opaque-test-token",
        max_age=120,
        secure=True,
    )

    cookie = response.headers["set-cookie"]
    assert "shop_guest=opaque-test-token" in cookie
    assert "HttpOnly" in cookie
    assert "Max-Age=120" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" in cookie
