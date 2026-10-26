import asyncio
import logging
import signal
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.rag.provider import DeterministicEmbeddingProvider
from app.rag.worker import RagIndexWorker, WorkerOptions

logger = logging.getLogger(__name__)
READY_FILE = Path("/tmp/rag-worker-ready")


class JobWorker(Protocol):
    async def run_once(self) -> bool: ...


async def run_worker_loop(
    worker: JobWorker,
    *,
    poll_seconds: float,
    stop_event: asyncio.Event,
    ready_file: Path = READY_FILE,
) -> None:
    try:
        while not stop_event.is_set():
            try:
                processed = await worker.run_once()
                ready_file.touch()
            except Exception:
                # Unexpected infrastructure failures retain the lease for recovery.
                # Avoid logging exception text because driver/provider errors may contain secrets.
                ready_file.unlink(missing_ok=True)
                logger.error("rag_worker_iteration_failed")
                processed = False
            if not processed and not stop_event.is_set():
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
                except asyncio.TimeoutError:
                    pass
    finally:
        ready_file.unlink(missing_ok=True)


async def run(stop_event: asyncio.Event | None = None) -> None:
    settings = get_settings()
    stop_event = stop_event or asyncio.Event()
    provider = DeterministicEmbeddingProvider(settings.embedding_dimension)
    worker = RagIndexWorker(
        SessionLocal,
        provider,
        WorkerOptions(
            embedding_dimension=settings.embedding_dimension,
            lock_timeout_seconds=settings.rag_worker_lock_timeout_seconds,
            provider_timeout_seconds=settings.rag_worker_provider_timeout_seconds,
            max_attempts=settings.rag_worker_max_attempts,
            retry_base_seconds=settings.rag_worker_retry_base_seconds,
            retry_max_seconds=settings.rag_worker_retry_max_seconds,
        ),
    )
    logger.info("rag_worker_started")
    await run_worker_loop(
        worker,
        poll_seconds=settings.rag_worker_poll_seconds,
        stop_event=stop_event,
    )
    logger.info("rag_worker_stopped")


async def _main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(shutdown_signal, stop_event.set)
    await run(stop_event)


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
