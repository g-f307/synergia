"""Expire bounded batches of assistance results; safe count-only dry-run."""

from __future__ import annotations

import argparse
import json
import os
import sys
from uuid import UUID, uuid4

from app.ai_assistance_config import AiAssistanceConfig
from app.ai_assistance_maintenance import run_maintenance
from app.ai_assistance_repository import PostgresAiAssistanceRepository
from app.observability.telemetry import configure_logging


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--actor-id", required=True, type=UUID)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = AiAssistanceConfig.from_environment(os.environ)
    repo = PostgresAiAssistanceRepository(
        os.environ["DATABASE_URL"], config.retention_days
    )
    result = run_maintenance(
        repo,
        "retention",
        args.actor_id,
        uuid4(),
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("ai_assistance_cleanup_failed", file=sys.stderr)
        raise SystemExit(1) from None
