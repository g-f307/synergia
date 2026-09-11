from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import validate_threat_model  # noqa: E402


def _changed_register(tmp_path: Path, change) -> Path:
    document = json.loads(
        validate_threat_model.REGISTER.read_text(encoding="utf-8")
    )
    change(document)
    target = tmp_path / "security-risk-register.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    return target


def test_threat_model_matches_openapi_access_matrix_and_evidence() -> None:
    document = validate_threat_model.validate()

    assert document["version"] == "1.0.0"
    assert len(document["journeys"]) == 7
    assert len(document["risks"]) >= 25


def test_threat_model_rejects_operation_with_wrong_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _changed_register(
        tmp_path,
        lambda document: document["journeys"][2]["operations"][0].update(
            scope="global"
        ),
    )
    monkeypatch.setattr(validate_threat_model, "REGISTER", target)

    with pytest.raises(ValueError, match="Contrato divergente"):
        validate_threat_model.validate()


def test_threat_model_rejects_risk_without_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _changed_register(
        tmp_path,
        lambda document: document["risks"][0].update(evidence=[]),
    )
    monkeypatch.setattr(validate_threat_model, "REGISTER", target)

    with pytest.raises(ValueError, match="sem evidence"):
        validate_threat_model.validate()


def test_threat_model_rejects_non_reproducible_inherent_severity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _changed_register(
        tmp_path,
        lambda document: document["risks"][0].update(inherent_severity="medium"),
    )
    monkeypatch.setattr(validate_threat_model, "REGISTER", target)

    with pytest.raises(ValueError, match="severidade inerente divergente"):
        validate_threat_model.validate()


def test_threat_model_rejects_transfer_without_reopen_condition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def remove_condition(document: dict) -> None:
        risk = next(
            item for item in document["risks"] if item["disposition"] == "transferred"
        )
        risk.pop("reopen_condition")

    target = _changed_register(tmp_path, remove_condition)
    monkeypatch.setattr(validate_threat_model, "REGISTER", target)

    with pytest.raises(ValueError, match="transferido sem etapa ou retomada"):
        validate_threat_model.validate()


def test_threat_model_rejects_stage_issue_without_related_risk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _changed_register(
        tmp_path,
        lambda document: [
            risk.update(treatment_issue=91)
            for risk in document["risks"]
            if risk["treatment_issue"] == 90
        ],
    )
    monkeypatch.setattr(validate_threat_model, "REGISTER", target)

    with pytest.raises(ValueError, match="Issues da Etapa 5 sem risco relacionado"):
        validate_threat_model.validate()
