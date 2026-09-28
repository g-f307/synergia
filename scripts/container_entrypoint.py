from __future__ import annotations

import os
import sys

from app.container_runtime import build_database_conninfo


def main() -> None:
    if not os.environ.get("DATABASE_URL", "").strip():
        try:
            os.environ["DATABASE_URL"] = build_database_conninfo(os.environ)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    if len(sys.argv) < 2:
        raise SystemExit("container entrypoint requires a command")
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
