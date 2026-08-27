from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "database" / "migrations"
SYNTHETIC_DATA = ROOT / "data" / "synthetic"


def validate_migrations() -> None:
    migrations = sorted(MIGRATIONS.glob("*.sql"))
    if not migrations:
        raise ValueError("Nenhuma migration SQL foi encontrada")

    for migration in migrations:
        sql = migration.read_text(encoding="utf-8").strip()
        if not sql:
            raise ValueError(f"Migration vazia: {migration.relative_to(ROOT)}")
        subprocess.run(
            [
                "psql",
                "--set=ON_ERROR_STOP=1",
                "--single-transaction",
                f"--file={migration}",
            ],
            check=True,
        )
    print(f"Migrations SQL validadas: {len(migrations)}")


def validate_synthetic_data() -> None:
    files = [path for path in SYNTHETIC_DATA.iterdir() if path.name != ".gitkeep"]
    supported = {".csv", ".json"}
    unsupported = [path for path in files if path.suffix.lower() not in supported]
    if unsupported:
        names = ", ".join(path.name for path in unsupported)
        raise ValueError(f"Formatos sintéticos não suportados: {names}")

    for path in files:
        if path.suffix.lower() == ".json":
            json.loads(path.read_text(encoding="utf-8"))
        else:
            with path.open(encoding="utf-8", newline="") as source:
                header = next(csv.reader(source), None)
                if not header or any(not column.strip() for column in header):
                    raise ValueError(f"CSV sem cabeçalho válido: {path.name}")
    print(f"Arquivos sintéticos validados: {len(files)}")


if __name__ == "__main__":
    validate_migrations()
    validate_synthetic_data()
