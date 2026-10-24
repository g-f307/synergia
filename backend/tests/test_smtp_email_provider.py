from __future__ import annotations

import logging
import smtplib
import socket
import ssl
import traceback
from dataclasses import replace
from email import policy
from email.parser import BytesParser
from io import BytesIO
from uuid import uuid4

import pytest

from app.email_config import SMTPConfig
from app.email_contracts import (
    ConfigurationEmailError,
    EmailMessage,
    PermanentEmailError,
    TemporaryEmailError,
    UncertainEmailError,
)
from app.smtp_email_provider import SMTPEmailProvider, compose_smtp_message

SENSITIVE = "SYNTHETIC-PRIVATE-SMTP-RESPONSE-143"
SENDER = "sender@example.invalid"
RECIPIENT = "recipient@example.invalid"


def configuration(**overrides):
    return replace(
        SMTPConfig(
            host="smtp.example.invalid",
            sender=SENDER,
            allowed_recipients=frozenset({RECIPIENT}),
            username="synthetic-user",
            password="synthetic-secret-143",
        ),
        **overrides,
    )


def message(**overrides):
    return replace(
        EmailMessage(
            uuid4(),
            RECIPIENT,
            SENDER,
            "Execução sintética",
            "Duas pendências.\nSegunda linha.",
            "pt-BR",
            uuid4(),
        ),
        **overrides,
    )


class ScriptedSMTP:
    """Controlled server replies; deliberately offers no deduplication."""

    def __init__(self, owner, kind, options):
        self.owner, self.kind, self.options = owner, kind, options
        self.events = []
        self.payload = None
        self.secure = kind == "implicit"
        self.closed = False
        self._host = ""
        self.ehlo_count = 0

    def event(self, name, default=None):
        self.events.append(name)
        fault = self.owner.faults.get(name, default)
        if isinstance(fault, Exception):
            raise fault
        return fault

    def set_debuglevel(self, level):
        assert level == 0
        self.event("debug_off")

    def connect(self, host, port):
        assert self._host == host == "smtp.example.invalid"
        assert port in {465, 587}
        return self.event("connect", (220, b"ready"))

    def ehlo(self):
        self.ehlo_count += 1
        return self.event(
            "ehlo" if self.ehlo_count == 1 else "ehlo_after_tls", (250, b"capabilities")
        )

    def starttls(self, *, context):
        assert self.kind == "starttls"
        self.owner.contexts.append(context)
        result = self.event("starttls", (220, b"ready for TLS"))
        if result[0] == 220:
            self.secure = True
        return result

    def login(self, username, password):
        assert self.secure
        assert username == "synthetic-user" and password == "synthetic-secret-143"
        return self.event("login", (235, b"authenticated"))

    def mail(self, sender):
        assert self.secure and sender == SENDER
        return self.event("mail", (250, b"sender accepted"))

    def rcpt(self, recipient):
        assert self.secure and recipient == RECIPIENT
        return self.event("rcpt", (250, b"recipient accepted"))

    def data(self, payload):
        assert self.secure
        self.payload = payload
        return self.event("data", (250, b"opaque remote queue identifier"))

    def quit(self):
        return self.event("quit", (221, b"closed"))

    def close(self):
        self.closed = True
        self.event("close")


class TransportScript:
    def __init__(self):
        self.faults = {}
        self.clients = []
        self.contexts = []

    def factory(self, kind, **options):
        assert "host" not in options
        assert options["local_hostname"] == "synergia.invalid"
        assert 0 < options["timeout"] <= 30
        if kind == "implicit":
            self.contexts.append(options["context"])
        client = ScriptedSMTP(self, kind, options)
        self.clients.append(client)
        return client


@pytest.fixture
def transport(monkeypatch):
    script = TransportScript()
    monkeypatch.setattr(smtplib, "SMTP", lambda **kw: script.factory("starttls", **kw))
    monkeypatch.setattr(
        smtplib, "SMTP_SSL", lambda **kw: script.factory("implicit", **kw)
    )

    def no_network(*args, **kwargs):
        raise AssertionError("External connections are forbidden in SMTP unit tests")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    return script


