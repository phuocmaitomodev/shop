import argparse
import asyncio
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import derive_demo_reset_token
from app.db.session import SessionLocal
from app.models.auth import PasswordResetToken, User


async def load_demo_reset_token(email: str) -> str | None:
    settings = get_settings()
    async with SessionLocal() as session:
        token_id = await session.scalar(
            select(PasswordResetToken.id)
            .join(User, User.id == PasswordResetToken.user_id)
            .where(
                User.email == email.strip().lower(),
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > datetime.now(timezone.utc),
            )
            .order_by(PasswordResetToken.created_at.desc())
            .limit(1)
        )
    if token_id is None:
        return None
    return derive_demo_reset_token(
        settings.app_secret_key.get_secret_value(), token_id
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read the current local demo password-reset token."
    )
    parser.add_argument("email")
    args = parser.parse_args()
    token = asyncio.run(load_demo_reset_token(args.email))
    if token is None:
        sys.stderr.write("Không có yêu cầu đặt lại mật khẩu còn hiệu lực.\n")
        return 1
    sys.stdout.write(f"{token}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
