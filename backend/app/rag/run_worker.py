import asyncio
import logging
from pathlib import Path

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.rag.provider import DeterministicEmbeddingProvider
from app.rag.worker import RagIndexWorker, WorkerOptions

logger = logging.getLogger(__name__)
READY_FILE = Path("/tmp/rag-worker-ready")


async def run() -> None:
    settings = get_settings()
    provider = DeterministicEmbeddingProvider(settings.embedding_dimension)
    worker = RagIndexWorker(
        SessionLocal,
        provider,
        WorkerOptions(
            embedding_dimension=settings.embedding_dimension,
            lock_timeout_seconds=settings.rag_worker_lock_timeout_seconds,
            max_attempts=settings.rag_worker_max_attempts,
            retry_base_seconds=settings.rag_worker_retry_base_seconds,
            retry_max_seconds=settings.rag_worker_retry_max_seconds,
        ),
    )
    logger.info("rag_worker_started")
    try:
        while True:
            try:
                processed = await worker.run_once()
                READY_FILE.touch()
            except Exception:
                # Unexpected infrastructure failures retain the lease for recovery.
                # Avoid logging exception text because driver/provider errors may contain secrets.
                READY_FILE.unlink(missing_ok=True)
                logger.error("rag_worker_iteration_failed")
                processed = False
            if not processed:
                await asyncio.sleep(settings.rag_worker_poll_seconds)
    finally:
        READY_FILE.unlink(missing_ok=True)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
