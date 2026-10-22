from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_db_session

router = APIRouter(prefix="/health", tags=["health"])


def _success(request: Request, status: str) -> dict:
    return {
        "data": {"status": status},
        "meta": {"request_id": request.state.request_id},
    }


@router.get("/live")
async def liveness(request: Request) -> dict:
    return _success(request, "healthy")


@router.get("/ready")
async def readiness(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise AppError(
            status_code=503,
            code="DATABASE_UNAVAILABLE",
            message="Cơ sở dữ liệu tạm thời không khả dụng.",
        ) from exc
    return _success(request, "ready")
