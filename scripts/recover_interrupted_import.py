from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.import_recovery import ImportRecoveryError, recover_import  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspeciona ou retoma uma importação interrompida"
    )
    parser.add_argument("execution_id", help="ID exato da execução")
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument(
        "--apply", action="store_true", help="retomar após parar os workers de upload"
    )
    args = parser.parse_args()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL é obrigatório")
    try:
        result = recover_import(
            database_url, args.storage_root, args.execution_id, apply=args.apply
        )
    except ImportRecoveryError as exc:
        print(
            json.dumps(
                {"execution_id": args.execution_id, "error": str(exc)},
                ensure_ascii=False,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
