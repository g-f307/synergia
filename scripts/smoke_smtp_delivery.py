"""Inspect one notification; send only with both explicit opt-in flags."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.email_config import EmailConfig  # noqa: E402
from app.email_smoke import SMTPEmailSmoke  # noqa: E402
from app.observability import configure_logging  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notification-id", required=True, type=UUID)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--allow-real-send", action="store_true")
    args = parser.parse_args()
    if args.send != args.allow_real_send:
        parser.error("real delivery requires both --send and --allow-real-send")
    configure_logging()
    try:
        config = EmailConfig.from_env()
        database = os.getenv("DATABASE_URL", "").strip()
        if not database:
            raise ValueError("smtp_smoke_database_required")
        result = SMTPEmailSmoke(config, database).run(
            args.notification_id, send=args.send
        )
    except ValueError:
        print(json.dumps({"error_code": "smtp_smoke_configuration_or_target_invalid"}))
        return 2
    except Exception:
        print(json.dumps({"error_code": "smtp_smoke_unavailable"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    if not args.send:
        return 0 if result["ready"] else 2
    return 0 if result["outcome"] in {"accepted", "already_accepted"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
