"""Neutral contract for a corporate identity provider.

Nothing here talks to a network or to a real provider. The module defines the
claims the application would accept, how they are validated and mapped to the
internal access model, and an offline provider used by tests. Every failure
rejects the identity: a missing or invalid claim never widens access.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

SAFE_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/+ -]{0,254}")
ROLE_KEY = re.compile(r"[a-z][a-z0-9_.-]{0,119}")
ORGANIZATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
MAX_ORGANIZATIONS = 100
MAX_GROUPS = 200
MAX_METHODS = 20
DEFAULT_MFA_METHODS = frozenset({"mfa", "otp", "hwk", "swk", "fpt", "pop"})
PROVIDER_MODES = frozenset({"local", "fake", "corporate"})
OFFLINE_ENVIRONMENTS = frozenset({"development", "test"})

# Stable codes. Callers answer with one generic message so a response never says
# which check failed; the code is for audit events and tests.
REJECTION_CODES = frozenset(
    {
        "identity_assertion_invalid",
        "identity_issuer_mismatch",
        "identity_audience_mismatch",
        "identity_assertion_expired",
        "identity_subject_invalid",
        "identity_email_invalid",
        "identity_claims_invalid",
        "identity_mfa_required",
        "identity_scope_missing",
    }
)


class IdentityRejected(Exception):
    """The assertion is not acceptable; no session may be created."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        if code not in REJECTION_CODES:  # pragma: no cover - programming error
            raise ValueError(f"unknown rejection code: {code}")
        self.code = code


class IdentityProviderUnavailable(Exception):
    """The provider cannot be reached; there is no fallback to local login."""


class IdentityConfigurationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ClaimNames:
    """Claim names are configuration: the provider's real names are not known."""

    subject: str = "sub"
    email: str = "email"
    email_verified: str = "email_verified"
    name: str = "name"
    organizations: str = "organizations"
    groups: str = "groups"
    methods: str = "amr"
    authenticated_at: str = "auth_time"


@dataclass(frozen=True)
class GroupRole:
    """One reviewed mapping from a provider group to an internal role.

    A role without ``organization_code`` is global and must be marked as
    reviewed; it can never be created by convenience.
    """

    group: str
    role_key: str
    organization_code: str | None = None
    global_reviewed: bool = False

    def __post_init__(self) -> None:
        if not self.group.strip() or not ROLE_KEY.fullmatch(self.role_key):
            raise IdentityConfigurationError("mapping_invalid")
        if self.organization_code is None and not self.global_reviewed:
            raise IdentityConfigurationError("global_mapping_not_reviewed")
        if self.organization_code is not None and not ORGANIZATION.fullmatch(
            self.organization_code
        ):
            raise IdentityConfigurationError("mapping_invalid")


@dataclass(frozen=True)
class ClaimsPolicy:
    issuer: str
    audiences: frozenset[str]
    claim_names: ClaimNames = ClaimNames()
    require_mfa: bool = True
    mfa_methods: frozenset[str] = DEFAULT_MFA_METHODS
    require_verified_email: bool = True
    clock_skew_seconds: int = 30
    max_authentication_age_seconds: int = 24 * 3600
    organization_aliases: Mapping[str, str] = field(default_factory=dict)
    group_roles: tuple[GroupRole, ...] = ()

    def __post_init__(self) -> None:
        if not self.issuer or not self.audiences:
            raise IdentityConfigurationError("issuer_or_audience_missing")
        if self.clock_skew_seconds < 0 or self.max_authentication_age_seconds <= 0:
            raise IdentityConfigurationError("policy_invalid")


@dataclass(frozen=True)
class ExternalIdentity:
    provider_key: str
    subject: str
    email: str = field(repr=False)
    display_name: str = field(repr=False)
    organizations: frozenset[str]
    methods: frozenset[str]
    authenticated_at: datetime | None = None
    groups: frozenset[str] = field(default_factory=frozenset, repr=False)


@dataclass(frozen=True)
class ResolvedAccess:
    organizations: frozenset[str]
    roles: tuple[tuple[str, str | None], ...]


class IdentityProvider(Protocol):
    """Port the application depends on; adapters translate their own protocol."""

    provider_key: str

    def authenticate(self, assertion: str) -> ExternalIdentity: ...


def _text_list(value: Any, limit: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list | tuple) or len(value) > limit:
        raise IdentityRejected("identity_claims_invalid")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise IdentityRejected("identity_claims_invalid")
    return [item.strip() for item in value]


def _timestamp(claims: Mapping[str, Any], name: str) -> int | None:
    value = claims.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise IdentityRejected("identity_claims_invalid")
    return int(value)


