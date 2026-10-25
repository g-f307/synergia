from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import validate_identity_contract as contract  # noqa: E402


def _changed(tmp_path: Path, change) -> Path:
    document = json.loads(contract.REGISTER.read_text(encoding="utf-8"))
    change(document)
    target = tmp_path / "corporate-identity-decisions.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    return target


def _decision(document: dict, identifier: str) -> dict:
    return next(item for item in document["decisions"] if item["id"] == identifier)


def test_register_covers_every_required_decision_with_owner_and_state() -> None:
    document = contract.validate()

    assert {item["id"] for item in document["decisions"]} >= contract.REQUIRED_IDS
    assert all(item["owner"] and item["state"] for item in document["decisions"])
    states = {item["state"] for item in document["decisions"]}
    assert states <= contract.STATES


def test_external_decisions_stay_pending_until_the_client_answers() -> None:
    document = contract.validate()
    gates = {f"ID-P0{n}" for n in range(1, 8)}

    external = [item for item in document["decisions"] if item["id"] in gates]

    assert {item["state"] for item in external} == {"pending_external"}
    assert all("LG" in item["owner"] for item in external)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: _decision(d, "ID-P01").update(owner=""), "responsável"),
        (lambda d: _decision(d, "ID-P01").update(owner="Alguém"), "responsável"),
        (lambda d: _decision(d, "ID-P02").update(state="aprovado"), "estado"),
        (lambda d: _decision(d, "ID-P03").pop("state"), "estado"),
        (lambda d: _decision(d, "ID-P04").update(interim_behavior=" "), "interim"),
        (lambda d: _decision(d, "ID-P05").update(evidence=[]), "evidência"),
        (
            lambda d: _decision(d, "ID-P06").update(evidence=["docs/nao-existe.md"]),
            "Evidência inexistente",
        ),
        (
            lambda d: _decision(d, "ID-P07").update(evidence=["/etc/passwd"]),
            "Evidência inexistente",
        ),
        (lambda d: d["decisions"].pop(), "ausentes"),
        (lambda d: d["decisions"].append(dict(d["decisions"][0])), "duplicadas"),
        (lambda d: d["states"].pop("proposed"), "estados"),
    ],
)
def test_register_rejects_incomplete_decisions(tmp_path, change, message) -> None:
    target = _changed(tmp_path, change)

    with pytest.raises(ValueError, match=message):
        contract.validate(target)


@pytest.mark.parametrize(
    "text",
    [
        "client_secret: abcdef123456",
        "password = hunter2hunter2",
        "senha: umaSenhaReal1",
        "Authorization: Bearer abcdefghijklmnop1234",
        "-----BEGIN PRIVATE KEY-----",
        "token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.signature",
    ],
)
def test_secret_scanner_flags_credential_shaped_text(text) -> None:
    assert any(pattern.search(text) for pattern in contract.SECRET_PATTERNS)


@pytest.mark.parametrize(
    "text",
    [
        "AUTH_CORPORATE_CLIENT_SECRET_FILE=/run/secrets/idp-client",
        "o segredo é lido de arquivo montado",
        "AUTH_CORPORATE_CLIENT_ID=synergia-synthetic-client",
        "senha ausente ou ilegível",
    ],
)
def test_secret_scanner_ignores_references_to_secrets(text) -> None:
    assert not any(pattern.search(text) for pattern in contract.SECRET_PATTERNS)


def test_documents_cite_the_gates_they_depend_on() -> None:
    for relative, required in contract.DOCUMENTS.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert all(identifier in text for identifier in required), relative
