"""Seed the synthetic #193 browser scenario in an explicitly selected test DB.

Run after apply_migrations.py/bootstrap_web_e2e.py. The two private organizations
and actor keep this fixture independent of the existing operational journey.
Repeated calls insert no duplicate executions and never delete audit history.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
from argon2 import PasswordHasher

ORGANIZATION_A = UUID("19300000-0000-4000-8000-000000000001")
ORGANIZATION_B = UUID("19300000-0000-4000-8000-000000000002")
USER = UUID("19300000-0000-4000-8000-000000000003")
INSTANT = datetime(2026, 11, 1, 12, tzinfo=UTC)


def bootstrap() -> None:
    password = os.getenv("E2E_PASSWORD", "synthetic-e2e-password-63")
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        for organization, label in ((ORGANIZATION_A, "A"), (ORGANIZATION_B, "B")):
            connection.execute(
                "INSERT INTO synergia.iam_organizations "
                "(id,organization_code,display_name) VALUES (%s,%s,%s) "
                "ON CONFLICT (id) DO NOTHING",
                (organization, f"syn193-{label.lower()}", f"Synthetic 193 {label}"),
            )
        connection.execute(
            "INSERT INTO synergia.identity_users "
            "(id,status,display_name,local_password_hash,locale,timezone) "
            "VALUES (%s,'active','Synthetic Reconciliation',%s,'pt-BR',"
            "'America/Manaus') ON CONFLICT (id) DO NOTHING",
            (USER, PasswordHasher().hash(password)),
        )
        connection.execute(
            "INSERT INTO synergia.user_emails "
            "(user_id,email,is_primary,is_verified,verified_at) "
            "VALUES (%s,'reconciliation.e2e@example.invalid',true,true,now()) "
            "ON CONFLICT (normalized_email) DO NOTHING",
            (USER,),
        )
        connection.execute(
            "INSERT INTO synergia.user_role_assignments "
            "(user_id,role_id,organization_id) "
            "SELECT %s,id,%s FROM synergia.roles WHERE normalized_key='consulta' "
            "ON CONFLICT DO NOTHING",
            (USER, ORGANIZATION_A),
        )
        states = ["completed"] * 3 + ["completed_with_errors"] * 2 + ["duplicate"] * 9
        states += [
            "pending",
            "validating",
            "normalizing",
            "consolidating",
            "applying_rules",
            "reprocessing",
            "failed",
            "validation_failed",
            "cancelled",
            *(["completed"] * 4),
            "completed_with_errors",
            "completed_with_errors",
            "duplicate",
        ]
        for tenant, organization in (("a", ORGANIZATION_A), ("b", ORGANIZATION_B)):
            for index, status in enumerate(
                states if tenant == "a" else ["completed"] * 30
            ):
                identifier = f"e2e193-{tenant}-{index:02d}"
                selected = index < 14 or tenant == "b"
                source = "OWM" if selected else "N-FP"
                extension = "csv" if selected else "json"
                instant = INSTANT if selected else INSTANT + timedelta(days=1)
                if tenant == "a" and index == 16:
                    source = None
                inserted = connection.execute(
                    "INSERT INTO synergia.executions "
                    "(id,organization_id,status,source,started_at) "
                    "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING RETURNING id",
                    (identifier, organization, status, source, instant),
                ).fetchone()
                if not inserted or source is None:
                    continue
                source_file = connection.execute(
                    "INSERT INTO synergia.source_files "
                    "(execution_id,file_name,content_hash,extension) "
                    "VALUES (%s,%s,%s,%s) RETURNING id",
                    (identifier, f"synthetic.{extension}", uuid4().hex * 2, extension),
                ).fetchone()[0]
                connection.execute(
                    "INSERT INTO synergia.pipeline_summaries "
                    "(execution_id,source_file_id,rows_read,valid_records,"
                    "rejected_records,normalized_records,error_count,warning_count) "
                    "VALUES (%s,%s,10,10,0,10,0,0)",
                    (identifier, source_file),
                )
        connection.execute(
            "INSERT INTO synergia.executions (id,status,source,started_at) "
            "VALUES ('e2e193-no-iam','completed','OWM',%s) "
            "ON CONFLICT (id) DO NOTHING",
            (INSTANT,),
        )
    print("Synthetic #193 scenario ready: 60 scoped executions + 1 excluded IAM row.")


if __name__ == "__main__":
    bootstrap()