def map_claims(
    claims: Mapping[str, Any],
    policy: ClaimsPolicy,
    *,
    provider_key: str,
    now: datetime | None = None,
) -> ExternalIdentity:
    """Validate a verified claim set and translate it into a neutral identity.

    Signature verification belongs to the protocol adapter; this function treats
    ``claims`` as untrusted content and applies the contract to it.
    """
    current = int((now or datetime.now(UTC)).timestamp())
    names = policy.claim_names
    skew = policy.clock_skew_seconds

    if claims.get("iss") != policy.issuer:
        raise IdentityRejected("identity_issuer_mismatch")
    audience = claims.get("aud")
    audiences = [audience] if isinstance(audience, str) else audience
    if not isinstance(audiences, list) or not any(
        isinstance(item, str) and item in policy.audiences for item in audiences
    ):
        raise IdentityRejected("identity_audience_mismatch")

    expires = _timestamp(claims, "exp")
    if expires is None or current > expires + skew:
        raise IdentityRejected("identity_assertion_expired")
    not_before = _timestamp(claims, "nbf")
    issued = _timestamp(claims, "iat")
    if (not_before is not None and not_before > current + skew) or (
        issued is not None and issued > current + skew
    ):
        raise IdentityRejected("identity_assertion_expired")

    subject = claims.get(names.subject)
    if (
        not isinstance(subject, str)
        or subject != subject.strip()
        or not 1 <= len(subject) <= 255
        or any(ord(character) < 32 or ord(character) == 127 for character in subject)
    ):
        raise IdentityRejected("identity_subject_invalid")

    # Imported here: ``app.users`` depends on the authorization stack, which
    # depends on this package's configuration.
    from app.users import normalize_email

    raw_email = claims.get(names.email)
    if not isinstance(raw_email, str):
        raise IdentityRejected("identity_email_invalid")
    try:
        email = normalize_email(raw_email)
    except ValueError:
        raise IdentityRejected("identity_email_invalid") from None
    if policy.require_verified_email and claims.get(names.email_verified) is not True:
        raise IdentityRejected("identity_email_invalid")

    display_name = claims.get(names.name, "")
    if not isinstance(display_name, str) or len(display_name) > 200:
        raise IdentityRejected("identity_claims_invalid")

    organizations = set()
    for value in _text_list(claims.get(names.organizations), MAX_ORGANIZATIONS):
        alias = policy.organization_aliases.get(value.casefold())
        if alias is not None and ORGANIZATION.fullmatch(alias):
            organizations.add(alias)
        # An unknown organization is ignored: it never grants anything.

    methods = frozenset(
        item.casefold() for item in _text_list(claims.get(names.methods), MAX_METHODS)
    )
    if policy.require_mfa and not methods & policy.mfa_methods:
        raise IdentityRejected("identity_mfa_required")

    authenticated = _timestamp(claims, names.authenticated_at)
    authenticated_at = None
    if authenticated is not None:
        if current - authenticated > policy.max_authentication_age_seconds + skew:
            raise IdentityRejected("identity_assertion_expired")
        authenticated_at = datetime.fromtimestamp(authenticated, UTC)

    groups = _text_list(claims.get(names.groups), MAX_GROUPS)
    return ExternalIdentity(
        provider_key=provider_key,
        subject=subject,
        email=email,
        display_name=display_name.strip(),
        organizations=frozenset(organizations),
        methods=methods,
        authenticated_at=authenticated_at,
        groups=frozenset(group.casefold() for group in groups),
    )


def resolve_access(identity: ExternalIdentity, policy: ClaimsPolicy) -> ResolvedAccess:
    """Translate groups into roles through the reviewed mapping only.

    Unknown groups grant nothing; an organization-scoped role needs that
    organization in the assertion; an identity left without any organization
    scope or reviewed global role is rejected rather than admitted empty.
    """
    roles: list[tuple[str, str | None]] = []
    for entry in policy.group_roles:
        if entry.group.casefold() not in identity.groups:
            continue
        if entry.organization_code is None:
            roles.append((entry.role_key, None))
        elif entry.organization_code in identity.organizations:
            roles.append((entry.role_key, entry.organization_code))
    if not identity.organizations and not any(org is None for _, org in roles):
        raise IdentityRejected("identity_scope_missing")
    return ResolvedAccess(
        organizations=identity.organizations, roles=tuple(sorted(set(roles), key=str))
    )


