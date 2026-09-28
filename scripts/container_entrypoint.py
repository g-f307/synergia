from __future__ import annotations

import os
import sys

from psycopg.conninfo import make_conninfo


def main() -> None:
    if not os.environ.get("DATABASE_URL", "").strip():
        required = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")
        missing = [name for name in required if name not in os.environ]
        if missing:
            raise SystemExit(f"missing PostgreSQL settings: {', '.join(missing)}")
        os.environ["DATABASE_URL"] = make_conninfo(
            host=os.environ["PGHOST"],
            port=os.environ["PGPORT"],
            dbname=os.environ["PGDATABASE"],
            user=os.environ["PGUSER"],
            password=os.environ["PGPASSWORD"],
        )
    if len(sys.argv) < 2:
        raise SystemExit("container entrypoint requires a command")
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
