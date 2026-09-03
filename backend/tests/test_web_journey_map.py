from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import validate_web_journey_map  # noqa: E402


def test_web_journey_map_matches_openapi_access_and_prototype() -> None:
    document = validate_web_journey_map.validate()

    assert document["version"] == "1.0.0"
    assert document["prototype_ref"] == "prototype-v1.0"
    assert {route["id"] for route in document["routes"]} >= {
        "dashboard",
        "import-new",
        "execution-detail",
        "search",
        "pending-list",
    }


def _changed_map(tmp_path: Path, change) -> Path:
    document = json.loads(validate_web_journey_map.MAP.read_text(encoding="utf-8"))
    change(document)
    target = tmp_path / "web-route-map.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    return target


def test_web_journey_map_rejects_prototype_page_without_decision(
    tmp_path, monkeypatch
) -> None:
    target = _changed_map(
        tmp_path,
        lambda document: document["routes"][1].update(prototype_pages=[]),
    )
    monkeypatch.setattr(validate_web_journey_map, "MAP", target)

    with pytest.raises(ValueError, match="Páginas do protótipo sem decisão"):
        validate_web_journey_map.validate()


def test_web_journey_map_rejects_permission_different_from_matrix(
    tmp_path, monkeypatch
) -> None:
    target = _changed_map(
        tmp_path,
        lambda document: document["routes"][1]["endpoints"][0].update(
            permission="business.read"
        ),
    )
    monkeypatch.setattr(validate_web_journey_map, "MAP", target)

    with pytest.raises(ValueError, match="Permissão divergente"):
        validate_web_journey_map.validate()


def test_web_journey_map_rejects_scope_different_from_matrix(
    tmp_path, monkeypatch
) -> None:
    target = _changed_map(
        tmp_path,
        lambda document: document["routes"][1].update(scope="global"),
    )
    monkeypatch.setattr(validate_web_journey_map, "MAP", target)

    with pytest.raises(ValueError, match="Escopo divergente"):
        validate_web_journey_map.validate()


def test_web_journey_map_rejects_primary_permission_outside_contracts(
    tmp_path, monkeypatch
) -> None:
    target = _changed_map(
        tmp_path,
        lambda document: document["routes"][1].update(permission="business.read"),
    )
    monkeypatch.setattr(validate_web_journey_map, "MAP", target)

    with pytest.raises(ValueError, match="Permissão principal divergente"):
        validate_web_journey_map.validate()


def test_web_journey_map_rejects_unimplemented_angular_route(
    tmp_path, monkeypatch
) -> None:
    def mark_planned_route_as_implemented(document: dict) -> None:
        planned = next(
            route for route in document["routes"] if route["status"] == "planned"
        )
        planned["status"] = "implemented"

    target = _changed_map(
        tmp_path,
        mark_planned_route_as_implemented,
    )
    monkeypatch.setattr(validate_web_journey_map, "MAP", target)

    with pytest.raises(
        ValueError, match="Rotas marcadas como implementadas ausentes no Angular"
    ):
        validate_web_journey_map.validate()
