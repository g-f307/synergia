"""Inspect by default; resolve uncertain SMTP only after explicit external evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.email_reconciliation import EmailReconciliationRepository  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery_id", type=UUID)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--resolution", choices=("accepted", "not_accepted"))
    parser.add_argument("--evidence", choices=("smtp_log", "recipient_confirmation"))
    parser.add_argument("--request-id", type=UUID)
    parser.add_argument("--actor-id", type=UUID)
    parser.add_argument("--workers-stopped", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args()
    if args.apply and not all(
        (
            args.resolution,
            args.evidence,
            args.request_id,
            args.actor_id,
            args.workers_stopped,
        )
    ):
        parser.error(
            "--apply requires resolution, evidence, request-id, actor-id "
            "and workers-stopped"
        )
    if not args.apply and any(
        (
            args.resolution,
            args.evidence,
            args.request_id,
            args.actor_id,
            args.workers_stopped,
        )
    ):
        parser.error("resolution arguments require --apply")
    if not 1 <= args.max_attempts <= 10:
        parser.error("max-attempts must be between 1 and 10")
    if args.resolution == "not_accepted" and args.evidence != "smtp_log":
        parser.error("not_accepted requires positive evidence from SMTP logs")
    database = os.getenv("DATABASE_URL", "").strip()
    if not database:
        parser.error("DATABASE_URL is required")
    try:
        repository = EmailReconciliationRepository(database)
        result = (
            repository.reconcile(
                args.delivery_id,
                resolution=args.resolution,
                evidence=args.evidence,
                request_id=args.request_id,
                actor_id=args.actor_id,
                workers_stopped=args.workers_stopped,
                max_attempts=args.max_attempts,
            )
            if args.apply
            else repository.inspect(args.delivery_id)
        )
    except ValueError:
        print(json.dumps({"error_code": "smtp_reconciliation_rejected"}))
        return 2
    except Exception:
        print(json.dumps({"error_code": "smtp_reconciliation_unavailable"}))
        return 1
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
