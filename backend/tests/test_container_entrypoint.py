from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "scripts" / "container_entrypoint.py"


def test_builds_safe_conninfo_for_reserved_password_characters() -> None:
    password = "synthetic-p@ss:word/with#chars\\and space"
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    environment.update(
        {
            "PGHOST": "postgres",
            "PGPORT": "5432",
            "PGDATABASE": "synergia",
            "PGUSER": "synergia",
            "PGPASSWORD": password,
        }
    )
    command = [
        sys.executable,
        str(ENTRYPOINT),
        sys.executable,
        "-c",
        "import json, os; print(json.dumps({'url': os.environ['DATABASE_URL']}))",
    ]

    result = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )

    parsed = conninfo_to_dict(json.loads(result.stdout)["url"])
    assert parsed == {
        "user": "synergia",
        "password": password,
        "dbname": "synergia",
        "host": "postgres",
        "port": "5432",
    }
