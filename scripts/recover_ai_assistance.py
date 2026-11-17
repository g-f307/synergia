"""Recover expired processing leases in one bounded, audited batch."""

from __future__ import annotations

import argparse
import json
import os
import sys
from uuid import UUID, uuid4

from app.ai_assistance_maintenance import run_maintenance
from app.ai_assistance_repository import PostgresAiAssistanceRepository
from app.observability.telemetry import configure_logging


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actor-id", required=True, type=UUID)
    parser.add_argument("--batch-size", type=int, default=100)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    repo = PostgresAiAssistanceRepository(os.environ["DATABASE_URL"])
    result = run_maintenance(
        repo,
        "recovery",
        args.actor_id,
        uuid4(),
        batch_size=args.batch_size,
        dry_run=not args.apply,
    )
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("ai_assistance_recovery_failed", file=sys.stderr)
        raise SystemExit(1) from None
