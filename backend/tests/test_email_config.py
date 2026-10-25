from __future__ import annotations

import socket
from dataclasses import replace
from uuid import uuid4

import pytest

from app.email_config import EmailConfig, SMTPConfig
from app.email_contracts import EmailMessage, PermanentEmailError
from app.email_delivery import EmailConfig as LegacyEmailConfig
from app.email_delivery import EmailMessage as LegacyEmailMessage
from app.email_delivery import LocalCaptureEmailProvider, build_provider

SECRET = "SYNTHETIC-CREDENTIAL-143"
SENDER = "sender@example.invalid"
RECIPIENT = "allowed+test@example.invalid"


@pytest.fixture(autouse=True)
def smtp_environment(monkeypatch):
    for key in (
        "EMAIL_SMTP_HOST",
        "EMAIL_SMTP_PORT",
        "EMAIL_SMTP_TLS_MODE",
        "EMAIL_SMTP_TIMEOUT_SECONDS",
        "EMAIL_SMTP_AUTH_MODE",
        "EMAIL_SMTP_USERNAME",
        "EMAIL_SMTP_PASSWORD",
        "EMAIL_SMTP_PASSWORD_FILE",
        "EMAIL_SMTP_ALLOWED_RECIPIENTS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("EMAIL_SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setenv("EMAIL_FROM_ADDRESS", SENDER)
    monkeypatch.setenv("EMAIL_SMTP_USERNAME", "synthetic-login")
    monkeypatch.setenv("EMAIL_SMTP_PASSWORD", SECRET)
    monkeypatch.setenv("EMAIL_SMTP_ALLOWED_RECIPIENTS", RECIPIENT)

    def no_network(*args, **kwargs):
        raise AssertionError("Configuration must never connect or resolve DNS")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)


def message(**overrides):
    value = EmailMessage(
        uuid4(),
        RECIPIENT,
        SENDER,
        "Assunto sintético",
        "Corpo sintético\nSegunda linha.",
        "pt-BR",
        None,
    )
    return replace(value, **overrides)


def test_generic_smtp_configuration_requires_no_network_and_no_provider_specifics():
    config = SMTPConfig.from_env()
    assert (config.host, config.port, config.tls_mode, config.timeout_seconds) == (
        "smtp.example.invalid",
        587,
        "starttls",
        15.0,
    )
    assert config.validate_message(message()) == (SENDER, RECIPIENT)
    assert config.auth_mode == "password" and config.password == SECRET


@pytest.mark.parametrize(
    "key,value",
    [
        ("EMAIL_SMTP_HOST", ""),
        ("EMAIL_SMTP_HOST", "smtp://smtp.example.invalid"),
        ("EMAIL_SMTP_HOST", "host name"),
        ("EMAIL_SMTP_HOST", "bad..host"),
        ("EMAIL_SMTP_PORT", "0"),
        ("EMAIL_SMTP_PORT", "65536"),
        ("EMAIL_SMTP_PORT", SECRET),
        ("EMAIL_SMTP_TLS_MODE", "none"),
        ("EMAIL_SMTP_TLS_MODE", "plain"),
        ("EMAIL_SMTP_TIMEOUT_SECONDS", "0"),
        ("EMAIL_SMTP_TIMEOUT_SECONDS", "-1"),
        ("EMAIL_SMTP_TIMEOUT_SECONDS", "31"),
        ("EMAIL_SMTP_TIMEOUT_SECONDS", "nan"),
        ("EMAIL_SMTP_TIMEOUT_SECONDS", "inf"),
        ("EMAIL_SMTP_TIMEOUT_SECONDS", SECRET),
        ("EMAIL_SMTP_AUTH_MODE", "unknown"),
        ("EMAIL_SMTP_USERNAME", ""),
        ("EMAIL_SMTP_USERNAME", "user\r\nINJECTED"),
        ("EMAIL_SMTP_PASSWORD", ""),
        ("EMAIL_SMTP_PASSWORD", "secret\nINJECTED"),
        ("EMAIL_FROM_ADDRESS", "Name <sender@example.invalid>"),
        ("EMAIL_FROM_ADDRESS", "sender@example.invalid\r\nBcc: other@example.invalid"),
        ("EMAIL_SMTP_ALLOWED_RECIPIENTS", ""),
        ("EMAIL_SMTP_ALLOWED_RECIPIENTS", "*"),
        ("EMAIL_SMTP_ALLOWED_RECIPIENTS", "*@example.invalid"),
        ("EMAIL_SMTP_ALLOWED_RECIPIENTS", "Name <allowed@example.invalid>"),
        ("EMAIL_SMTP_ALLOWED_RECIPIENTS", "one@example.invalid,"),
        ("EMAIL_SMTP_ALLOWED_RECIPIENTS", "one@example.invalid,,two@example.invalid"),
        ("EMAIL_SMTP_ALLOWED_RECIPIENTS", "a..b@example.invalid"),
        ("EMAIL_SMTP_ALLOWED_RECIPIENTS", "one@example.invalid\n"),
    ],
)
def test_invalid_configuration_fails_offline_without_exposing_values(
    monkeypatch, key, value
):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError) as error:
        SMTPConfig.from_env()
    assert SECRET not in str(error.value)
    assert "INJECTED" not in str(error.value)
    assert "@example.invalid" not in str(error.value)


