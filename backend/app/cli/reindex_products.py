import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import SessionLocal
from app.rag.product_projection import (
    ProductProjectionSyncResult,
    sync_product_projections,
)


async def run_reindex(
    session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
) -> ProductProjectionSyncResult:
    async with session_factory() as session, session.begin():
        return await sync_product_projections(session)


async def _main() -> None:
    result = await run_reindex()
    print(
        "Product projection sync completed: "
        f"created={result.created} updated={result.updated} "
        f"deactivated={result.deactivated}"
    )


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
