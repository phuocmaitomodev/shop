import asyncio
import sys

from app.db.session import SessionLocal
from app.return_policy_seed import verify_return_policy


async def run() -> int:
    async with SessionLocal() as session:
        try:
            report = await verify_return_policy(session)
        except Exception as exc:
            print(f"ERROR: return policy verification failed: {exc}", file=sys.stderr)
            return 1

    if not report.ok:
        for error in report.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        "Return policy verification passed: "
        f"{report.counts['knowledge_documents']} source, "
        f"{report.counts['rag_documents']} projection, "
        f"{report.counts['index_jobs']} index job(s)."
    )
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