def test_implicit_tls_and_explicit_relay_auth_mode_are_provider_independent(
    monkeypatch,
):
    monkeypatch.setenv("EMAIL_SMTP_TLS_MODE", "implicit")
    monkeypatch.setenv("EMAIL_SMTP_PORT", "465")
    monkeypatch.setenv("EMAIL_SMTP_AUTH_MODE", "none")
    monkeypatch.delenv("EMAIL_SMTP_USERNAME")
    monkeypatch.delenv("EMAIL_SMTP_PASSWORD")
    config = SMTPConfig.from_env()
    assert (config.tls_mode, config.port, config.auth_mode) == ("implicit", 465, "none")
    assert not config.username and not config.password


def test_unauthenticated_relay_cannot_silently_ignore_supplied_credentials(monkeypatch):
    monkeypatch.setenv("EMAIL_SMTP_AUTH_MODE", "none")
    with pytest.raises(ValueError, match="must not configure credentials"):
        SMTPConfig.from_env()


def test_secret_file_preserves_spaces_without_exposing_its_path(monkeypatch, tmp_path):
    path = tmp_path / "PRIVATE-SECRET-FILE"
    path.write_text(" leading-and-trailing-spaces  \n")
    monkeypatch.delenv("EMAIL_SMTP_PASSWORD")
    monkeypatch.setenv("EMAIL_SMTP_PASSWORD_FILE", str(path))
    config = SMTPConfig.from_env()
    assert config.password == " leading-and-trailing-spaces  "
    for private in (str(path), config.password, SENDER, RECIPIENT, "synthetic-login"):
        assert private not in repr(config)


@pytest.mark.parametrize(
    "content", [None, b"", b"\xff", b"x" * 4097, b"secret\nembedded\n"]
)
def test_unreadable_or_invalid_secret_file_has_safe_errors(
    monkeypatch, tmp_path, content
):
    path = tmp_path / "PRIVATE-SECRET-FILE"
    if content is not None:
        path.write_bytes(content)
    monkeypatch.delenv("EMAIL_SMTP_PASSWORD")
    monkeypatch.setenv("EMAIL_SMTP_PASSWORD_FILE", str(path))
    with pytest.raises(ValueError) as error:
        SMTPConfig.from_env()
    assert str(path) not in str(error.value)
    assert "embedded" not in str(error.value)


def test_ambiguous_secret_sources_are_refused_before_reading_file(monkeypatch):
    monkeypatch.setenv("EMAIL_SMTP_PASSWORD_FILE", "/PRIVATE-NONEXISTENT")
    with pytest.raises(ValueError, match="only one SMTP password source"):
        SMTPConfig.from_env()


def test_allowlist_is_exact_and_normalized_without_provider_alias_expansion(
    monkeypatch,
):
    monkeypatch.setenv(
        "EMAIL_SMTP_ALLOWED_RECIPIENTS",
        " Allowed+test@EXAMPLE.invalid , second@example.invalid",
    )
    config = SMTPConfig.from_env()
    assert config.validate_message(
        message(recipient="ALLOWED+TEST@EXAMPLE.INVALID")
    ) == (SENDER, RECIPIENT)
    for address in (
        "allowed@example.invalid",
        "allowed.test@example.invalid",
        "other@example.invalid",
        "allowed+test@other.invalid",
    ):
        with pytest.raises(PermanentEmailError, match="not_allowed"):
            config.validate_message(message(recipient=address))


