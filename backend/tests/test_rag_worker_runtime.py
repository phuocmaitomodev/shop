import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.rag import run_worker as run_worker_module
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


def test_run_configures_logging_before_lifecycle_events_without_sensitive_fields(
    monkeypatch,
) -> None:
    sensitive_value = "postgresql://user:super-secret@example.invalid/shop"
    events: list[tuple] = []
    settings = SimpleNamespace(
        app_secret_key=sensitive_value,
        database_url=sensitive_value,
        log_level="DEBUG",
        embedding_dimension=768,
        rag_worker_lock_timeout_seconds=300,
        rag_worker_provider_timeout_seconds=120,
        rag_worker_max_attempts=5,
        rag_worker_retry_base_seconds=5,
        rag_worker_retry_max_seconds=300,
        rag_worker_poll_seconds=2,
    )

    class RecordingLogger:
        def info(self, message: str, *args: object, **kwargs: object) -> None:
            events.append(("log", message, args, kwargs))

    async def fake_worker_loop(*args: object, **kwargs: object) -> None:
        events.append(("worker_loop",))

    monkeypatch.setattr(run_worker_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        run_worker_module,
        "configure_logging",
        lambda level: events.append(("configure_logging", level)),
        raising=False,
    )
    monkeypatch.setattr(
        run_worker_module, "DeterministicEmbeddingProvider", lambda dimension: object()
    )
    monkeypatch.setattr(run_worker_module, "RagIndexWorker", lambda *args: object())
    monkeypatch.setattr(run_worker_module, "run_worker_loop", fake_worker_loop)
    monkeypatch.setattr(run_worker_module, "logger", RecordingLogger())

    asyncio.run(run_worker_module.run(asyncio.Event()))

    assert events == [
        ("configure_logging", "DEBUG"),
        ("log", "rag_worker_started", (), {}),
        ("worker_loop",),
        ("log", "rag_worker_stopped", (), {}),
    ]
    assert sensitive_value not in repr(events)