@pytest.mark.parametrize("mode,port", [("starttls", 587), ("implicit", 465)])
def test_tls_authentication_single_envelope_and_confirmed_reference(
    transport, mode, port
):
    item = message()
    reference = SMTPEmailProvider(configuration(tls_mode=mode, port=port)).send(item)
    assert reference == f"smtp-{item.delivery_id}"
    client = transport.clients[0]
    assert client.closed and client.events[-2:] == ["quit", "close"]
    assert (
        client.events.count("mail")
        == client.events.count("rcpt")
        == client.events.count("data")
        == 1
    )
    if mode == "starttls":
        assert (
            client.events.index("starttls")
            < client.events.index("ehlo_after_tls")
            < client.events.index("login")
        )
    else:
        assert "starttls" not in client.events
    for context in transport.contexts:
        assert context.check_hostname is True
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.minimum_version >= ssl.TLSVersion.TLSv1_2


@pytest.mark.parametrize("locale", ["pt-BR", "en-US"])
def test_mime_is_utf8_with_escaped_html_and_no_extra_recipients(locale):
    body = '<script>alert("texto")</script>\r\n<a href="javascript:bad">& texto</a>'
    item = message(body=body, locale=locale)
    sender, recipient, payload = compose_smtp_message(item, configuration())
    assert (sender, recipient) == (SENDER, RECIPIENT)
    payload.decode("ascii")  # encoded headers and bodies need no SMTPUTF8/8BITMIME
    parsed = BytesParser(policy=policy.default).parsebytes(payload)
    assert str(parsed["Subject"]) == item.subject
    assert str(parsed["Content-Language"]) == locale
    assert parsed["Date"] and parsed["Message-ID"]
    assert parsed["Cc"] is None and parsed["Bcc"] is None
    assert parsed.get_content_type() == "multipart/alternative"
    plain, escaped = list(parsed.iter_parts())
    assert plain.get_content_type() == "text/plain"
    assert escaped.get_content_type() == "text/html"
    assert plain.get_content().replace("\r\n", "\n").rstrip("\n") == body.replace(
        "\r\n", "\n"
    )
    html_body = escaped.get_content()
    assert "<script>" not in html_body and "<a href=" not in html_body
    assert "&lt;script&gt;" in html_body and "&amp; texto" in html_body
    assert "<br>" in html_body


def test_message_id_is_stable_but_transport_does_not_promise_deduplication(transport):
    provider = SMTPEmailProvider(configuration())
    item = message()
    assert provider.send(item) == provider.send(item)
    assert len(transport.clients) == 2
    identifiers = [
        BytesParser(policy=policy.default).parsebytes(c.payload)["Message-ID"]
        for c in transport.clients
    ]
    assert str(identifiers[0]) == str(identifiers[1])


@pytest.mark.parametrize(
    "overrides",
    [
        {"recipient": "blocked@example.invalid"},
        {"subject": "Safe\r\nBcc: attacker@example.invalid"},
        {"sender": "other@example.invalid"},
        {"body": "\x00PRIVATE"},
        {"locale": "pt-BR\r\nBcc: attacker@example.invalid"},
        {"delivery_id": "INVALID\r\n"},
    ],
)
def test_invalid_envelope_or_metadata_prevents_even_connection_creation(
    transport, overrides
):
    with pytest.raises(PermanentEmailError):
        SMTPEmailProvider(configuration()).send(message(**overrides))
    assert transport.clients == []


