import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from psycopg.conninfo import conninfo_to_dict

from app.container_runtime import (
    build_database_conninfo,
    validate_deployment_environment,
)

ROOT = Path(__file__).resolve().parents[2]


def test_builds_safe_conninfo_for_reserved_password_characters() -> None:
    password = "synthetic-p@ss:word/with#chars\\and space"
    environment = {
        "PGHOST": "postgres",
        "PGPORT": "5432",
        "PGDATABASE": "synergia",
        "PGUSER": "synergia",
        "PGPASSWORD": password,
    }

    parsed = conninfo_to_dict(build_database_conninfo(environment))
    assert parsed == {
        "user": "synergia",
        "password": password,
        "dbname": "synergia",
        "host": "postgres",
        "port": "5432",
    }


def _deployment_environment(environment: str) -> dict[str, str]:
    return {
        "SYNERGIA_ENV": environment,
        "PGPASSWORD": "synthetic-postgres-password",
        "AUTH_JWT_SIGNING_KEY": "synthetic-signing-key-with-at-least-32-bytes",
        "RATE_LIMIT_KEY_SECRET": "synthetic-rate-limit-key-with-at-least-32-bytes",
        "AUTH_ALLOWED_ORIGINS": "http://synergia.internal.example",
        "SYNERGIA_API_ORIGIN": "http://synergia-api.internal.example",
        "AUTH_REFRESH_COOKIE_SECURE": "false",
        "SYNERGIA_LOCAL_AUTH_ENABLED": "false",
        "AUTH_IDENTITY_PROVIDER": "local",
    }


@pytest.mark.parametrize("value", [None, "", "staging"])
def test_deployment_environment_must_be_explicit_and_known(value) -> None:
    environment = _deployment_environment("development")
    if value is None:
        environment.pop("SYNERGIA_ENV")
    else:
        environment["SYNERGIA_ENV"] = value

    with pytest.raises(ValueError, match="SYNERGIA_ENV"):
        validate_deployment_environment(environment)


def test_development_accepts_local_defaults() -> None:
    environment = {
        "SYNERGIA_ENV": "development",
        "PGPASSWORD": "synergia-local-only",
        "AUTH_JWT_SIGNING_KEY": "synergia-local-signing-key-change-me-119",
        "RATE_LIMIT_KEY_SECRET": "synergia-local-rate-limit-key-change-me",
        "AUTH_ALLOWED_ORIGINS": "http://localhost:8080",
        "SYNERGIA_API_ORIGIN": "http://localhost:8000",
    }

    assert validate_deployment_environment(environment) == "development"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PGPASSWORD", "synergia-local-only"),
        ("AUTH_JWT_SIGNING_KEY", "synergia-local-signing-key-change-me-119"),
        ("RATE_LIMIT_KEY_SECRET", "synergia-local-rate-limit-key-change-me"),
        ("AUTH_ALLOWED_ORIGINS", "http://localhost:8080"),
        ("SYNERGIA_API_ORIGIN", "http://localhost:8000"),
    ],
)
def test_homologation_rejects_local_defaults(name: str, value: str) -> None:
    environment = _deployment_environment("homologation")
    environment[name] = value

    with pytest.raises(ValueError, match=name):
        validate_deployment_environment(environment)


@pytest.mark.parametrize(
    "name",
    ["PGPASSWORD", "AUTH_JWT_SIGNING_KEY", "RATE_LIMIT_KEY_SECRET"],
)
def test_homologation_rejects_unedited_placeholders(name: str) -> None:
    environment = _deployment_environment("homologation")
    environment[name] = "CHANGE_ME"

    with pytest.raises(ValueError, match=name):
        validate_deployment_environment(environment)


@pytest.mark.parametrize("name", ["AUTH_JWT_SIGNING_KEY", "RATE_LIMIT_KEY_SECRET"])
def test_homologation_rejects_short_signing_secrets(name: str) -> None:
    environment = _deployment_environment("homologation")
    environment[name] = "too-short"

    with pytest.raises(ValueError, match=name):
        validate_deployment_environment(environment)


def test_homologation_local_login_requires_a_valid_expiry() -> None:
    environment = _deployment_environment("homologation")
    environment["SYNERGIA_LOCAL_AUTH_ENABLED"] = "true"

    with pytest.raises(ValueError, match="AUTH_LOCAL_LOGIN_EXPIRES_AT"):
        validate_deployment_environment(environment)

    environment["AUTH_LOCAL_LOGIN_EXPIRES_AT"] = (
        datetime.now(UTC) + timedelta(days=30)
    ).isoformat()
    assert validate_deployment_environment(environment) == "homologation"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SYNERGIA_API_ORIGIN", "http://CHANGE_ME_API_HOST:8000"),
        ("AUTH_ALLOWED_ORIGINS", "http://web.internal.example/login"),
        ("SYNERGIA_API_ORIGIN", "http://api.internal.example:not-a-port"),
    ],
)
def test_homologation_rejects_malformed_origins(name: str, value: str) -> None:
    environment = _deployment_environment("homologation")
    environment[name] = value

    with pytest.raises(ValueError, match=name):
        validate_deployment_environment(environment)


