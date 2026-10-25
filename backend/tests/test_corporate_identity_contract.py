from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.auth.config import AuthConfig
from app.auth.identity_provider import (
    ClaimsPolicy,
    CorporateIdentityConfig,
    FakeIdentityProvider,
    GroupRole,
    IdentityConfigurationError,
    IdentityProviderUnavailable,
    IdentityRejected,
    load_mapping,
    map_claims,
    resolve_access,
)
from app.errors import ApiError

pytestmark = pytest.mark.security
EXAMPLES = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "corporate-identity-claims-examples.json"
)
NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
ISSUER = "https://idp.example.invalid/synthetic"
AUDIENCE = "synergia-api-synthetic"
KEY = "synthetic-test-signing-key-with-at-least-32-bytes"


def _document() -> dict:
    return json.loads(EXAMPLES.read_text(encoding="utf-8"))


def _policy(**changes) -> ClaimsPolicy:
    raw = _document()["policy"]
    values = {
        "issuer": raw["issuer"],
        "audiences": frozenset(raw["audiences"]),
        "organization_aliases": {
            k.casefold(): v for k, v in raw["organizations"].items()
        },
        "group_roles": tuple(
            GroupRole(
                item["group"],
                item["role_key"],
                item.get("organization_code"),
                item.get("global_reviewed", False),
            )
            for item in raw["group_roles"]
        ),
    }
    values.update(changes)
    return ClaimsPolicy(**values)


def _claims(**changes) -> dict:
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "synthetic-subject-9000",
        "email": "teste.sintetico@example.invalid",
        "email_verified": True,
        "organizations": ["org-a-idp"],
        "groups": ["synergia-analysts-a"],
        "amr": ["mfa"],
        "exp": int((NOW + timedelta(minutes=10)).timestamp()),
        "iat": int(NOW.timestamp()),
    }
    claims.update(changes)
    return {k: v for k, v in claims.items() if v is not ...}


def _with_expiry(claims: dict) -> dict:
    return {"exp": int((NOW + timedelta(minutes=10)).timestamp()), **claims}


@pytest.mark.parametrize("example", _document()["examples"], ids=lambda e: e["id"])
def test_documented_examples_behave_exactly_as_the_contract_says(example) -> None:
    policy = _policy()
    claims = _with_expiry(example["claims"])
    expected = example["expect"]

    if expected["outcome"] == "rejected":
        with pytest.raises(IdentityRejected) as rejection:
            resolve_access(
                map_claims(claims, policy, provider_key="fake", now=NOW), policy
            )
        assert rejection.value.code == expected["code"]
        return
    identity = map_claims(claims, policy, provider_key="fake", now=NOW)
    access = resolve_access(identity, policy)
    assert sorted(access.organizations) == expected["organizations"]
    assert sorted(access.roles, key=str) == sorted(
        (tuple(role) for role in expected["roles"]), key=str
    )


def test_examples_are_synthetic_and_carry_no_secret_material() -> None:
    text = EXAMPLES.read_text(encoding="utf-8")

    assert _document()["synthetic"] is True
    for marker in ("password", "secret", "BEGIN ", "eyJ", "Bearer "):
        assert marker not in text
    assert text.count("example.invalid") >= 10


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"iss": "https://idp.example.invalid/other"}, "identity_issuer_mismatch"),
        ({"aud": "someone-else"}, "identity_audience_mismatch"),
        ({"aud": None}, "identity_audience_mismatch"),
        ({"exp": ...}, "identity_assertion_expired"),
        (
            {"exp": int((NOW - timedelta(minutes=5)).timestamp())},
            "identity_assertion_expired",
        ),
        (
            {"nbf": int((NOW + timedelta(minutes=5)).timestamp())},
            "identity_assertion_expired",
        ),
        (
            {"iat": int((NOW + timedelta(minutes=5)).timestamp())},
            "identity_assertion_expired",
        ),
        (
            {"auth_time": int((NOW - timedelta(days=2)).timestamp())},
            "identity_assertion_expired",
        ),
        ({"exp": "soon"}, "identity_claims_invalid"),
        ({"exp": True}, "identity_claims_invalid"),
        ({"sub": ...}, "identity_subject_invalid"),
        ({"sub": ""}, "identity_subject_invalid"),
        ({"sub": "a\nb"}, "identity_subject_invalid"),
        ({"sub": "x" * 256}, "identity_subject_invalid"),
        ({"email": ...}, "identity_email_invalid"),
        ({"email": "not-an-address"}, "identity_email_invalid"),
        ({"email_verified": ...}, "identity_email_invalid"),
        ({"amr": ...}, "identity_mfa_required"),
        ({"amr": ["pwd"]}, "identity_mfa_required"),
        ({"organizations": [1, 2]}, "identity_claims_invalid"),
        ({"organizations": ["org-a-idp"] * 101}, "identity_claims_invalid"),
        ({"groups": ["g"] * 201}, "identity_claims_invalid"),
        ({"name": "n" * 201}, "identity_claims_invalid"),
    ],
)
def test_every_invalid_or_missing_claim_rejects_the_identity(changes, code) -> None:
    with pytest.raises(IdentityRejected) as rejection:
        map_claims(_claims(**changes), _policy(), provider_key="fake", now=NOW)

    assert rejection.value.code == code


