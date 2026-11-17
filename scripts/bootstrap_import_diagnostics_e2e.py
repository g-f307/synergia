"""Controlled #194 browser fixtures; refuses operational databases and storage."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from io import BytesIO, StringIO
from pathlib import Path
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import psycopg
from argon2 import PasswordHasher
from openpyxl import Workbook
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
ORG_A = UUID("19400000-0000-4000-8000-000000000001")
ORG_B = UUID("19400000-0000-4000-8000-000000000002")
USERS = (
    ("reader", "import.read", ORG_A),
    ("outside", "import.read", ORG_B),
    ("creator", "import.create", ORG_A),
)
PREFIX = "e2e194-"
STATES = {
    "ready": "completed_with_errors",
    "missing": "completed",
    "preparation": "failed",
    "active": "validating",
    "zero": "completed",
    "success": "completed",
    "duplicate": "duplicate",
    "duplicate-b": "duplicate",
    "rejected": "failed",
    "outside": "completed",
}


def configuration() -> tuple[str, Path]:
    url = os.environ["DATABASE_URL"]
    database = conninfo_to_dict(url).get("dbname", "")
    if os.getenv("SYNERGIA_ENV", "test") != "test" or not re.fullmatch(
        r"synergia_194_[a-z0-9_]+|synergia_ci|synergia_e2e", database
    ):
        raise ValueError("Synthetic #194 runner requires an explicit test database")
    storage = Path(
        os.getenv("IMPORT_STORAGE_DIR", ROOT / ".test-tmp/e2e-imports")
    ).resolve()
    if not (
        storage.is_relative_to(ROOT / ".test-tmp") or storage.is_relative_to("/tmp")
    ):
        raise ValueError("Synthetic #194 storage must be under .test-tmp or /tmp")
    return url, storage


def synthetic_csv() -> bytes:
    stream = StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["workorder", "status"])
    for index in range(55):
        writer.writerow(
            [
                "" if index < 20 else f"WO-SYN194-{index}",
                f"reject-{index}" if index < 20 else "unmapped",
            ]
        )
    return stream.getvalue().encode()


def seed() -> None:
    url, storage = configuration()
    storage.mkdir(parents=True, exist_ok=True)
    content = synthetic_csv()
    with psycopg.connect(url) as connection:
        for organization, label in ((ORG_A, "a"), (ORG_B, "b")):
            connection.execute(
                "INSERT INTO synergia.iam_organizations "
                "(id,organization_code,display_name) VALUES (%s,%s,%s) "
                "ON CONFLICT (id) DO NOTHING",
                (organization, "syn194-" + label, "Synthetic Import " + label),
            )
        password_hash = PasswordHasher().hash(
            os.getenv("E2E_PASSWORD", "synthetic-e2e-password-63")
        )
        for number, (label, permission, organization) in enumerate(USERS, 3):
            user = UUID(f"19400000-0000-4000-8000-{number:012d}")
            connection.execute(
                "INSERT INTO synergia.identity_users "
                "(id,status,display_name,local_password_hash,locale,timezone) "
                "VALUES (%s,'active',%s,%s,'pt-BR','America/Manaus') "
                "ON CONFLICT (id) DO NOTHING",
                (user, "Synthetic Import " + label, password_hash),
            )
            connection.execute(
                "INSERT INTO synergia.user_emails "
                "(user_id,email,is_primary,is_verified,verified_at) "
                "VALUES (%s,%s,true,true,now()) ON CONFLICT DO NOTHING",
                (user, f"imports-{label}.e2e@example.invalid"),
            )
            for key in (permission, *(["import.read"] if label == "creator" else [])):
                connection.execute(
                    "INSERT INTO synergia.user_permission_assignments "
                    "(user_id,permission_id,organization_id) "
                    "SELECT %s,id,%s FROM synergia.permissions "
                    "WHERE normalized_key=%s ON CONFLICT DO NOTHING",
                    (user, organization, key),
                )
        for label, status in STATES.items():
            identifier = PREFIX + label
            reason = "preparation_error" if label == "preparation" else None
            inserted = connection.execute(
                "INSERT INTO synergia.executions "
                "(id,status,source,organization_id,actor_type,actor_identifier,"
                "failure_reason) VALUES "
                "(%s,%s,'N-FP',%s,'technical','synthetic-194',%s) "
                "ON CONFLICT (id) DO NOTHING RETURNING id",
                (identifier, status, ORG_B if label == "outside" else ORG_A, reason),
            ).fetchone()
            if not inserted:
                continue
            if label.startswith("duplicate"):
                # Linked after all roots exist (the foreign key is immediate).
                continue
            if label == "rejected":
                connection.execute(
                    "INSERT INTO synergia.file_inspections "
                    "(execution_id,source,original_file_name,internal_name,size_bytes,"
                    "content_hash,decision,reason_code,retained_until,analyzed_at) "
                    "VALUES (%s,'N-FP','synthetic.xlsx',%s,10,%s,'rejected',"
                    "'macro_or_active_content',now()+interval '1 hour',now())",
                    (identifier, uuid4().hex + uuid4().hex[:16], uuid4().hex * 2),
                )
                continue
            directory = storage / "accepted/n_fp" / identifier
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "synthetic.csv").write_bytes(content)
            file_id = connection.execute(
                "INSERT INTO synergia.source_files "
                "(execution_id,source,file_name,extension,content_hash,storage_key) "
                "VALUES (%s,'N-FP','synthetic.csv','csv',%s,%s) RETURNING id",
                (
                    identifier,
                    hashlib.sha256(content).hexdigest(),
                    str((directory / "synthetic.csv").relative_to(storage)),
                ),
            ).fetchone()[0]
            if label not in {"ready", "missing", "zero", "success", "outside"}:
                continue
            rows, valid, rejected, errors, warnings = (
                (55, 35, 20, 20, 35)
                if label == "ready"
                else (0, 0, 0, 0, 0)
                if label == "zero"
                else (1, 1, 0, 0, 0)
            )
            connection.execute(
                "INSERT INTO synergia.pipeline_summaries "
                "(execution_id,source_file_id,rows_read,valid_records,rejected_records,"
                "normalized_records,error_count,warning_count) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (identifier, file_id, rows, valid, rejected, valid, errors, warnings),
            )
            (directory / "pipeline-summary.json").write_text(
                json.dumps(
                    {
                        "rows_read": rows,
                        "valid_records": valid,
                        "rejected_records": rejected,
                        "normalized_records": valid,
                        "errors": errors,
                        "warnings": warnings,
                    }
                )
            )
            if label == "ready":
                for index in range(55):
                    error = index < 20
                    connection.execute(
                        "INSERT INTO synergia.pipeline_issues "
                        "(execution_id,source_file_id,scope,severity,code,sheet_name,"
                        "row_number,column_name,reason,details) "
                        "VALUES (%s,%s,'record',%s,%s,'CSV',%s,'A',%s,%s)",
                        (
                            identifier,
                            file_id,
                            "error" if error else "warning",
                            "required_field" if error else "unknown_state",
                            index + 2,
                            "synthetic-sensitive-cell",
                            Jsonb({"value": "synthetic-sensitive-cell"}),
                        ),
                    )
        for label, previous in (("duplicate", "ready"), ("duplicate-b", "outside")):
            connection.execute(
                "UPDATE synergia.executions SET duplicate_of_execution_id=%s "
                "WHERE id=%s AND duplicate_of_execution_id IS NULL",
                (PREFIX + previous, PREFIX + label),
            )
    # A harmless synthetic ZIP entry exercises the real upload security check.
    workbook = Workbook()
    workbook.active.append(["workorder", "status"])
    workbook.active.append(["WO-SYN194-MACRO", "open"])
    stream = BytesIO()
    workbook.save(stream)
    with (
        ZipFile(stream) as original,
        ZipFile(storage / "synthetic-macro.xlsx", "w", ZIP_DEFLATED) as target,
    ):
        for name in original.namelist():
            target.writestr(name, original.read(name))
        target.writestr("xl/vbaProject.bin", b"synthetic inert marker")
    print("Synthetic #194 fixtures ready; no credentials or file values emitted.")


def remove_artifact(label: str, *, persisted: bool) -> None:
    url, storage = configuration()
    if label not in {"ready", "missing"} or (persisted and label != "missing"):
        raise ValueError("Only the controlled artifact-absence fixtures may be changed")
    identifier = PREFIX + label
    (storage / "accepted/n_fp" / identifier / "pipeline-summary.json").unlink(
        missing_ok=True
    )
    if persisted:
        with psycopg.connect(url) as connection:
            connection.execute(
                "DELETE FROM synergia.pipeline_summaries WHERE execution_id=%s",
                (identifier,),
            )


def snapshot() -> dict:
    url, storage = configuration()
    contents = []
    with psycopg.connect(url) as connection:
        for table in (
            "executions",
            "execution_state_transitions",
            "source_files",
            "pipeline_issues",
            "pipeline_summaries",
            "file_inspections",
            "imported_records",
            "normalized_records",
            "audit_events",
        ):
            contents.append(
                connection.execute(
                    sql.SQL(
                        "SELECT to_jsonb(t) FROM synergia.{} t "
                        "ORDER BY to_jsonb(t)::text"
                    ).format(sql.Identifier(table))
                ).fetchall()
            )
    files = sorted(
        (str(path.relative_to(storage)), hashlib.sha256(path.read_bytes()).hexdigest())
        for path in storage.rglob("*")
        if path.is_file()
    )
    return {
        "business_sha256": hashlib.sha256(
            json.dumps(contents, sort_keys=True).encode()
        ).hexdigest(),
        "files_sha256": hashlib.sha256(json.dumps(files).encode()).hexdigest(),
        "file_count": len(files),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["seed", "remove-artifact", "snapshot"])
    parser.add_argument("--execution", choices=["ready", "missing"], default="ready")
    parser.add_argument("--persisted", action="store_true")
    args = parser.parse_args()
    if args.action == "seed":
        seed()
    elif args.action == "remove-artifact":
        remove_artifact(args.execution, persisted=args.persisted)
    else:
        print(json.dumps(snapshot(), sort_keys=True))