@pytest.mark.parametrize(
    "origin",
    [
        "https://*.company.example",
        "https://bad_host.company.example",
    ],
)
def test_homologation_rejects_wildcard_or_malformed_origin_hosts(
    origin: str,
) -> None:
    environment = _deployment_environment("homologation")
    environment["AUTH_ALLOWED_ORIGINS"] = origin

    with pytest.raises(ValueError, match="AUTH_ALLOWED_ORIGINS"):
        validate_deployment_environment(environment)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AUTH_JWT_ALGORITHM", "HS512"),
        ("AUTH_IDENTITY_PROVIDER", "fake"),
    ],
)
def test_homologation_rejects_authentication_settings_the_app_rejects(
    name: str, value: str
) -> None:
    environment = _deployment_environment("homologation")
    environment[name] = value

    with pytest.raises(ValueError, match=name):
        validate_deployment_environment(environment)


def test_production_requires_secure_cookie_and_corporate_identity() -> None:
    environment = _deployment_environment("production")

    with pytest.raises(ValueError, match="AUTH_REFRESH_COOKIE_SECURE"):
        validate_deployment_environment(environment)

    environment["AUTH_REFRESH_COOKIE_SECURE"] = "true"
    with pytest.raises(ValueError, match="AUTH_IDENTITY_PROVIDER"):
        validate_deployment_environment(environment)

    environment["AUTH_IDENTITY_PROVIDER"] = "corporate"
    with pytest.raises(ValueError, match="AUTH_CORPORATE_ISSUER"):
        validate_deployment_environment(environment)

    environment.update(
        {
            "AUTH_ALLOWED_ORIGINS": "https://synergia.internal.example",
            "SYNERGIA_API_ORIGIN": "https://synergia-api.internal.example",
            "AUTH_CORPORATE_ISSUER": "https://identity.internal.example",
            "AUTH_CORPORATE_DISCOVERY_URL": (
                "https://identity.internal.example/.well-known/openid-configuration"
            ),
            "AUTH_CORPORATE_AUDIENCE": "synergia-api",
            "AUTH_CORPORATE_CLIENT_ID": "synergia",
            "AUTH_CORPORATE_CLIENT_SECRET_FILE": "/run/secrets/identity-client",
            "AUTH_CORPORATE_MAPPING_FILE": "/run/secrets/identity-mapping.json",
        }
    )
    assert validate_deployment_environment(environment) == "production"


def test_production_requires_https_public_origins() -> None:
    environment = _deployment_environment("production")
    environment.update(
        {
            "AUTH_REFRESH_COOKIE_SECURE": "true",
            "AUTH_IDENTITY_PROVIDER": "corporate",
            "AUTH_CORPORATE_ISSUER": "https://identity.internal.example",
            "AUTH_CORPORATE_DISCOVERY_URL": (
                "https://identity.internal.example/.well-known/openid-configuration"
            ),
            "AUTH_CORPORATE_AUDIENCE": "synergia-api",
            "AUTH_CORPORATE_CLIENT_ID": "synergia",
            "AUTH_CORPORATE_CLIENT_SECRET_FILE": "/run/secrets/identity-client",
            "AUTH_CORPORATE_MAPPING_FILE": "/run/secrets/identity-mapping.json",
        }
    )

    with pytest.raises(ValueError, match="AUTH_ALLOWED_ORIGINS.*HTTPS"):
        validate_deployment_environment(environment)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AUTH_CORPORATE_REQUIRE_MFA", "false"),
        (
            "AUTH_CORPORATE_DISCOVERY_URL",
            "https://other-identity.internal.example/.well-known/openid-configuration",
        ),
    ],
)
def test_production_rejects_incompatible_corporate_identity_settings(
    name: str, value: str
) -> None:
    environment = _deployment_environment("production")
    environment.update(
        {
            "AUTH_ALLOWED_ORIGINS": "https://web.internal.example",
            "SYNERGIA_API_ORIGIN": "https://api.internal.example",
            "AUTH_REFRESH_COOKIE_SECURE": "true",
            "AUTH_IDENTITY_PROVIDER": "corporate",
            "AUTH_CORPORATE_ISSUER": "https://identity.internal.example",
            "AUTH_CORPORATE_DISCOVERY_URL": (
                "https://identity.internal.example/.well-known/openid-configuration"
            ),
            "AUTH_CORPORATE_AUDIENCE": "synergia-api",
            "AUTH_CORPORATE_CLIENT_ID": "synergia",
            "AUTH_CORPORATE_CLIENT_SECRET_FILE": "/run/secrets/identity-client",
            "AUTH_CORPORATE_MAPPING_FILE": "/run/secrets/identity-mapping.json",
            "AUTH_CORPORATE_REQUIRE_MFA": "true",
        }
    )
    environment[name] = value

    with pytest.raises(ValueError, match=name):
        validate_deployment_environment(environment)