def test_a_valid_assertion_maps_to_a_neutral_identity_without_leaking_personal_data():
    identity = map_claims(_claims(), _policy(), provider_key="fake", now=NOW)

    assert identity.subject == "synthetic-subject-9000"
    assert identity.organizations == frozenset({"ORG-A"})
    assert "teste.sintetico" not in repr(identity)
    assert "synergia-analysts-a" not in repr(identity)


def test_clock_skew_tolerates_small_drift_but_not_more() -> None:
    policy = _policy(clock_skew_seconds=30)
    just_expired = int((NOW - timedelta(seconds=20)).timestamp())
    long_expired = int((NOW - timedelta(seconds=60)).timestamp())

    map_claims(_claims(exp=just_expired), policy, provider_key="fake", now=NOW)
    with pytest.raises(IdentityRejected):
        map_claims(_claims(exp=long_expired), policy, provider_key="fake", now=NOW)


def test_mfa_can_only_be_relaxed_by_explicit_policy() -> None:
    relaxed = _policy(require_mfa=False)

    identity = map_claims(_claims(amr=["pwd"]), relaxed, provider_key="fake", now=NOW)

    assert identity.methods == frozenset({"pwd"})


def test_groups_never_widen_access_beyond_the_reviewed_mapping() -> None:
    policy = _policy()
    identity = map_claims(
        _claims(
            organizations=["org-a-idp"],
            groups=["synergia-operators-b", "synergia-platform-admins-fake", "ADMIN"],
        ),
        policy,
        provider_key="fake",
        now=NOW,
    )

    access = resolve_access(identity, policy)

    assert access.roles == ()
    assert access.organizations == frozenset({"ORG-A"})


def test_group_matching_is_exact_not_a_prefix_or_substring() -> None:
    policy = _policy()
    identity = map_claims(
        _claims(groups=["synergia-analysts-a-extra", "xsynergia-analysts-a"]),
        policy,
        provider_key="fake",
        now=NOW,
    )

    assert resolve_access(identity, policy).roles == ()


def test_scoped_role_requires_its_organization_in_the_assertion() -> None:
    policy = _policy()
    identity = map_claims(
        _claims(organizations=["org-b-idp"], groups=["synergia-analysts-a"]),
        policy,
        provider_key="fake",
        now=NOW,
    )

    access = resolve_access(identity, policy)

    assert access.organizations == frozenset({"ORG-B"})
    assert access.roles == ()


def test_a_global_role_cannot_be_declared_without_review() -> None:
    with pytest.raises(IdentityConfigurationError) as error:
        GroupRole("synergia-platform-admins", "platform_admin")

    assert error.value.code == "global_mapping_not_reviewed"


@pytest.mark.parametrize("role_key", ["", "Admin Role", "../x", "A" * 130])
def test_role_keys_are_validated(role_key) -> None:
    with pytest.raises(IdentityConfigurationError):
        GroupRole("group", role_key, "ORG-A")


def test_fake_provider_is_offline_and_fails_closed() -> None:
    directory = {"known": _claims()}
    provider = FakeIdentityProvider(_policy(), directory, clock=lambda: NOW)

    assert provider.authenticate("known").subject == "synthetic-subject-9000"
    with pytest.raises(IdentityRejected) as unknown:
        provider.authenticate("unknown")
    assert unknown.value.code == "identity_assertion_invalid"

    provider.unavailable = True
    with pytest.raises(IdentityProviderUnavailable):
        provider.authenticate("known")


def test_fake_provider_does_not_touch_the_network(monkeypatch) -> None:
    import socket

    def no_network(*args, **kwargs):
        raise AssertionError("The offline provider must never connect")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    provider = FakeIdentityProvider(_policy(), {"k": _claims()}, clock=lambda: NOW)

    assert provider.authenticate("k").provider_key == "fake"


def _clear_identity_environment(monkeypatch) -> None:
    import os

    for key in tuple(os.environ):
        if key.startswith(("AUTH_CORPORATE_", "AUTH_CLAIM_", "AUTH_IDENTITY_")):
            monkeypatch.delenv(key)


