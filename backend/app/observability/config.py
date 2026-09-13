from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _positive_integer(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class ObservabilityConfig:
    database_url: str
    storage_root: Path
    scrape_token: str
    probe_timeout_seconds: int = 2
    worker_stale_seconds: int = 300
    queue_degraded_seconds: int = 300

    @classmethod
    def from_env(cls) -> ObservabilityConfig:
        configured_storage = os.getenv("IMPORT_STORAGE_DIR", "").strip()
        storage_root = (
            Path(configured_storage)
            if configured_storage
            else Path(__file__).resolve().parents[3] / "data" / "imports"
        )
        return cls(
            database_url=os.getenv("DATABASE_URL", "").strip(),
            storage_root=storage_root,
            scrape_token=os.getenv("OBSERVABILITY_METRICS_TOKEN", ""),
            probe_timeout_seconds=_positive_integer(
                "OBSERVABILITY_PROBE_TIMEOUT_SECONDS", 2
            ),
            worker_stale_seconds=_positive_integer(
                "OBSERVABILITY_WORKER_STALE_SECONDS", 300
            ),
            queue_degraded_seconds=_positive_integer(
                "OBSERVABILITY_QUEUE_DEGRADED_SECONDS", 300
            ),
        )

    def validate_scrape_token(self) -> None:
        if len(self.scrape_token.encode()) < 32:
            raise ValueError(
                "OBSERVABILITY_METRICS_TOKEN must contain at least 32 bytes"
            )