@pytest.mark.parametrize(
    "phase,fault,error_type,code",
    [
        (
            "connect",
            TimeoutError(SENSITIVE),
            TemporaryEmailError,
            "smtp_connection_unavailable",
        ),
        (
            "connect",
            (421, SENSITIVE.encode()),
            TemporaryEmailError,
            "smtp_connection_temporarily_unavailable",
        ),
        (
            "connect",
            (554, SENSITIVE.encode()),
            ConfigurationEmailError,
            "smtp_connection_rejected",
        ),
        (
            "ehlo",
            (550, SENSITIVE.encode()),
            ConfigurationEmailError,
            "smtp_greeting_rejected",
        ),
        (
            "ehlo",
            (-1, SENSITIVE.encode()),
            ConfigurationEmailError,
            "smtp_protocol_invalid",
        ),
        (
            "starttls",
            smtplib.SMTPNotSupportedError(SENSITIVE),
            ConfigurationEmailError,
            "smtp_capability_unavailable",
        ),
        (
            "starttls",
            ssl.SSLCertVerificationError(1, SENSITIVE),
            ConfigurationEmailError,
            "smtp_tls_certificate_invalid",
        ),
        (
            "starttls",
            ssl.SSLError(1, SENSITIVE),
            ConfigurationEmailError,
            "smtp_tls_negotiation_failed",
        ),
        (
            "starttls",
            smtplib.SMTPResponseException(454, SENSITIVE.encode()),
            TemporaryEmailError,
            "smtp_tls_temporarily_unavailable",
        ),
        (
            "ehlo_after_tls",
            (450, SENSITIVE.encode()),
            TemporaryEmailError,
            "smtp_greeting_temporarily_unavailable",
        ),
        (
            "login",
            smtplib.SMTPAuthenticationError(535, SENSITIVE.encode()),
            ConfigurationEmailError,
            "smtp_authentication_rejected",
        ),
        (
            "login",
            smtplib.SMTPAuthenticationError(454, SENSITIVE.encode()),
            TemporaryEmailError,
            "smtp_authentication_temporarily_unavailable",
        ),
        (
            "login",
            smtplib.SMTPNotSupportedError(SENSITIVE),
            ConfigurationEmailError,
            "smtp_capability_unavailable",
        ),
        (
            "mail",
            (450, SENSITIVE.encode()),
            TemporaryEmailError,
            "smtp_sender_temporarily_unavailable",
        ),
        (
            "mail",
            (550, SENSITIVE.encode()),
            ConfigurationEmailError,
            "smtp_sender_rejected",
        ),
        (
            "rcpt",
            (450, SENSITIVE.encode()),
            TemporaryEmailError,
            "smtp_recipient_temporarily_unavailable",
        ),
        (
            "rcpt",
            (550, SENSITIVE.encode()),
            PermanentEmailError,
            "smtp_recipient_rejected",
        ),
        (
            "data",
            smtplib.SMTPDataError(451, SENSITIVE.encode()),
            TemporaryEmailError,
            "smtp_data_command_temporarily_unavailable",
        ),
        (
            "data",
            smtplib.SMTPDataError(554, SENSITIVE.encode()),
            PermanentEmailError,
            "smtp_data_command_rejected",
        ),
        (
            "data",
            (451, SENSITIVE.encode()),
            TemporaryEmailError,
            "smtp_data_temporarily_unavailable",
        ),
        ("data", (552, SENSITIVE.encode()), PermanentEmailError, "smtp_data_rejected"),
        (
            "data",
            TimeoutError(SENSITIVE),
            UncertainEmailError,
            "smtp_confirmation_unknown",
        ),
        (
            "data",
            smtplib.SMTPServerDisconnected(SENSITIVE),
            UncertainEmailError,
            "smtp_confirmation_unknown",
        ),
        (
            "data",
            ssl.SSLError(1, SENSITIVE),
            UncertainEmailError,
            "smtp_confirmation_unknown",
        ),
        (
            "data",
            RuntimeError(SENSITIVE),
            UncertainEmailError,
            "smtp_confirmation_unknown",
        ),
        (
            "data",
            smtplib.SMTPNotSupportedError(SENSITIVE),
            UncertainEmailError,
            "smtp_confirmation_unknown",
        ),
        (
            "data",
            (354, SENSITIVE.encode()),
            UncertainEmailError,
            "smtp_confirmation_unknown",
        ),
        (
            "data",
            (-1, SENSITIVE.encode()),
            UncertainEmailError,
            "smtp_confirmation_unknown",
        ),
    ],
)
def test_delivery_outcomes_are_classified_by_acceptance_phase_without_leaks(
    transport,
    caplog,
    phase,
    fault,
    error_type,
    code,
):
    transport.faults[phase] = fault
    with caplog.at_level(logging.DEBUG), pytest.raises(error_type) as error:
        SMTPEmailProvider(configuration()).send(message())
    assert str(error.value) == code
    assert SENSITIVE not in caplog.text
    assert SENSITIVE not in "".join(traceback.format_exception(error.value))
    assert "synthetic-secret-143" not in caplog.text
    assert transport.clients[0].closed
    assert len(transport.clients) == 1
    if phase == "data":
        assert "quit" not in transport.clients[0].events
    else:
        assert transport.clients[0].payload is None


@pytest.mark.parametrize("phase", ["quit", "close"])
def test_cleanup_failure_does_not_reverse_confirmed_acceptance(transport, phase):
    transport.faults[phase] = smtplib.SMTPServerDisconnected(SENSITIVE)
    item = message()
    assert SMTPEmailProvider(configuration()).send(item) == f"smtp-{item.delivery_id}"
    assert transport.clients[0].closed
    assert transport.clients[0].events.count("data") == 1


