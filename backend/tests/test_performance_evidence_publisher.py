from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from publish_performance_evidence import publish  # noqa: E402


def _spec(tmp_path: Path) -> Path:
    categories = (
        "manifest",
        "migration_comparison",
        "postgres_plan_after",
        "postgres_plan_before",
        "reference_run",
        "rupture_run",
    )
    entries = []
    for index, category in enumerate(categories):
        source = tmp_path / f"source-{index}.json"
        source.write_text(
            json.dumps(
                {
                    "category": category,
                    "workspace": str(tmp_path),
                    "password": "must-not-be-published",
                }
            ),
            encoding="utf-8",
        )
        entries.append(
            {
                "category": category,
                "source": source.name,
                "target": category,
            }
        )
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "published_at": "2026-09-17T00:00:00Z",
                "output": "published",
                "claims": {"status": "passed"},
                "scope": {"included": ["test evidence"]},
                "entries": entries,
            }
        ),
        encoding="utf-8",
    )
    return spec


def test_publisher_redacts_indexes_and_checksums(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    result = publish(_spec(tmp_path))

    assert result["summary"]["files"] == 6
    assert result["scope"] == {"included": ["test evidence"]}
    published = tmp_path / "published"
    payload = json.loads((published / "manifest/source-0.json").read_text())
    assert payload["workspace"] == "${WORKSPACE}"
    assert payload["password"] == "[REDACTED]"
    checksums = {
        line.split("  ", 1)[1]: line.split("  ", 1)[0]
        for line in (published / "SHA256SUMS").read_text().splitlines()
    }
    assert checksums["index.json"] == hashlib.sha256(
        (published / "index.json").read_bytes()
    ).hexdigest()


def test_publisher_rejects_secret_in_plain_text(monkeypatch, tmp_path: Path) -> None:
    spec_path = _spec(tmp_path)
    spec = json.loads(spec_path.read_text())
    secret = tmp_path / "secret.csv"
    secret.write_text("header\nAuthorization: Bearer abcdefghijklmnopqrstuvwxyz\n")
    spec["entries"][0]["source"] = secret.name
    spec_path.write_text(json.dumps(spec))
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="Possível segredo"):
        publish(spec_path)
