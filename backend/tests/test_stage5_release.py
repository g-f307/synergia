from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import validate_stage5_release  # noqa: E402


def _changed_decision(tmp_path: Path, change) -> Path:
    document = json.loads(validate_stage5_release.DECISION.read_text(encoding="utf-8"))
    change(document)
    target = tmp_path / "stage-5-release-decision.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    return target


def test_stage5_decision_is_complete_and_does_not_claim_corporate_approval() -> None:
    decision = validate_stage5_release.validate()

    assert decision["decisions"] == {
        "pre_rpa_homologation": "technically_ready",
        "release_candidate": "not_approved",
        "stage_6_entry": "not_authorized",
    }
    assert all(gate["status"] == "passed" for gate in decision["technical_gates"])
    assert all(gate["status"] == "pending" for gate in decision["corporate_gates"])


def test_stage6_requires_both_formal_signoffs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _changed_decision(
        tmp_path,
        lambda document: document["decisions"].update(stage_6_entry="authorized"),
    )
    monkeypatch.setattr(validate_stage5_release, "DECISION", target)

    with pytest.raises(ValueError, match="without both sign-offs"):
        validate_stage5_release.validate()


def test_high_corporate_risk_cannot_disappear_from_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def remove_identity_risk(document: dict) -> None:
        for gate in document["corporate_gates"]:
            if gate["id"] == "corporate-identity":
                gate["related_risks"] = ["R-24"]

    target = _changed_decision(tmp_path, remove_identity_risk)
    monkeypatch.setattr(validate_stage5_release, "DECISION", target)

    with pytest.raises(ValueError, match="R-03"):
        validate_stage5_release.validate()


def test_technical_gate_requires_reproducible_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _changed_decision(
        tmp_path,
        lambda document: document["technical_gates"][0].update(
            evidence=["reports/private/nonexistent-secret.log"]
        ),
    )
    monkeypatch.setattr(validate_stage5_release, "DECISION", target)

    with pytest.raises(ValueError, match="missing evidence"):
        validate_stage5_release.validate()


def test_signoffs_must_be_mapping_objects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _changed_decision(
        tmp_path,
        lambda document: document.update(signoffs={"product_owner": "approved"}),
    )
    monkeypatch.setattr(validate_stage5_release, "DECISION", target)

    with pytest.raises(ValueError, match="invalid sign-off structure"):
        validate_stage5_release.validate()
