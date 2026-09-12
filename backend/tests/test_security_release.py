from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import security_release  # noqa: E402, I001


pytestmark = pytest.mark.security


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("private-key", "-----BEGIN " + "PRIVATE KEY-----"),
        ("github-token", "ghp_" + "abcdefghijklmnopqrstuvwxyzABCDE12345"),
        ("aws-access-key", "AK" + "IAABCDEFGHIJKLMNOP"),
        ("jwt", "eyJabcdefghijk" + ".abcdefghijk.abcdefghijk"),
    ],
)
def test_secret_detectors_have_positive_fixtures(kind: str, value: str) -> None:
    assert security_release.SECRET_PATTERNS[kind].search(value)


def test_release_policy_blocks_synthetic_high_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = {
        "schema_version": 1,
        "blocking_severity": "high",
        "exceptions": [],
    }
    target = tmp_path / "policy.json"
    target.write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setattr(security_release, "POLICY", target)

    with pytest.raises(ValueError, match="SYNTHETIC-VULNERABLE-DEPENDENCY"):
        security_release.enforce_findings({
            "findings": [{
                "id": "SYNTHETIC-VULNERABLE-DEPENDENCY",
                "severity": "critical",
                "status": "open",
            }]
        })


def test_expired_exception_does_not_bypass_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = {
        "schema_version": 1,
        "blocking_severity": "high",
        "exceptions": [{
            "id": "CVE-SYNTHETIC",
            "owner": "security",
            "rationale": "fixture",
            "mitigation": "fixture",
            "expires_at": "2025-01-01T00:00:00Z",
        }],
    }
    target = tmp_path / "policy.json"
    target.write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setattr(security_release, "POLICY", target)

    with pytest.raises(ValueError, match="CVE-SYNTHETIC"):
        security_release.enforce_findings(
            {"findings": [{"id": "CVE-SYNTHETIC", "severity": "high"}]},
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_dast_rejects_non_disposable_target() -> None:
    with pytest.raises(ValueError, match="disposable loopback"):
        security_release.run_dast("https://production.example.com")


def test_authenticated_dast_does_not_persist_credentials_or_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = iter([
        (200, {
            "Content-Security-Policy": "default-src 'none'",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
        }, b"{}"),
        (404, {}, b'{"detail":"not found"}'),
        (404, {}, b'{"detail":"not found"}'),
        (404, {}, b'{"detail":"not found"}'),
        (404, {}, b'{"detail":"not found"}'),
        (401, {}, b'{"detail":"invalid credentials"}'),
        (200, {}, b'{"access_token":"synthetic-access-token"}'),
        (200, {}, b'{"display_name":"Synthetic"}'),
        (200, {}, b'{"items":[]}'),
        (200, {}, b'{"items":[]}'),
        (200, {}, b'{"items":[]}'),
        (200, {}, b'{"items":[]}'),
        (404, {}, b'{"detail":"not found"}'),
    ])
    monkeypatch.setattr(
        security_release,
        "_request",
        lambda *args, **kwargs: next(responses),
    )
    monkeypatch.setattr(security_release, "EVIDENCE", tmp_path)
    monkeypatch.setenv("DAST_EMAIL", "operator@example.invalid")
    monkeypatch.setenv("DAST_PASSWORD", "synthetic-password")

    document = security_release.run_dast("http://127.0.0.1:18000")
    persisted = (tmp_path / "dast-report.json").read_text(encoding="utf-8")

    assert not document["findings"]
    assert "synthetic-access-token" not in persisted
    assert "synthetic-password" not in persisted
    assert "operator@example.invalid" not in persisted


def test_sbom_contains_python_node_and_container_components(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(security_release, "EVIDENCE", tmp_path)
    document = security_release.generate_sbom()
    components = document["components"]

    assert document["bomFormat"] == "CycloneDX"
    assert any(item["purl"].startswith("pkg:pypi/") for item in components)
    assert any(item["purl"].startswith("pkg:npm/") for item in components)
    assert any(item["purl"].startswith("pkg:docker/") for item in components)