def test_cleanup_does_not_mask_a_known_rejection(transport):
    transport.faults.update(
        rcpt=(550, SENSITIVE.encode()),
        quit=TimeoutError(SENSITIVE),
        close=OSError(SENSITIVE),
    )
    with pytest.raises(PermanentEmailError, match="smtp_recipient_rejected"):
        SMTPEmailProvider(configuration()).send(message())
    assert transport.clients[0].closed


def test_explicit_relay_mode_keeps_tls_without_sending_password(transport):
    config = configuration(auth_mode="none", username="", password="")
    SMTPEmailProvider(config).send(message())
    assert transport.clients[0].secure
    assert "login" not in transport.clients[0].events


def test_configured_socket_timeout_is_applied_to_connection(transport):
    SMTPEmailProvider(configuration(timeout_seconds=7.5)).send(message())
    assert transport.clients[0].options["timeout"] == 7.5


def test_authentication_port_can_be_replaced_without_changing_delivery_message(
    transport,
):
    class AlternativeAuthentication:
        def validate(self):
            assert transport.clients == []

        def authenticate(self, client):
            assert client.secure
            client.event("alternative_auth")

    SMTPEmailProvider(configuration(), authenticator=AlternativeAuthentication()).send(
        message()
    )
    assert "alternative_auth" in transport.clients[0].events
    assert "login" not in transport.clients[0].events


@pytest.mark.parametrize("field", ["username", "password"])
def test_default_password_auth_refuses_unsupported_encoding_before_network(
    transport, field
):
    with pytest.raises(ConfigurationEmailError, match="smtp_auth_encoding_unsupported"):
        SMTPEmailProvider(configuration(**{field: "usuário-sintético"})).send(message())
    assert transport.clients == []


@pytest.mark.parametrize("mode,port", [("starttls", 587), ("implicit", 465)])
def test_stdlib_transaction_uses_verified_hostname_and_tls_before_authentication(
    monkeypatch,
    mode,
    port,
):
    """Exercise real smtplib over in-memory sockets, without an external service."""
    frames = []
    contexts = []
    sockets = []

    class ScriptedSocket:
        def __init__(self, replies, secure):
            self.replies = BytesIO(replies)
            self.secure = secure
            self.closed = False
            sockets.append(self)

        def makefile(self, mode):
            assert mode == "rb"
            return self.replies

        def sendall(self, content):
            if content.upper().startswith((b"AUTH", b"MAIL", b"RCPT", b"DATA")):
                assert self.secure
            frames.append((self.secure, content))

        def close(self):
            self.closed = True

    def create_connection(address, timeout, source_address=None):
        assert address == ("smtp.example.invalid", port)
        assert timeout == 7.5
        assert source_address is None
        return ScriptedSocket(
            b"220 synthetic SMTP\r\n250-synthetic\r\n250 STARTTLS\r\n220 TLS ready\r\n",
            False,
        )

    def wrap_socket(context, sock, *, server_hostname):
        assert server_hostname == "smtp.example.invalid"
        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
        contexts.append(context)
        replies = b"220 synthetic SMTP\r\n" if mode == "implicit" else b""
        replies += (
            b"250-synthetic\r\n250 AUTH PLAIN\r\n235 authenticated\r\n"
            b"250 sender\r\n250 recipient\r\n354 send data\r\n"
            b"250 accepted\r\n221 goodbye\r\n"
        )
        # The real SSL wrapper owns the raw socket after wrapping.
        sock.close()
        return ScriptedSocket(replies, True)

    def no_dns(*args, **kwargs):
        raise AssertionError("DNS is forbidden in this controlled transaction")

    monkeypatch.setattr(socket, "create_connection", create_connection)
    monkeypatch.setattr(socket, "getaddrinfo", no_dns)
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", wrap_socket)
    item = message()
    reference = SMTPEmailProvider(
        configuration(tls_mode=mode, port=port, timeout_seconds=7.5)
    ).send(item)
    assert reference == f"smtp-{item.delivery_id}"
    assert len(contexts) == 1 and all(s.closed for s in sockets)
    assert sum(content.upper().startswith(b"EHLO") for _, content in frames) == (
        2 if mode == "starttls" else 1
    )
    assert sum(content.startswith(b"AUTH") for _, content in frames) == 1
    transmitted = next(content for _, content in frames if b"MIME-Version:" in content)
    assert b"synthetic-secret-143" not in transmitted
    assert transmitted.endswith(b"\r\n.\r\n")
