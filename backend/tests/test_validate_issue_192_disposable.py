"""Testes de segurança do runner descartável e reconciliação exata (#192)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))


def test_disposable_url_rejects_password_trick_and_production_env(monkeypatch):
    from validate_issue_192_disposable import validate_disposable_database_url

    # Password contains '192' and 'disposable', but db name is production 'synergia'
    with pytest.raises(ValueError, match="synergia_issue_192_"):
        validate_disposable_database_url(
            "postgresql://user:disposable192@prod.host:5432/synergia"
        )

    assert (
        validate_disposable_database_url(
            "postgresql://user:pw@127.0.0.1:15432/synergia_issue_192_test"
        )
        == "synergia_issue_192_test"
    )

    monkeypatch.setenv("SYNERGIA_ENV", "production")
    with pytest.raises(ValueError, match="não descartável"):
        validate_disposable_database_url(
            "postgresql://user:pw@127.0.0.1:15432/synergia_issue_192_test"
        )


def test_ensure_empty_disposable_database_refuses_existing_schema():
    from validate_issue_192_disposable import ensure_empty_disposable_database

    class FakeConn:
        def __init__(self, db_name: str, has_schema: bool):
            self.db_name = db_name
            self.has_schema = has_schema

        def execute(self, sql: str):
            value = self.db_name if "current_database" in sql else self.has_schema
            return type("Cur", (), {"fetchone": lambda _s: (value,)})()

    ensure_empty_disposable_database(
        FakeConn("synergia_issue_192_a", False), "synergia_issue_192_a"
    )
    with pytest.raises(ValueError, match="current_database"):
        ensure_empty_disposable_database(
            FakeConn("synergia", False), "synergia_issue_192_a"
        )
    with pytest.raises(ValueError, match="já possui schema"):
        ensure_empty_disposable_database(
            FakeConn("synergia_issue_192_a", True), "synergia_issue_192_a"
        )


def test_reconcile_correlation_sets_detects_missing_extra_and_duplicates():
    from validate_issue_192_disposable import reconcile_correlation_sets

    pg = [("ev-1", "ai.assistance.generated"), ("ev-2", "ai.assistance.read")]
    exact = reconcile_correlation_sets(
        pg,
        [
            {"event_id": "ev-1", "action": "ai.assistance.generated"},
            {"event_id": "ev-2", "action": "ai.assistance.read"},
        ],
    )
    assert exact["matched"] is True

    dup = reconcile_correlation_sets(
        pg,
        [
            {"event_id": "ev-1", "action": "ai.assistance.generated"},
            {"event_id": "ev-1", "action": "ai.assistance.generated"},
        ],
    )
    assert dup["matched"] is False
    assert dup["duplicates_in_graylog"] == [("ev-1", "ai.assistance.generated")]
    assert dup["missing_in_graylog"] == [("ev-2", "ai.assistance.read")]

    extra = reconcile_correlation_sets(
        pg,
        [
            {"event_id": "ev-1", "action": "ai.assistance.generated"},
            {"event_id": "ev-2", "action": "ai.assistance.read"},
            {"event_id": "ev-3", "action": "other"},
        ],
    )
    assert extra["matched"] is False
    assert extra["extra_in_graylog"] == [("ev-3", "other")]


def test_disposable_runner_uses_real_ledger_and_id_column():
    source = (ROOT / "scripts" / "validate_issue_192_disposable.py").read_text(
        encoding="utf-8"
    )
    assert "public.synergia_schema_migrations" in source
    assert "synergia.schema_migrations" not in source
    assert "DELETE FROM" not in source
    assert "SELECT id::text, action" in source
    assert "event_id::text" not in source
