from app.main import health


def test_health_returns_service_status() -> None:
    assert health() == {"status": "ok", "service": "synergia-api"}
