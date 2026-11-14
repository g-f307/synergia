from __future__ import annotations

import pytest

from app.ai_assistance_config import PREFIX, AiAssistanceConfig
from app.deployment_environment import validate_deployment_environment
from app.main import create_app

pytestmark = pytest.mark.security


def configured():
    return {
        PREFIX + key: value
        for key, value in {
            "ENABLED": "true",
            "ENDPOINT": "http://127.0.0.1:11434",
            "MODEL": "synthetic:1",
            "DIGEST": "sha256:" + "a" * 64,
        }.items()
    }


def test_default_disabled_without_runtime():
    config = AiAssistanceConfig.from_environment({})
    assert not config.enabled
    assert (
        config.timeout_seconds,
        config.context_max_bytes,
        config.response_max_bytes,
        config.max_concurrency,
        config.retention_days,
        config.follow_redirects,
    ) == (
        30,
        8192,
        8192,
        1,
        30,
        False,
    )


@pytest.mark.parametrize("key", ["ENDPOINT", "MODEL", "DIGEST"])
def test_enabled_requires_configuration(key):
    environment = configured()
    del environment[PREFIX + key]
    with pytest.raises(ValueError):
        AiAssistanceConfig.from_environment(environment)


@pytest.mark.parametrize(
    "key,value",
    [
        ("ENABLED", "yes"),
        ("ENABLED", "CHANGE_ME"),
        ("MODEL", "placeholder"),
        ("MODEL", "model name"),
        ("DIGEST", "latest"),
        ("DIGEST", ""),
        ("ENDPOINT", "https://127.0.0.1:11434"),
        ("ENDPOINT", "http://example.invalid:11434"),
        ("ENDPOINT", "http://user:password@127.0.0.1:11434"),
        ("ENDPOINT", "http://127.0.0.1:11434?x=1"),
        ("ENDPOINT", "http://127.0.0.1:11434?"),
        ("ENDPOINT", "http://127.0.0.1:11434#"),
        ("ENDPOINT", "http://127.0.0.1:11434/api/generate"),
        ("ENDPOINT", "http://127.0.0.1:0"),
        ("ENDPOINT", "http://127.0.0.1:abc"),
        ("ENDPOINT", "http://169.254.169.254"),
        ("ALLOWED_SERVICE", "*"),
        ("TIMEOUT_SECONDS", "31"),
        ("CONTEXT_MAX_BYTES", "8193"),
        ("RESPONSE_MAX_BYTES", "16384"),
        ("MAX_CONCURRENCY", "2"),
        ("FOLLOW_REDIRECTS", "true"),
        ("RETENTION_DAYS", "0"),
        ("RETENTION_DAYS", "366"),
        ("RETENTION_DAYS", "1.5"),
    ],
)
def test_unsafe_configuration_rejected_even_disabled(key, value):
    environment = configured()
    environment[PREFIX + "ENABLED"] = "false"
    environment[PREFIX + key] = value
    with pytest.raises(ValueError):
        AiAssistanceConfig.from_environment(environment)


@pytest.mark.parametrize(
    "endpoint",
    ["http://localhost:11434", "http://[::1]:11434", "http://127.0.0.2:11434"],
)
def test_loopback_allowed(endpoint):
    environment = configured()
    environment[PREFIX + "ENDPOINT"] = endpoint
    assert AiAssistanceConfig.from_environment(environment).endpoint == endpoint


def test_named_service_requires_explicit_allowlist():
    environment = configured()
    environment[PREFIX + "ENDPOINT"] = "http://ollama:11434"
    with pytest.raises(ValueError):
        AiAssistanceConfig.from_environment(environment)
    environment[PREFIX + "ALLOWED_SERVICE"] = "ollama"
    assert AiAssistanceConfig.from_environment(environment).enabled


@pytest.mark.parametrize(
    "deployment", ["development", "test", "homologation", "production"]
)
def test_invalid_config_fails_before_deployment_checks(deployment):
    with pytest.raises(ValueError, match="DIGEST"):
        validate_deployment_environment(
            {
                "SYNERGIA_ENV": deployment,
                PREFIX + "MODEL": "synthetic:1",
            }
        )


def test_direct_asgi_startup_fails_closed(monkeypatch):
    monkeypatch.setenv(PREFIX + "ENABLED", "true")
    monkeypatch.delenv(PREFIX + "DIGEST", raising=False)
    with pytest.raises(ValueError):
        create_app()
