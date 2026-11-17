"""The destructive fixture commands must fail closed outside controlled test data."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import bootstrap_import_diagnostics_e2e as fixture  # noqa: E402


@pytest.mark.parametrize("environment", ["production", "homologation"])
def test_fixture_rejects_operational_environment(monkeypatch, environment):
    monkeypatch.setenv("SYNERGIA_ENV", environment)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/synergia_194_test")
    with pytest.raises(ValueError, match="explicit test database"):
        fixture.configuration()


@pytest.mark.parametrize(
    "database", ["synergia", "postgres", "synergia_194_test_other!"]
)
def test_fixture_rejects_non_test_database(monkeypatch, database):
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/" + database)
    with pytest.raises(ValueError, match="explicit test database"):
        fixture.configuration()


def test_fixture_rejects_non_disposable_storage(monkeypatch):
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/synergia_194_test")
    monkeypatch.setenv("IMPORT_STORAGE_DIR", "/var/lib/synergia-imports")
    with pytest.raises(ValueError, match="storage must be"):
        fixture.configuration()


@pytest.mark.parametrize(
    ("execution", "persisted"),
    [
        ("outside", False),
        ("ready", True),
        ("../missing", False),
    ],
)
def test_fixture_cannot_delete_other_artifact_or_summary(
    monkeypatch, tmp_path, execution, persisted
):
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/synergia_194_test")
    monkeypatch.setenv("IMPORT_STORAGE_DIR", str(tmp_path))
    artifact = tmp_path / "accepted/n_fp/e2e194-ready/pipeline-summary.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("synthetic sentinel")
    with pytest.raises(ValueError, match="controlled artifact-absence"):
        fixture.remove_artifact(execution, persisted=persisted)
    assert artifact.read_text() == "synthetic sentinel"
