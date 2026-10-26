import asyncio
import sys

from app.catalog_seed import SeedConflictError, verify_catalog_idempotence
from app.db.session import SessionLocal


async def run() -> int:
    async with SessionLocal() as session:
        try:
            report = await verify_catalog_idempotence(session)
            if not report.ok:
                await session.rollback()
                for error in report.errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                return 1
            await session.commit()
        except SeedConflictError as exc:
            await session.rollback()
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            await session.rollback()
            print(f"ERROR: catalog verification failed: {exc}", file=sys.stderr)
            return 1

    print(
        "Catalog verification passed: canonical identities and fields are valid; "
        "reseed produced an identical snapshot "
        f"({report.counts['categories']} categories, "
        f"{report.counts['products']} products, "
        f"{report.counts['variants']} variants)."
    )
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
