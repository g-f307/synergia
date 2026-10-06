from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
from pathlib import Path

try:
    from generate_homologation_fixture import (
        validate_manifest as validate_homologation_manifest,
    )
    from generate_synthetic_data import validate_manifest
except ModuleNotFoundError:
    from scripts.generate_homologation_fixture import (
        validate_manifest as validate_homologation_manifest,
    )
    from scripts.generate_synthetic_data import validate_manifest
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "database" / "migrations"
SYNTHETIC_DATA = ROOT / "data" / "synthetic"


def psql_command() -> list[str]:
    if shutil.which("psql"):
        return ["psql"]
    if not shutil.which("docker"):
        raise RuntimeError("psql e Docker Compose não estão disponíveis")
    return [
        "docker",
        "compose",
        "exec",
        "-T",
        "postgres",
        "psql",
        "--username",
        os.getenv("PGUSER", "synergia"),
        "--dbname",
        os.getenv("PGDATABASE", "synergia"),
    ]


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
                *psql_command(),
                "--set=ON_ERROR_STOP=1",
                "--single-transaction",
            ],
            input=sql.encode("utf-8"),
            check=True,
        )
    print(f"Migrations SQL validadas: {len(migrations)}")


def validate_synthetic_data() -> None:
    supported = {".csv", ".json", ".xlsx"}
    files = [
        path
        for path in SYNTHETIC_DATA.rglob("*")
        if path.is_file() and path.suffix.lower() in supported
    ]

    for path in files:
        if path.name == "manifest.json":
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if "contains_real_data" in manifest:
                validate_homologation_manifest(path)
            else:
                validate_manifest(path)
        elif path.suffix.lower() == ".json":
            document = json.loads(path.read_text(encoding="utf-8"))
            if "cases" in document and "dataset_version" in document:
                validate_operational_manifest(path, document)
        elif path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8", newline="") as source:
                header = next(csv.reader(source), None)
                if not header or any(not column.strip() for column in header):
                    raise ValueError(f"CSV sem cabeçalho válido: {path.name}")
        else:
            workbook = load_workbook(path, read_only=True, data_only=False)
            try:
                rows = workbook.active.iter_rows(values_only=True)
                has_header = any(
                    len([value for value in row if str(value or "").strip()]) >= 2
                    for _, row in zip(range(25), rows, strict=False)
                )
                if not has_header:
                    raise ValueError(f"XLSX sem cabeçalho válido: {path.name}")
            finally:
                workbook.close()
    print(f"Arquivos sintéticos validados: {len(files)}")


def validate_operational_manifest(path: Path, manifest: dict) -> None:
    """Validate the frozen manifest used by the local operational PoC."""
    cases = manifest.get("cases")
    if not isinstance(manifest.get("dataset_version"), str) or not cases:
        raise ValueError(f"Manifesto operacional inválido: {path.name}")
    if not isinstance(cases, list) or len(
        {case.get("case_id") for case in cases}
    ) != len(cases):
        raise ValueError(f"Manifesto operacional com casos duplicados: {path.name}")
    listed = set()
    for case in cases:
        if not isinstance(case, dict) or not case.get("case_id"):
            raise ValueError(f"Caso operacional inválido: {path.name}")
        for field in ("input", "gold"):
            filename = case.get(field)
            if not isinstance(filename, str) or Path(filename).name != filename:
                raise ValueError(f"Arquivo operacional inválido: {filename}")
            if filename in listed:
                raise ValueError(f"Arquivo operacional duplicado: {filename}")
            listed.add(filename)
            target = path.parent / filename
            if not target.is_file():
                raise ValueError(f"Arquivo operacional ausente: {filename}")
            try:
                json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"JSON operacional inválido: {filename}") from exc
    actual = {item.name for item in path.parent.iterdir() if item.is_file()}
    if actual != listed | {path.name}:
        raise ValueError(f"Arquivos operacionais divergem do manifesto: {path.name}")


if __name__ == "__main__":
    validate_migrations()
    validate_synthetic_data()
