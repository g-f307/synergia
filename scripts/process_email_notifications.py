from __future__ import annotations

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


def main() -> int:
    config = EmailConfig.from_env()
    if not config.enabled:
        print("Email delivery is disabled; no attempts were created.")
        return 0
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required when email delivery is enabled")
    result = EmailDeliveryService(
        config,
        EmailDeliveryRepository(database_url),
        build_provider(config),
    ).run_once()
    print(
        "Email delivery completed: "
        f"processed={result['processed']} sent={result['sent']} "
        f"failed={result['failed']}"
    )
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
