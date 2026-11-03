from __future__ import annotations

import os
import re
import sys

from app.container_runtime import (
    build_database_conninfo,
    validate_deployment_environment,
)


def main() -> None:
    try:
        selected_environment = validate_deployment_environment(os.environ)
    except ValueError as exc:
        raise SystemExit(f"invalid deployment configuration: {exc}") from exc
    revision = os.environ.get("SYNERGIA_BUILD_REVISION", "unknown")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        revision = "unknown"
    print(
        f"synergia startup: environment={selected_environment} revision={revision}",
        file=sys.stderr,
        flush=True,
    )
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
