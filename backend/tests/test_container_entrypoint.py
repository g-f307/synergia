from psycopg.conninfo import conninfo_to_dict

from app.container_runtime import build_database_conninfo


def test_builds_safe_conninfo_for_reserved_password_characters() -> None:
    password = "synthetic-p@ss:word/with#chars\\and space"
    environment = {
        "PGHOST": "postgres",
        "PGPORT": "5432",
        "PGDATABASE": "synergia",
        "PGUSER": "synergia",
        "PGPASSWORD": password,
    }

    parsed = conninfo_to_dict(build_database_conninfo(environment))
    assert parsed == {
        "user": "synergia",
        "password": password,
        "dbname": "synergia",
        "host": "postgres",
        "port": "5432",
    }
