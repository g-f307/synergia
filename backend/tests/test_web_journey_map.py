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

    assert document["version"] == "1.2.0"
    assert document["prototype_ref"] == "prototype-v1.0"
    assert {route["id"] for route in document["routes"]} >= {
        "dashboard",
        "import-new",
        "execution-detail",
        "search",
        "pending-list",
    }
    admin = next(route for route in document["routes"] if route["id"] == "admin")
    assert admin.get("exposure", "full") == "full"
    assert "gap" not in admin
    assert admin["issue"] == 106
    assert document["supporting_operations"]
    assert document["planned_capabilities"]


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
    def add_an_implemented_route_missing_from_angular(document: dict) -> None:
        implemented = next(
            route for route in document["routes"] if route["status"] == "implemented"
        )
        document["routes"].append(
            {
                **implemented,
                "id": "route-not-present-in-angular",
                "route": "/route-not-present-in-angular",
                "prototype_pages": [],
            }
        )

    target = _changed_map(
        tmp_path,
        add_an_implemented_route_missing_from_angular,
    )
    monkeypatch.setattr(validate_web_journey_map, "MAP", target)

    with pytest.raises(
        ValueError, match="Rotas marcadas como implementadas ausentes no Angular"
    ):
        validate_web_journey_map.validate()


def test_web_journey_map_rejects_openapi_operation_without_decision(
    tmp_path, monkeypatch
) -> None:
    def remove_decision(document: dict) -> None:
        document["supporting_operations"] = [
            item
            for item in document["supporting_operations"]
            if item["path"] != "/history"
        ]

    target = _changed_map(tmp_path, remove_decision)
    monkeypatch.setattr(validate_web_journey_map, "MAP", target)

    with pytest.raises(ValueError, match="Inventário OpenAPI divergente"):
        validate_web_journey_map.validate()


def test_web_journey_map_rejects_partial_route_without_gap(
    tmp_path, monkeypatch
) -> None:
    def remove_gap(document: dict) -> None:
        reports = next(
            route for route in document["routes"] if route["id"] == "reports"
        )
        reports.pop("gap")

    target = _changed_map(tmp_path, remove_gap)
    monkeypatch.setattr(validate_web_journey_map, "MAP", target)

    with pytest.raises(ValueError, match="Rota parcial sem lacuna explícita"):
        validate_web_journey_map.validate()


def test_web_journey_map_rejects_full_route_with_gap(
    tmp_path, monkeypatch
) -> None:
    def add_gap_to_admin(document: dict) -> None:
        admin = next(route for route in document["routes"] if route["id"] == "admin")
        admin["gap"] = "lacuna incompatível com uma rota completa"

    target = _changed_map(tmp_path, add_gap_to_admin)
    monkeypatch.setattr(validate_web_journey_map, "MAP", target)

    with pytest.raises(ValueError, match="Rota full não pode possuir lacuna"):
        validate_web_journey_map.validate()


def test_web_journey_map_rejects_full_route_with_partial_domain_operations(
    tmp_path, monkeypatch
) -> None:
    def hide_reports_gap_and_mark_full(document: dict) -> None:
        reports = next(
            route for route in document["routes"] if route["id"] == "reports"
        )
        reports["exposure"] = "full"
        reports.pop("gap")

    target = _changed_map(tmp_path, hide_reports_gap_and_mark_full)
    monkeypatch.setattr(validate_web_journey_map, "MAP", target)

    with pytest.raises(
        ValueError,
        match="Rota full possui operações parciais no mesmo consumidor",
    ):
        validate_web_journey_map.validate()


def test_web_journey_map_rejects_full_operation_with_invalid_consumer(
    tmp_path, monkeypatch
) -> None:
    def use_unknown_consumer(document: dict) -> None:
        operation = next(
            item
            for item in document["supporting_operations"]
            if item["path"] == "/auth/logout"
        )
        operation["consumer"] = "missing-angular-consumer"

    target = _changed_map(tmp_path, use_unknown_consumer)
    monkeypatch.setattr(validate_web_journey_map, "MAP", target)

    with pytest.raises(ValueError, match="Consumidor inválido"):
        validate_web_journey_map.validate()


def test_web_journey_map_rejects_full_operation_without_angular_consumption(
    tmp_path, monkeypatch
) -> None:
    def point_to_unrelated_source(document: dict) -> None:
        operation = next(
            item
            for item in document["supporting_operations"]
            if item["path"] == "/auth/logout"
        )
        operation["evidence"] = ["web/src/app/features/admin.component.ts"]

    target = _changed_map(tmp_path, point_to_unrelated_source)
    monkeypatch.setattr(validate_web_journey_map, "MAP", target)

    with pytest.raises(ValueError, match="sem consumo Angular comprovado"):
        validate_web_journey_map.validate()


def test_web_journey_map_rejects_deferred_operation_without_target(
    tmp_path, monkeypatch
) -> None:
    def remove_target(document: dict) -> None:
        operation = next(
            item
            for item in document["supporting_operations"]
            if item["path"] == "/history"
        )
        operation.pop("target")

    target = _changed_map(tmp_path, remove_target)
    monkeypatch.setattr(validate_web_journey_map, "MAP", target)

    with pytest.raises(ValueError, match="deferred sem decisão e destino"):
        validate_web_journey_map.validate()


def test_web_journey_map_rejects_technical_operation_without_rationale(
    tmp_path, monkeypatch
) -> None:
    def remove_rationale(document: dict) -> None:
        operation = next(
            item
            for item in document["supporting_operations"]
            if item["path"] == "/metrics"
        )
        operation.pop("decision")

    target = _changed_map(tmp_path, remove_rationale)
    monkeypatch.setattr(validate_web_journey_map, "MAP", target)

    with pytest.raises(ValueError, match="Operação técnica sem justificativa"):
        validate_web_journey_map.validate()