@pytest.mark.parametrize(
    "overrides",
    [
        {"sender": "other@example.invalid"},
        {"recipient": "Name <allowed+test@example.invalid>"},
        {"recipient": RECIPIENT + ",other@example.invalid"},
        {"recipient": RECIPIENT + "\r\nBcc: other@example.invalid"},
        {"subject": "Safe\r\nBcc: other@example.invalid"},
        {"subject": ""},
        {"subject": "\ud800"},
        {"subject": "x" * 999},
        {"subject": "A\tB"},
        {"body": "\x00PRIVATE"},
        {"body": "\x1bPRIVATE"},
        {"body": ""},
        {"body": "\ud800"},
        {"body": "x" * 262145},
    ],
)
def test_envelope_and_message_injection_are_rejected_before_connection(overrides):
    with pytest.raises(PermanentEmailError) as error:
        SMTPConfig.from_env().validate_message(message(**overrides))
    assert "PRIVATE" not in str(error.value)
    assert "@example.invalid" not in str(error.value)


def test_public_imports_and_local_capture_remain_compatible(monkeypatch, tmp_path):
    assert LegacyEmailConfig is EmailConfig and LegacyEmailMessage is EmailMessage
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "local_capture")
    monkeypatch.setenv("EMAIL_CAPTURE_PATH", str(tmp_path / "capture.jsonl"))
    monkeypatch.setenv("EMAIL_SMTP_PORT", "INVALID-IGNORED")
    config = EmailConfig.from_env()
    provider = build_provider(config)
    assert isinstance(provider, LocalCaptureEmailProvider)
    item = message()
    assert provider.send(item) == provider.send(item)
    assert len(config.capture_path.read_text().splitlines()) == 1
    assert item.body not in repr(item) and item.recipient not in repr(item)


def test_disabled_channel_ignores_transport_configuration(monkeypatch):
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "false")
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    monkeypatch.setenv("EMAIL_SMTP_PASSWORD_FILE", "/PRIVATE-NONEXISTENT")
    assert EmailConfig.from_env() == EmailConfig()


def test_smtp_configuration_builds_provider_without_connecting(monkeypatch):
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    config = EmailConfig.from_env()
    provider = build_provider(config)
    assert config.provider == provider.name == "smtp"
    assert config.smtp is not None and config.capture_path is None
    assert provider.config is config.smtp


@pytest.mark.parametrize(
    "overrides",
    [
        {"port": True},
        {"timeout_seconds": True},
        {"allowed_recipients": "*"},
        {"allowed_recipients": frozenset()},
        {"password": "secret\x00"},
        {"password": "\ud800"},
    ],
)
def test_programmatic_configuration_cannot_bypass_policy(overrides):
    with pytest.raises(ValueError):
        replace(SMTPConfig.from_env(), **overrides)


def test_public_configuration_never_reads_the_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    unreadable = tmp_path / "ausente" / "smtp-secret"
    monkeypatch.delenv("EMAIL_SMTP_PASSWORD")
    monkeypatch.setenv("EMAIL_SMTP_PASSWORD_FILE", str(unreadable))
    opened: list[str] = []
    real_open = type(unreadable).open

    def tracking_open(self, *args, **kwargs):
        opened.append(str(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(type(unreadable), "open", tracking_open)

    public = EmailConfig.from_env(load_secret=False)

    assert opened == []
    assert public.provider == "smtp" and public.smtp is not None
    assert public.smtp.password is None and not public.smtp.secret_loaded
    with pytest.raises(ValueError, match="unreadable"):
        EmailConfig.from_env()


def test_public_configuration_ignores_even_conflicting_secret_sources(monkeypatch):
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    monkeypatch.setenv("EMAIL_SMTP_PASSWORD_FILE", "/run/secrets/anything")

    assert EmailConfig.from_env(load_secret=False).smtp is not None
    with pytest.raises(ValueError, match="only one"):
        EmailConfig.from_env()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("EMAIL_SMTP_HOST", "not a host"),
        ("EMAIL_SMTP_PORT", "abc"),
        ("EMAIL_SMTP_TLS_MODE", "plaintext"),
        ("EMAIL_SMTP_ALLOWED_RECIPIENTS", "*"),
        ("EMAIL_SMTP_USERNAME", ""),
    ],
)
def test_public_configuration_still_rejects_invalid_public_settings(
    monkeypatch, key, value
):
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    monkeypatch.setenv(key, value)

    with pytest.raises(ValueError):
        EmailConfig.from_env(load_secret=False)


def test_transmitting_provider_refuses_a_configuration_without_the_secret(
    monkeypatch,
):
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    public = EmailConfig.from_env(load_secret=False)

    with pytest.raises(Exception, match="smtp_secret_not_loaded"):
        build_provider(public)
