from datetime import datetime, timedelta, timezone
from time import monotonic
from uuid import uuid4

from anyio import sleep, to_thread
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, session_cookie
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.rate_limit import enforce_auth_rate_limit
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    derive_demo_reset_token,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.session import get_db_session
from app.models.auth import AuthSession, PasswordResetToken, User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    StatusEnvelope,
    UserEnvelope,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=UserEnvelope, status_code=status.HTTP_201_CREATED
)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await enforce_auth_rate_limit(request, "register")
    existing_user = await session.scalar(select(User).where(User.email == payload.email))
    if existing_user is not None:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="EMAIL_ALREADY_EXISTS",
            message="Email đã được sử dụng.",
            fields={"email": "Email đã được sử dụng."},
        )

    user = User(
        email=str(payload.email),
        password_hash=await to_thread.run_sync(hash_password, payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        role="customer",
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="EMAIL_ALREADY_EXISTS",
            message="Email đã được sử dụng.",
            fields={"email": "Email đã được sử dụng."},
        ) from exc
    await session.refresh(user)
    return {
        "data": UserResponse.model_validate(user),
        "meta": {"request_id": request.state.request_id},
    }


@router.post("/login", response_model=UserEnvelope)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await enforce_auth_rate_limit(request, "login")
    user = await session.scalar(
        select(User).where(User.email == payload.email).with_for_update()
    )
    password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    password_is_valid = await to_thread.run_sync(
        verify_password, payload.password, password_hash
    )
    if user is None or not user.is_active or not password_is_valid:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_CREDENTIALS",
            message="Email hoặc mật khẩu không đúng.",
        )

    settings = get_settings()
    token = generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.auth_session_ttl_days
    )
    session.add(
        AuthSession(
            user_id=user.id,
            refresh_token_hash=hash_token(token),
            expires_at=expires_at,
            user_agent=(request.headers.get("user-agent") or "")[:512] or None,
        )
    )
    await session.commit()
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_session_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    return {
        "data": UserResponse.model_validate(user),
        "meta": {"request_id": request.state.request_id},
    }


@router.get("/me", response_model=UserEnvelope)
async def current_user(
    request: Request, user: User = Depends(get_current_user)
) -> dict:
    return {
        "data": UserResponse.model_validate(user),
        "meta": {"request_id": request.state.request_id},
    }


@router.post("/logout", response_model=StatusEnvelope)
async def logout(
    request: Request,
    response: Response,
    token: str | None = Depends(session_cookie),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    settings = get_settings()
    if token:
        auth_session = await session.scalar(
            select(AuthSession).where(
                AuthSession.refresh_token_hash == hash_token(token),
                AuthSession.revoked_at.is_(None),
            )
        )
        if auth_session is not None:
            auth_session.revoked_at = datetime.now(timezone.utc)
            await session.commit()
    response.delete_cookie(settings.auth_cookie_name, path="/")
    return {
        "data": {"status": "logged_out"},
        "meta": {"request_id": request.state.request_id},
    }


@router.post("/forgot-password", response_model=StatusEnvelope)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    started_at = monotonic()
    await enforce_auth_rate_limit(request, "forgot-password")
    settings = get_settings()
    user = await session.scalar(
        select(User).where(User.email == payload.email).with_for_update()
    )
    token_id = uuid4()
    token = derive_demo_reset_token(
        settings.app_secret_key.get_secret_value(), token_id
    )
    token_hash = hash_token(token)
    if user is not None and user.is_active:
        now = datetime.now(timezone.utc)
        await session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        session.add(
            PasswordResetToken(
                id=token_id,
                user_id=user.id,
                token_hash=token_hash,
                expires_at=now
                + timedelta(minutes=settings.password_reset_ttl_minutes),
            )
        )
        await session.commit()
    remaining_seconds = (
        settings.forgot_response_floor_ms / 1000 - (monotonic() - started_at)
    )
    if remaining_seconds > 0:
        await sleep(remaining_seconds)
    return {
        "data": {"status": "accepted"},
        "meta": {"request_id": request.state.request_id},
    }


@router.post("/reset-password", response_model=StatusEnvelope)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await enforce_auth_rate_limit(request, "reset-password")
    settings = get_settings()
    token_hash = hash_token(payload.token)
    reset_candidate = await session.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
    )
    if reset_candidate is None:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_RESET_TOKEN",
            message="Yêu cầu đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.",
        )

    user = await session.scalar(
        select(User).where(User.id == reset_candidate.user_id).with_for_update()
    )
    reset_record = await session.scalar(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.id == reset_candidate.id,
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
        .with_for_update()
    )
    if reset_record is None:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_RESET_TOKEN",
            message="Yêu cầu đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.",
        )

    if user is None or not user.is_active:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_RESET_TOKEN",
            message="Yêu cầu đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.",
        )

    now = datetime.now(timezone.utc)
    user.password_hash = await to_thread.run_sync(
        hash_password, payload.new_password
    )
    reset_record.used_at = now
    await session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await session.commit()
    response.delete_cookie(settings.auth_cookie_name, path="/")
    return {
        "data": {"status": "password_reset"},
        "meta": {"request_id": request.state.request_id},
    }