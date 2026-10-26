import asyncio
from datetime import datetime, timedelta, timezone

from app.rag.healthcheck import DEFAULT_MAX_AGE_SECONDS, is_ready_file_fresh
from app.rag.run_worker import run_worker_loop


def test_healthcheck_rejects_missing_and_stale_ready_file(tmp_path) -> None:
    assert DEFAULT_MAX_AGE_SECONDS == 150.0
    ready_file = tmp_path / "rag-worker-ready"
    now = datetime.now(timezone.utc)

    assert is_ready_file_fresh(ready_file, max_age_seconds=30, now=now) is False

    ready_file.touch()
    fresh_time = datetime.fromtimestamp(ready_file.stat().st_mtime, timezone.utc)
    assert (
        is_ready_file_fresh(
            ready_file,
            max_age_seconds=30,
            now=fresh_time + timedelta(seconds=29),
        )
        is True
    )
    assert (
        is_ready_file_fresh(
            ready_file,
            max_age_seconds=30,
            now=fresh_time + timedelta(seconds=31),
        )
        is False
    )


def test_worker_loop_stops_without_waiting_full_poll_interval_and_cleans_marker(
    tmp_path,
) -> None:
    class IdleWorker:
        def __init__(self) -> None:
            self.calls = 0

        async def run_once(self) -> bool:
            self.calls += 1
            return False

    async def exercise() -> None:
        worker = IdleWorker()
        stop_event = asyncio.Event()
        ready_file = tmp_path / "rag-worker-ready"

        task = asyncio.create_task(
            run_worker_loop(
                worker,
                poll_seconds=60,
                stop_event=stop_event,
                ready_file=ready_file,
            )
        )
        for _ in range(20):
            if ready_file.exists():
                break
            await asyncio.sleep(0)

        assert ready_file.exists()
        stop_event.set()
        await asyncio.wait_for(task, timeout=1)

        assert worker.calls == 1
        assert not ready_file.exists()

    asyncio.run(exercise())
