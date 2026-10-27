import asyncio
import sys

from app.db.session import SessionLocal
from app.return_policy_seed import (
    ReturnPolicySeedConflictError,
    seed_return_policy,
    verify_return_policy,
)


async def run() -> int:
    async with SessionLocal() as session:
        try:
            await seed_return_policy(session)
            report = await verify_return_policy(session)
            if not report.ok:
                await session.rollback()
                for error in report.errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                return 1
            await session.commit()
        except ReturnPolicySeedConflictError as exc:
            await session.rollback()
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            await session.rollback()
            print(f"ERROR: return policy seed failed: {exc}", file=sys.stderr)
            return 1

    print(
        "Return policy seed complete: "
        f"versioned source with {report.counts['index_jobs']} index job(s)."
    )
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
