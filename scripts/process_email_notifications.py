from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.email_delivery import (  # noqa: E402
    EmailConfig,
    EmailDeliveryRepository,
    EmailDeliveryService,
    build_provider,
)
from app.observability import configure_logging  # noqa: E402
from app.observability.telemetry import safe_log  # noqa: E402


def main() -> int:
    configure_logging()
    config = EmailConfig.from_env()
    if not config.enabled:
        safe_log(
            logging.INFO,
            "email_worker.completed",
            outcome="disabled",
            processed_count=0,
            delivery_count=0,
            failed_count=0,
        )
        return 0
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required when email delivery is enabled")
    result = EmailDeliveryService(
        config,
        EmailDeliveryRepository(database_url),
        build_provider(config),
    ).run_once()
    safe_log(
        logging.INFO if result["failed"] == 0 else logging.WARNING,
        "email_worker.completed",
        outcome="success" if result["failed"] == 0 else "partial",
        processed_count=result["processed"],
        delivery_count=result["sent"],
        failed_count=result["failed"],
    )
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
