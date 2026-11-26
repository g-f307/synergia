"""Synthetic #196 browser fixture; never accepts an operational database."""

from __future__ import annotations

import argparse
import os
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
from argon2 import PasswordHasher
from psycopg.conninfo import conninfo_to_dict

ORG_A = UUID("19600000-0000-4000-8000-000000000001")
ORG_B = UUID("19600000-0000-4000-8000-000000000002")
INSTANT = datetime(2026, 10, 1, 12, tzinfo=UTC)


def configuration() -> str:
    url = os.environ["DATABASE_URL"]
    name = conninfo_to_dict(url).get("dbname", "")
    if os.getenv("SYNERGIA_ENV") != "test" or not re.fullmatch(
        r"synergia_196_[a-z0-9_]+|synergia_ci|synergia_e2e", name
    ):
        raise ValueError("Synthetic #196 fixture requires an explicit test database")
    return url


def snapshot(
    connection, label, organization, number, day, quantities, status="completed"
):
    execution = "e2e196-" + label
    inserted = connection.execute(
        "INSERT INTO synergia.executions "
        "(id,organization_id,status,source,started_at) VALUES (%s,%s,%s,'OWM',%s) "
        "ON CONFLICT DO NOTHING RETURNING id",
        (execution, organization, status, INSTANT + timedelta(days=day)),
    ).fetchone()
    if not inserted:
        return
    source = connection.execute(
        "INSERT INTO synergia.source_files "
        "(execution_id,file_name,content_hash,source,extension) "
        "VALUES (%s,'synthetic.json',%s,'OWM','json') RETURNING id",
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
        "received_quantity,released_quantity,partially_released) "
        "VALUES (%s,%s,%s,%s,'consolidated',%s,%s,%s,%s,%s,false)",
        (
            number,
            business,
            execution,
            source,
            INSTANT + timedelta(days=day),
            *quantities,
        ),
    )


def bootstrap():
    with psycopg.connect(configuration()) as connection:
        for organization, label in ((ORG_A, "A"), (ORG_B, "B")):
            connection.execute(
                "INSERT INTO synergia.iam_organizations "
                "(id,organization_code,display_name) VALUES (%s,%s,%s) "
                "ON CONFLICT DO NOTHING",
                (organization, "syn196-" + label.lower(), "Synthetic 196 " + label),
            )
        password = PasswordHasher().hash(
            os.getenv("E2E_PASSWORD", "synthetic-e2e-password-63")
        )
        for index, (label, dashboard, business) in enumerate(
            (
                ("reader", [ORG_A], [ORG_A]),
                ("both", [ORG_A, ORG_B], [ORG_A, ORG_B]),
                ("restricted", [ORG_A, ORG_B], [ORG_A]),
                ("denied", [ORG_A], []),
            ),
            3,
        ):
            user = UUID(f"19600000-0000-4000-8000-{index:012d}")
            connection.execute(
                "INSERT INTO synergia.identity_users "
                "(id,status,display_name,local_password_hash,locale,timezone) "
                "VALUES (%s,'active',%s,%s,'pt-BR','America/Manaus') "
                "ON CONFLICT DO NOTHING",
                (user, "Synthetic 196 " + label, password),
            )
            connection.execute(
                "INSERT INTO synergia.user_emails "
                "(user_id,email,is_primary,is_verified,verified_at) "
                "VALUES (%s,%s,true,true,now()) ON CONFLICT DO NOTHING",
                (user, f"coverage-{label}.e2e@example.invalid"),
            )
            connection.execute(
                "INSERT INTO synergia.user_permission_assignments "
                "(user_id,permission_id,organization_id) "
                "SELECT %s,id,NULL FROM synergia.permissions "
                "WHERE normalized_key='session.revoke.own' ON CONFLICT DO NOTHING",
                (user,),
            )
            for permission, scopes in (
                ("dashboard.read", dashboard),
                ("business.read", business),
            ):
                for organization in scopes:
                    connection.execute(
                        "INSERT INTO synergia.user_permission_assignments "
                        "(user_id,permission_id,organization_id) "
                        "SELECT %s,id,%s FROM synergia.permissions "
                        "WHERE normalized_key=%s ON CONFLICT DO NOTHING",
                        (user, organization, permission),
                    )
        snapshot(connection, "a-old", ORG_A, "WO-001", 0, (400, 500, 600, 400))
        for index, value in enumerate((4, None, 0), 1):
            snapshot(
                connection,
                f"a-{index}",
                ORG_A,
                f"WO-{index:03d}",
                1,
                (value, 0, None, 0 if index != 2 else None),
            )
        snapshot(connection, "b-current", ORG_B, "WO-001", 1, (999, 999, 999, 999))
        snapshot(connection, "a-unpublished", ORG_A, "WO-001", 3, (9999,) * 4, "failed")
        snapshot(connection, "unknown-iam", None, "WO-001", 3, (9999,) * 4)
    print(
        "Synthetic #196 fixture ready: 4/null/0, old version, A/B and excluded records."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--append-version", action="store_true")
    args = parser.parse_args()
    if args.append_version:
        with psycopg.connect(configuration()) as connection:
            snapshot(connection, "a-new", ORG_A, "WO-001", 2, (7, 0, None, 0))
        print("Synthetic new version appended; no old snapshot was modified.")
    else:
        bootstrap()
