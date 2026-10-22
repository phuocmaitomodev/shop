from datetime import datetime, timezone

from fastapi import Depends, status
from fastapi.security import APIKeyCookie
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import hash_token
from app.db.session import get_db_session
from app.models.auth import AuthSession, User

session_cookie = APIKeyCookie(
    name=get_settings().auth_cookie_name,
    scheme_name="SessionCookie",
    auto_error=False,
)


async def get_current_user(
    token: str | None = Depends(session_cookie),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    if not token:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Vui lòng đăng nhập để tiếp tục.",
        )

    user = await session.scalar(
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            AuthSession.refresh_token_hash == hash_token(token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(timezone.utc),
            User.is_active.is_(True),
        )
    )
    if user is None:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
        )
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="ADMIN_REQUIRED",
            message="Bạn không có quyền truy cập chức năng quản trị.",
        )
    return user