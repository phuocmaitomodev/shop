from fastapi import APIRouter, Depends, Request

from app.api.dependencies import require_admin
from app.models.auth import User
from app.schemas.auth import UserEnvelope, UserResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/auth-check", response_model=UserEnvelope)
async def admin_auth_check(
    request: Request, user: User = Depends(require_admin)
) -> dict:
    return {
        "data": UserResponse.model_validate(user),
        "meta": {"request_id": request.state.request_id},
    }