class FakeIdentityProvider:
    """Offline provider: synthetic directory, no network, no secrets.

    ``assertion`` is the key of a registered claim set. ``unavailable`` simulates
    an outage, which must surface as ``IdentityProviderUnavailable``.
    """

    provider_key = "fake"

    def __init__(
        self,
        policy: ClaimsPolicy,
        directory: Mapping[str, Mapping[str, Any]],
        *,
        clock: Any = None,
        unavailable: bool = False,
    ) -> None:
        self.policy = policy
        self.directory = dict(directory)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.unavailable = unavailable

    def authenticate(self, assertion: str) -> ExternalIdentity:
        if self.unavailable:
            raise IdentityProviderUnavailable("identity provider unavailable")
        claims = self.directory.get(assertion)
        if claims is None:
            raise IdentityRejected("identity_assertion_invalid")
        return map_claims(
            claims, self.policy, provider_key=self.provider_key, now=self.clock()
        )


def _https_url(name: str, value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username:
        raise IdentityConfigurationError(f"{name.lower()}_invalid")
    return value


def load_mapping(path: str) -> tuple[Mapping[str, str], tuple[GroupRole, ...]]:
    """Read the reviewed organization and group mapping from a private file."""
    file = Path(path)
    if not file.is_absolute():
        raise IdentityConfigurationError("mapping_file_invalid")
    try:
        document = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise IdentityConfigurationError("mapping_file_invalid") from None
    if not isinstance(document, dict):
        raise IdentityConfigurationError("mapping_file_invalid")
    aliases = document.get("organizations", {})
    entries = document.get("group_roles", [])
    if not isinstance(aliases, dict) or not isinstance(entries, list):
        raise IdentityConfigurationError("mapping_file_invalid")
    try:
        roles = tuple(
            GroupRole(
                group=str(item["group"]),
                role_key=str(item["role_key"]),
                organization_code=item.get("organization_code"),
                global_reviewed=item.get("global_reviewed") is True,
            )
            for item in entries
        )
    except (KeyError, TypeError, AttributeError):
        raise IdentityConfigurationError("mapping_invalid") from None
    return {str(k).casefold(): str(v) for k, v in aliases.items()}, roles


@dataclass(frozen=True)
class CorporateIdentityConfig:
    """Disabled-by-default settings; the live adapter is not implemented yet."""

    mode: str
    policy: ClaimsPolicy | None = None
    client_id: str = field(default="", repr=False)
    client_secret_file: str = field(default="", repr=False)
    discovery_url: str = ""

    @classmethod
    def from_env(cls, environment: str) -> CorporateIdentityConfig:
        mode = os.getenv("AUTH_IDENTITY_PROVIDER", "local").strip().lower()
        if mode not in PROVIDER_MODES:
            raise IdentityConfigurationError("provider_mode_invalid")
        if mode == "local":
            return cls(mode="local")
        if mode == "fake" and environment not in OFFLINE_ENVIRONMENTS:
            # The synthetic provider must never be reachable outside tests.
            raise IdentityConfigurationError("fake_provider_forbidden")
        if mode == "fake":
            return cls(mode="fake")

        issuer = _https_url(
            "AUTH_CORPORATE_ISSUER", os.getenv("AUTH_CORPORATE_ISSUER", "")
        )
        discovery = _https_url(
            "AUTH_CORPORATE_DISCOVERY_URL",
            os.getenv("AUTH_CORPORATE_DISCOVERY_URL", ""),
        )
        if urlparse(discovery).hostname != urlparse(issuer).hostname:
            raise IdentityConfigurationError("auth_corporate_discovery_url_invalid")
        audiences = frozenset(
            item.strip()
            for item in os.getenv("AUTH_CORPORATE_AUDIENCE", "").split(",")
            if item.strip()
        )
        client_id = os.getenv("AUTH_CORPORATE_CLIENT_ID", "").strip()
        secret_file = os.getenv("AUTH_CORPORATE_CLIENT_SECRET_FILE", "").strip()
        if not client_id or not audiences or not Path(secret_file).is_absolute():
            raise IdentityConfigurationError("client_settings_invalid")
        require_mfa = os.getenv("AUTH_CORPORATE_REQUIRE_MFA", "true").lower() != "false"
        if environment == "production" and not require_mfa:
            raise IdentityConfigurationError("mfa_cannot_be_disabled_in_production")
        mapping_file = os.getenv("AUTH_CORPORATE_MAPPING_FILE", "").strip()
        aliases, roles = load_mapping(mapping_file) if mapping_file else ({}, ())
        names = ClaimNames(
            **{
                key: os.getenv(f"AUTH_CLAIM_{key.upper()}", default).strip() or default
                for key, default in ClaimNames().__dict__.items()
            }
        )
        return cls(
            mode="corporate",
            policy=ClaimsPolicy(
                issuer=issuer,
                audiences=audiences,
                claim_names=names,
                require_mfa=require_mfa,
                organization_aliases=aliases,
                group_roles=roles,
            ),
            client_id=client_id,
            client_secret_file=secret_file,
            discovery_url=discovery,
        )