def test_container_entrypoint_reports_the_selected_environment() -> None:
    environment = _deployment_environment("development") | {
        "PGHOST": "postgres",
        "PGPORT": "5432",
        "PGDATABASE": "synergia",
        "PGUSER": "synergia",
        "PGPASSWORD": "synergia-local-only",
        "PYTHONPATH": str(ROOT / "backend"),
    }

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "container_entrypoint.py"),
            sys.executable,
            "-c",
            "print('command-ready')",
        ],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "command-ready"
    assert "synergia startup: environment=development" in result.stderr


def test_entrypoint_accepts_homologation_environment_rendered_by_compose() -> None:
    compose_environment = os.environ | {
        "COMPOSE_DISABLE_ENV_FILE": "1",
        "SYNERGIA_LOCAL_AUTH_ENABLED": "false",
        "SYNERGIA_ENV": "homologation",
        "POSTGRES_PASSWORD": "synthetic-postgres-password",
        "AUTH_JWT_SIGNING_KEY": "synthetic-signing-key-with-at-least-32-bytes",
        "RATE_LIMIT_KEY_SECRET": "synthetic-rate-limit-key-with-at-least-32-bytes",
        "AUTH_ALLOWED_ORIGINS": "http://web.internal.example",
        "SYNERGIA_API_ORIGIN": "http://api.internal.example",
    }
    rendered = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        env=compose_environment,
        text=True,
    )
    backend_environment = json.loads(rendered.stdout)["services"]["backend"][
        "environment"
    ]
    backend_environment["PYTHONPATH"] = str(ROOT / "backend")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "container_entrypoint.py"),
            sys.executable,
            "-c",
            "print('command-ready')",
        ],
        check=False,
        capture_output=True,
        env=backend_environment,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "command-ready"
    assert "synergia startup: environment=homologation" in result.stderr


@pytest.mark.parametrize(
    "revision,expected", [("a" * 40, "a" * 40), ("invalid-secret-value", "unknown")]
)
def test_entrypoint_reports_only_a_valid_build_revision(revision, expected):
    environment = _deployment_environment("development") | {
        "SYNERGIA_BUILD_REVISION": revision,
        "DATABASE_URL": "synthetic-not-used",
        "PYTHONPATH": str(ROOT / "backend"),
    }
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/container_entrypoint.py"),
            sys.executable,
            "-c",
            "print('command-ready')",
        ],
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert f"revision={expected}" in result.stderr
    assert "invalid-secret-value" not in result.stderr


def test_compose_rejects_missing_postgres_password_before_services_start() -> None:
    compose_environment = os.environ | {"SYNERGIA_ENV": "homologation"}
    compose_environment.pop("POSTGRES_PASSWORD", None)

    result = subprocess.run(
        ["docker", "compose", "--env-file", "/dev/null", "config"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=compose_environment,
        text=True,
    )

    assert result.returncode != 0
    assert "POSTGRES_PASSWORD" in result.stderr


@pytest.mark.parametrize("password", ["synergia-local-only", "CHANGE_ME"])
def test_compose_preflight_rejects_unsafe_password_before_postgres(
    password: str,
) -> None:
    compose_environment = os.environ | {
        "SYNERGIA_ENV": "homologation",
        "POSTGRES_PASSWORD": password,
        "AUTH_JWT_SIGNING_KEY": "synthetic-signing-key-with-at-least-32-bytes",
        "RATE_LIMIT_KEY_SECRET": "synthetic-rate-limit-key-with-at-least-32-bytes",
        "AUTH_ALLOWED_ORIGINS": "http://web.internal.example",
        "SYNERGIA_API_ORIGIN": "http://api.internal.example",
    }
    rendered = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            "/dev/null",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        env=compose_environment,
        text=True,
    )
    services = json.loads(rendered.stdout)["services"]
    assert services["postgres"]["depends_on"]["config-check"] == {
        "condition": "service_completed_successfully",
        "required": True,
    }
    preflight_environment = services["config-check"]["environment"]
    preflight_environment["PYTHONPATH"] = str(ROOT / "backend")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "container_entrypoint.py"),
            sys.executable,
            "-c",
            "print('configuration-valid')",
        ],
        check=False,
        capture_output=True,
        env=preflight_environment,
        text=True,
    )

    assert result.returncode != 0
    assert "PGPASSWORD" in result.stderr
