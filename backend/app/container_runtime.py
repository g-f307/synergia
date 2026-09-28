from __future__ import annotations

from collections.abc import Mapping

from psycopg.conninfo import make_conninfo

POSTGRES_ENVIRONMENT_VARIABLES = (
    "PGHOST",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGPASSWORD",
)


def build_database_conninfo(environment: Mapping[str, str]) -> str:
    missing = [
        name
        for name in POSTGRES_ENVIRONMENT_VARIABLES
        if name not in environment
    ]
    if missing:
        raise ValueError(f"missing PostgreSQL settings: {', '.join(missing)}")
    return make_conninfo(
        host=environment["PGHOST"],
        port=environment["PGPORT"],
        dbname=environment["PGDATABASE"],
        user=environment["PGUSER"],
        password=environment["PGPASSWORD"],
    )
