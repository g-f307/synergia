from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


def test_catalog_grants_only_explicit_business_roles():
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        rows = connection.execute(
            """SELECT r.normalized_key, p.normalized_key
            FROM synergia.role_permissions rp
            JOIN synergia.roles r ON r.id = rp.role_id
            JOIN synergia.permissions p ON p.id = rp.permission_id
            WHERE p.normalized_key LIKE 'ai.assistance.%'
              AND rp.revoked_at IS NULL AND p.is_active"""
        ).fetchall()
        assert set(rows) == {
            (role, permission)
            for role in ("gestor", "analista")
            for permission in ("ai.assistance.read", "ai.assistance.generate")
        }
        assert connection.execute(
            """SELECT version FROM synergia.permission_catalog_versions
            WHERE is_active"""
        ).fetchall() == [("1.6.0",)]


def test_rollback_preserves_history_and_disables_permissions():
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(
            (
                ROOT
                / "database/rollbacks"
                / "0037_create_ai_assistance_permissions.down.sql"
            ).read_text(),
            prepare=False,
        )
        assert connection.execute(
            """SELECT count(*) FROM synergia.permissions
            WHERE normalized_key LIKE 'ai.assistance.%' AND NOT is_active"""
        ).fetchone() == (2,)
        assert connection.execute(
            """SELECT count(*) FROM synergia.role_permissions rp
            JOIN synergia.permissions p ON p.id = rp.permission_id
            WHERE p.normalized_key LIKE 'ai.assistance.%'
              AND rp.revoked_at IS NULL"""
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT version FROM synergia.permission_catalog_versions WHERE is_active"
        ).fetchall() == [("1.5.0",)]
        connection.rollback()