def _corporate_environment(monkeypatch, tmp_path, **overrides) -> None:
    _clear_identity_environment(monkeypatch)
    values = {
        "AUTH_IDENTITY_PROVIDER": "corporate",
        "AUTH_CORPORATE_ISSUER": ISSUER,
        "AUTH_CORPORATE_DISCOVERY_URL": f"{ISSUER}/.well-known/openid-configuration",
        "AUTH_CORPORATE_AUDIENCE": AUDIENCE,
        "AUTH_CORPORATE_CLIENT_ID": "synergia-synthetic-client",
        "AUTH_CORPORATE_CLIENT_SECRET_FILE": str(tmp_path / "not-created" / "secret"),
    }
    values.update(overrides)
    for key, value in values.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_identity_provider_defaults_to_local_and_never_enables_corporate(monkeypatch):
    _clear_identity_environment(monkeypatch)

    config = CorporateIdentityConfig.from_env("production")

    assert (config.mode, config.policy) == ("local", None)


@pytest.mark.parametrize("environment", ["production", "homologation", ""])
def test_the_synthetic_provider_is_forbidden_outside_development_and_test(
    monkeypatch, environment
) -> None:
    _clear_identity_environment(monkeypatch)
    monkeypatch.setenv("AUTH_IDENTITY_PROVIDER", "fake")

    with pytest.raises(IdentityConfigurationError) as error:
        CorporateIdentityConfig.from_env(environment)

    assert error.value.code == "fake_provider_forbidden"
    for allowed in ("development", "test"):
        assert CorporateIdentityConfig.from_env(allowed).mode == "fake"


def test_unknown_provider_mode_is_rejected(monkeypatch) -> None:
    _clear_identity_environment(monkeypatch)
    monkeypatch.setenv("AUTH_IDENTITY_PROVIDER", "saml")

    with pytest.raises(IdentityConfigurationError, match="provider_mode_invalid"):
        CorporateIdentityConfig.from_env("test")


def test_corporate_configuration_validates_without_network_or_reading_the_secret(
    monkeypatch, tmp_path
) -> None:
    import socket

    def no_network(*args, **kwargs):
        raise AssertionError("Configuration must never connect")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    _corporate_environment(monkeypatch, tmp_path)

    config = CorporateIdentityConfig.from_env("production")

    assert config.mode == "corporate" and config.policy is not None
    assert config.policy.require_mfa is True
    assert "synergia-synthetic-client" not in repr(config)
    assert str(tmp_path) not in repr(config)
    assert not (tmp_path / "not-created").exists()


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        (
            {"AUTH_CORPORATE_ISSUER": "http://idp.example.invalid"},
            "auth_corporate_issuer_invalid",
        ),
        ({"AUTH_CORPORATE_ISSUER": None}, "auth_corporate_issuer_invalid"),
        (
            {"AUTH_CORPORATE_DISCOVERY_URL": "https://user:pw@idp.example.invalid/x"},
            "auth_corporate_discovery_url_invalid",
        ),
        (
            {"AUTH_CORPORATE_DISCOVERY_URL": "https://evil.example.invalid/x"},
            "auth_corporate_discovery_url_invalid",
        ),
        ({"AUTH_CORPORATE_AUDIENCE": ""}, "client_settings_invalid"),
        ({"AUTH_CORPORATE_CLIENT_ID": ""}, "client_settings_invalid"),
        (
            {"AUTH_CORPORATE_CLIENT_SECRET_FILE": "relative/secret"},
            "client_settings_invalid",
        ),
        ({"AUTH_CORPORATE_CLIENT_SECRET_FILE": ""}, "client_settings_invalid"),
        (
            {"AUTH_CORPORATE_REQUIRE_MFA": "false"},
            "mfa_cannot_be_disabled_in_production",
        ),
    ],
)
def test_incomplete_corporate_configuration_fails_closed(
    monkeypatch, tmp_path, overrides, code
) -> None:
    _corporate_environment(monkeypatch, tmp_path, **overrides)

    with pytest.raises(IdentityConfigurationError) as error:
        CorporateIdentityConfig.from_env("production")

    assert error.value.code == code


def test_mfa_may_only_be_relaxed_outside_production_by_explicit_setting(
    monkeypatch, tmp_path
) -> None:
    _corporate_environment(monkeypatch, tmp_path, AUTH_CORPORATE_REQUIRE_MFA="false")

    config = CorporateIdentityConfig.from_env("homologation")

    assert config.policy is not None and config.policy.require_mfa is False


def test_claim_names_are_configurable_without_code_changes(monkeypatch, tmp_path):
    _corporate_environment(
        monkeypatch,
        tmp_path,
        AUTH_CLAIM_SUBJECT="oid",
        AUTH_CLAIM_ORGANIZATIONS="company_units",
    )
    config = CorporateIdentityConfig.from_env("homologation")

    assert config.policy is not None
    assert config.policy.claim_names.subject == "oid"
    assert config.policy.claim_names.organizations == "company_units"
    assert config.policy.claim_names.groups == "groups"


