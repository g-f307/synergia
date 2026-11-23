"""Synthetic #195 fixtures; requires an explicitly selected disposable test DB."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
from argon2 import PasswordHasher
from psycopg.conninfo import conninfo_to_dict

ORG_A = UUID("19500000-0000-4000-8000-000000000001")
ORG_B = UUID("19500000-0000-4000-8000-000000000002")
INSTANT = datetime(2026, 10, 1, 12, tzinfo=UTC)


def configuration() -> str:
    url = os.environ["DATABASE_URL"]
    database = conninfo_to_dict(url).get("dbname", "")
    if os.getenv("SYNERGIA_ENV") != "test" or not re.fullmatch(
        r"synergia_195_[a-z0-9_]+|synergia_ci|synergia_e2e", database
    ):
        raise ValueError("Synthetic #195 fixture requires an explicit test database")
    return url


def snapshot(
    connection,
    label,
    organization,
    number,
    day,
    *,
    partial=False,
    status="completed",
    updated_day=None,
):
    execution = "e2e195-" + label
    inserted = connection.execute(
        "INSERT INTO synergia.executions "
        "(id,organization_id,status,source,started_at) "
        "VALUES (%s,%s,%s,'OWM',%s) ON CONFLICT (id) DO NOTHING RETURNING id",
        (execution, organization, status, INSTANT + timedelta(days=day)),
    ).fetchone()
    if not inserted:
        return
    source = connection.execute(
        "INSERT INTO synergia.source_files "
        "(execution_id,file_name,content_hash,source) "
        "VALUES (%s,'synthetic.json',%s,'OWM') RETURNING id",
        (execution, uuid4().hex * 2),
    ).fetchone()[0]
    business = connection.execute(
        "INSERT INTO synergia.organizations "
        "(organization_code,execution_id,source_file_id) "
        "VALUES ('SAME-WORKBOOK-CODE',%s,%s) RETURNING id",
        (execution, source),
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO synergia.workorders "
        "(workorder_number,organization_id,execution_id,source_file_id,"
        "processing_status,updated_at,planned_quantity,produced_quantity,"
        "received_quantity,released_quantity,pending_quantity,retained_quantity) "
        "VALUES (%s,%s,%s,%s,'consolidated',%s,%s,%s,9,0,%s,%s)",
        (
            number,
            business,
            execution,
            source,
            INSTANT + timedelta(days=day if updated_day is None else updated_day),
            None if partial else 40,
            0 if partial else 20,
            None if partial else 9,
            None if partial else 1,
        ),
    )


def bootstrap():
    with psycopg.connect(configuration()) as connection:
        for organization, label in ((ORG_A, "A"), (ORG_B, "B")):
            connection.execute(
                "INSERT INTO synergia.iam_organizations "
                "(id,organization_code,display_name) VALUES (%s,%s,%s) "
                "ON CONFLICT (id) DO NOTHING",
                (organization, "syn195-" + label.lower(), "Synthetic 195 " + label),
            )
        password = PasswordHasher().hash(
            os.getenv("E2E_PASSWORD", "synthetic-e2e-password-63")
        )
        for index, (label, organizations, permission) in enumerate(
            (
                ("reader", [ORG_A], "business.read"),
                ("both", [ORG_A, ORG_B], "business.read"),
                ("denied", [ORG_A], "dashboard.read"),
            ),
            3,
        ):
            user = UUID(f"19500000-0000-4000-8000-{index:012d}")
            connection.execute(
                "INSERT INTO synergia.identity_users "
                "(id,status,display_name,local_password_hash,locale,timezone) "
                "VALUES (%s,'active',%s,%s,'pt-BR','America/Manaus') "
                "ON CONFLICT (id) DO NOTHING",
                (user, "Synthetic 195 " + label, password),
            )
            connection.execute(
                "INSERT INTO synergia.user_emails "
                "(user_id,email,is_primary,is_verified,verified_at) "
                "VALUES (%s,%s,true,true,now()) ON CONFLICT DO NOTHING",
                (user, f"workorders-{label}.e2e@example.invalid"),
            )
            for organization in organizations:
                connection.execute(
                    "INSERT INTO synergia.user_permission_assignments "
                    "(user_id,permission_id,organization_id) "
                    "SELECT %s,id,%s FROM synergia.permissions "
                    "WHERE normalized_key=%s ON CONFLICT DO NOTHING",
                    (user, organization, permission),
                )
        snapshot(connection, "a-old", ORG_A, "000123", 0)
        snapshot(connection, "a-tie-earlier", ORG_A, "000123", 1, updated_day=4)
        snapshot(
            connection,
            "a-tie-later",
            ORG_A,
            "000123",
            2,
            updated_day=4,
            partial=True,
            status="completed_with_errors",
        )
        snapshot(connection, "b-current", ORG_B, "000123", 3, updated_day=4)
        snapshot(connection, "a-unpublished", ORG_A, "000123", 5, status="failed")
        snapshot(connection, "unknown-iam", None, "000123", 5)
        for index in range(23):
            snapshot(
                connection, f"paged-{index:02d}", ORG_A, "000456", 0, updated_day=index
            )
    print("Synthetic #195 fixture ready: 3 A versions, 1 B, 2 excluded, 23 paged.")


if __name__ == "__main__":
    bootstrap()
