from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_customer
from app.db.session import get_db_session
from app.models.auth import User
from app.schemas.auth import ProfileUpdateRequest, UserEnvelope, UserResponse
from app.schemas.common import ErrorEnvelope

router = APIRouter(prefix="/account", tags=["account"])


@router.get(
    "/profile",
    response_model=UserEnvelope,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
        status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    },
)
async def get_profile(
    request: Request,
    user: User = Depends(require_customer),
) -> dict:
    return {
        "data": UserResponse.model_validate(user),
        "meta": {"request_id": request.state.request_id},
    }


@router.patch(
    "/profile",
    response_model=UserEnvelope,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
        status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorEnvelope},
    },
)
async def update_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await session.commit()
    await session.refresh(user)
    return {
        "data": UserResponse.model_validate(user),
        "meta": {"request_id": request.state.request_id},
    }
