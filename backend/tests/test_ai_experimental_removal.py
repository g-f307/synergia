"""Regressões da retirada da superfície experimental /ai/quality."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]


def test_openapi_and_routes_do_not_expose_ai_quality():
    from app.main import app

    paths = list(app.openapi()["paths"].keys())
    assert not any(path.startswith("/ai/quality") for path in paths)

    client = TestClient(app)
    assert client.get("/ai/quality/scenarios").status_code == 404
    assert (
        client.post("/ai/quality/scenarios/QE-A01/explanations", json={}).status_code
        == 404
    )


def test_operational_app_and_web_exclude_ai_quality_assets():
    assert not (ROOT / "backend/app/ai_quality.py").exists()
    assert not (ROOT / "backend/app/ai_quality_core.py").exists()
    assert not (ROOT / "backend/app/ai_quality_assets").exists()
    assert not (ROOT / "web/src/app/domains/ai-quality").exists()

    main_source = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    assert "ai_quality" not in main_source

    model_audit_source = (ROOT / "backend/app/model_audit.py").read_text(
        encoding="utf-8"
    )
    assert "ai_quality" not in model_audit_source

    feedback_sources = (ROOT / "backend/app/model/feedback_sources.json").read_text(
        encoding="utf-8"
    )
    assert "ai/quality" not in feedback_sources

    routes_source = (ROOT / "web/src/app/app.routes.ts").read_text(encoding="utf-8")
    assert "ai/quality" not in routes_source
    assert "ai-quality" not in routes_source

    app_component_source = (ROOT / "web/src/app/app.component.ts").read_text(
        encoding="utf-8"
    )
    assert "/ai/quality" not in app_component_source
    assert "quality.navigation" not in app_component_source


def test_dockerfiles_do_not_copy_experimental_quality_assets():
    for dockerfile in (
        ROOT / "backend/Dockerfile",
        ROOT / "web/Dockerfile",
    ):
        content = dockerfile.read_text(encoding="utf-8")
        assert "ai_quality" not in content
        assert "ai-quality" not in content
        assert "scenarios.json" not in content


def test_offline_evaluation_assets_are_preserved_under_scripts():
    assert (ROOT / "scripts/ai_quality_core.py").exists()
    assert (ROOT / "scripts/ai_quality_assets/scenarios.json").exists()