def test_mapping_file_is_private_absolute_and_reviewed(tmp_path) -> None:
    good = tmp_path / "mapping.json"
    good.write_text(
        json.dumps(
            {
                "organizations": {"UNIT-1": "ORG-A"},
                "group_roles": [
                    {
                        "group": "g1",
                        "role_key": "analyst",
                        "organization_code": "ORG-A",
                    },
                    {"group": "g2", "role_key": "admin", "global_reviewed": True},
                ],
            }
        ),
        encoding="utf-8",
    )

    aliases, roles = load_mapping(str(good))

    assert aliases == {"unit-1": "ORG-A"}
    assert [role.role_key for role in roles] == ["analyst", "admin"]
    with pytest.raises(IdentityConfigurationError, match="mapping_file_invalid"):
        load_mapping("relative/mapping.json")
    with pytest.raises(IdentityConfigurationError, match="mapping_file_invalid"):
        load_mapping(str(tmp_path / "missing.json"))

    unreviewed = tmp_path / "unreviewed.json"
    unreviewed.write_text(
        json.dumps({"group_roles": [{"group": "g", "role_key": "admin"}]}),
        encoding="utf-8",
    )
    with pytest.raises(IdentityConfigurationError, match="global_mapping_not_reviewed"):
        load_mapping(str(unreviewed))
    malformed = tmp_path / "malformed.json"
    malformed.write_text(
        json.dumps({"group_roles": [{"role_key": "x"}]}), encoding="utf-8"
    )
    with pytest.raises(IdentityConfigurationError, match="mapping_invalid"):
        load_mapping(str(malformed))


def _auth_environment(monkeypatch, environment: str, **extra) -> None:
    _clear_identity_environment(monkeypatch)
    for key in ("AUTH_LOCAL_LOGIN_EXPIRES_AT", "SYNERGIA_LOCAL_AUTH_ENABLED"):
        monkeypatch.delenv(key, raising=False)
    for key, value in {
        "SYNERGIA_ENV": environment,
        "AUTH_JWT_ALGORITHM": "HS256",
        "AUTH_JWT_SIGNING_KEY": KEY,
        "AUTH_JWT_ISSUER": "synergia-test",
        "AUTH_JWT_AUDIENCE": "synergia-api-test",
        "AUTH_REFRESH_COOKIE_SECURE": "false"
        if environment != "production"
        else "true",
        **extra,
    }.items():
        monkeypatch.setenv(key, value)


def _in(days: float) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def test_local_login_in_homologation_requires_an_explicit_end_date(monkeypatch):
    _auth_environment(monkeypatch, "homologation", SYNERGIA_LOCAL_AUTH_ENABLED="true")

    assert AuthConfig.from_env().local_auth_enabled is False

    monkeypatch.setenv("AUTH_LOCAL_LOGIN_EXPIRES_AT", _in(30))
    config = AuthConfig.from_env()
    assert config.local_auth_enabled is True
    assert config.local_login_expires_at is not None


@pytest.mark.parametrize("value", ["not-a-date", "2026-12-01T10:00:00", _in(91)])
def test_invalid_or_too_distant_end_dates_fail_closed(monkeypatch, value) -> None:
    _auth_environment(
        monkeypatch,
        "homologation",
        SYNERGIA_LOCAL_AUTH_ENABLED="true",
        AUTH_LOCAL_LOGIN_EXPIRES_AT=value,
    )

    with pytest.raises(ApiError) as error:
        AuthConfig.from_env()

    assert error.value.code == "auth_configuration_invalid"


@pytest.mark.parametrize("environment", ["development", "test"])
def test_local_login_needs_no_end_date_in_development_and_test(
    monkeypatch, environment
) -> None:
    _auth_environment(monkeypatch, environment, SYNERGIA_LOCAL_AUTH_ENABLED="true")

    assert AuthConfig.from_env().local_auth_enabled is True


def test_local_login_is_never_enabled_in_production_even_with_an_end_date(monkeypatch):
    _auth_environment(
        monkeypatch,
        "production",
        SYNERGIA_LOCAL_AUTH_ENABLED="true",
        AUTH_LOCAL_LOGIN_EXPIRES_AT=_in(10),
    )

    config = AuthConfig.from_env()

    assert config.local_auth_enabled is False
    assert config.local_login_expires_at is None


def test_auth_configuration_rejects_the_synthetic_provider_in_production(monkeypatch):
    _auth_environment(monkeypatch, "production", AUTH_IDENTITY_PROVIDER="fake")

    with pytest.raises(ApiError) as error:
        AuthConfig.from_env()

    assert error.value.code == "auth_configuration_invalid"


def test_auth_configuration_reports_the_selected_provider(monkeypatch) -> None:
    _auth_environment(monkeypatch, "test", AUTH_IDENTITY_PROVIDER="fake")

    assert AuthConfig.from_env().identity_provider == "fake"
