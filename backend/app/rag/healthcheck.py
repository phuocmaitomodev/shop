import os
from datetime import datetime, timezone
from pathlib import Path


READY_FILE = Path("/tmp/rag-worker-ready")
DEFAULT_MAX_AGE_SECONDS = 150.0


def is_ready_file_fresh(
    ready_file: Path = READY_FILE,
    *,
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
    now: datetime | None = None,
) -> bool:
    if max_age_seconds <= 0:
        return False
    try:
        modified_at = datetime.fromtimestamp(ready_file.stat().st_mtime, timezone.utc)
    except OSError:
        return False
    checked_at = now or datetime.now(timezone.utc)
    age_seconds = (checked_at - modified_at).total_seconds()
    return 0 <= age_seconds <= max_age_seconds


def main() -> None:
    try:
        max_age_seconds = float(
            os.getenv(
                "RAG_WORKER_HEALTH_MAX_AGE_SECONDS",
                str(DEFAULT_MAX_AGE_SECONDS),
            )
        )
    except ValueError:
        raise SystemExit(1) from None
    raise SystemExit(
        0 if is_ready_file_fresh(max_age_seconds=max_age_seconds) else 1
    )


if __name__ == "__main__":
    main()
