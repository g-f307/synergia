import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai_assistance_errors import assistance_error
from app.errors import install_error_handlers

pytestmark = pytest.mark.security


@pytest.mark.parametrize(
    "reason,status",
    [
        ("execution_active", 409),
        ("generation_in_progress", 409),
        ("invalid_contract", 422),
        ("disabled", 503),
        ("runtime_unavailable", 503),
        ("timeout", 504),
    ],
)
def test_assistance_http_failure_contract(reason, status):
    application = FastAPI()
    install_error_handlers(application)

    @application.get("/contract")
    def contract():
        raise assistance_error(reason)

    with TestClient(application) as client:
        response = client.get("/contract")
    assert response.status_code == status
    assert response.json()["error"]["code"] == f"ai_assistance_{reason}"
    assert response.json()["error"]["details"] == {}
