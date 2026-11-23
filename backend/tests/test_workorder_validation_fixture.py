"""Fail closed before a synthetic browser/performance fixture can mutate data."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import bootstrap_workorder_versions_e2e as fixture  # noqa: E402


@pytest.mark.parametrize(
    "environment", ["production", "homologation", "development", ""]
)
def test_workorder_fixture_rejects_non_test_environment(monkeypatch, environment):
    monkeypatch.setenv("SYNERGIA_ENV", environment)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/synergia_195_test")
    with pytest.raises(ValueError, match="explicit test database"):
        fixture.configuration()


@pytest.mark.parametrize("database", ["synergia", "postgres", "synergia_195_test!"])
def test_workorder_fixture_rejects_non_test_database(monkeypatch, database):
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/" + database)
    with pytest.raises(ValueError, match="explicit test database"):
        fixture.configuration()
