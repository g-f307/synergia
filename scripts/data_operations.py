from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.data_operations import (  # noqa: E402
    DataOperationConfig,
    DataOperationError,
    create_backup,
    purge_dataset,
    restore_backup,
    verify_restoration,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Operações controladas de retenção e recuperação do SYNERGIA"
    )
    commands = result.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--destination", type=Path, required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--bundle", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--bundle", type=Path, required=True)
    retention = commands.add_parser("retention")
    retention.add_argument("--dataset", required=True)
    retention.add_argument("--apply", action="store_true")
    retention.add_argument("--transient-retention-days", type=int, default=90)
    return result


def main(arguments: list[str] | None = None) -> int:
    args = parser().parse_args(arguments)
    failure_correlation_id = str(uuid4())
    try:
        config = DataOperationConfig.from_env()
        if args.command == "backup":
            result = create_backup(config, args.destination)
        elif args.command == "restore":
            result = restore_backup(config, args.bundle)
        elif args.command == "verify":
            result = verify_restoration(config, args.bundle)
        else:
            result = purge_dataset(
                config,
                args.dataset,
                apply=args.apply,
                transient_retention_days=args.transient_retention_days,
            )
    except DataOperationError as exc:
        print(
            json.dumps(
                {
                    "correlation_id": failure_correlation_id,
                    "operation": args.command,
                    "outcome": "failed",
                    "reason_code": exc.reason_code,
                },
                sort_keys=True,
            )
        )
        return 1
    except Exception:
        # The CLI is an evidence boundary: infrastructure details and paths must
        # never escape through an unhandled traceback.
        print(
            json.dumps(
                {
                    "correlation_id": failure_correlation_id,
                    "operation": args.command,
                    "outcome": "failed",
                    "reason_code": "operation_failed",
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
