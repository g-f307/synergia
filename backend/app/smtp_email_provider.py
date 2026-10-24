"""SMTP transport only: MIME, verified TLS and classified acceptance outcomes."""

from __future__ import annotations

import html
import re
import smtplib
import ssl
from contextlib import suppress
from datetime import UTC, datetime
from email.message import EmailMessage as MIMEMessage
from email.policy import SMTP
from email.utils import format_datetime
from typing import Protocol
from uuid import UUID

from app.email_config import SMTPConfig
from app.email_contracts import (
    ConfigurationEmailError,
    EmailMessage,
    PermanentEmailError,
    TemporaryEmailError,
    UncertainEmailError,
)

SAFE_SMTP_FAILURE_CODES = frozenset(
    {
        "invalid_smtp_envelope",
        "invalid_smtp_subject",
        "invalid_smtp_body",
        "invalid_smtp_delivery_id",
        "invalid_smtp_locale",
        "smtp_sender_mismatch",
        "smtp_recipient_not_allowed",
        "smtp_auth_encoding_unsupported",
        "smtp_protocol_invalid",
        "smtp_confirmation_unknown",
        "smtp_tls_certificate_invalid",
        "smtp_capability_unavailable",
        "smtp_tls_negotiation_failed",
        "smtp_tls_configuration_invalid",
        "smtp_connection_unavailable",
        "smtp_transport_invalid",
        *(
            f"smtp_{phase}_{outcome}"
            for phase in (
                "connection",
                "greeting",
                "tls",
                "authentication",
                "sender",
                "recipient",
                "data",
                "data_command",
            )
            for outcome in ("rejected", "temporarily_unavailable")
        ),
    }
)


class SMTPAuthenticator(Protocol):
    """Authentication may evolve without changing templates or delivery use cases."""

    def validate(self) -> None: ...

    def authenticate(self, client: smtplib.SMTP) -> None: ...


class PasswordSMTPAuthenticator:
    def __init__(self, config: SMTPConfig) -> None:
        self.config = config

    def validate(self) -> None:
        # smtplib.login encodes its SASL responses as ASCII. A future OAuth or
        # internationalized authentication adapter can implement this port.
        if not self.config.username.isascii() or not self.config.password.isascii():
            raise ConfigurationEmailError("smtp_auth_encoding_unsupported")

    def authenticate(self, client: smtplib.SMTP) -> None:
        code, _ = client.login(self.config.username, self.config.password)
        _require_reply(code, {235, 503}, "authentication")


class RelaySMTPAuthenticator:
    """Explicit relay mode: TLS is still mandatory; no credentials are sent."""

    def validate(self) -> None:
        return None

    def authenticate(self, client: smtplib.SMTP) -> None:
        return None


def _require_reply(code: int, accepted: set[int], phase: str) -> None:
    if code in accepted:
        return
    if 400 <= code < 500:
        raise TemporaryEmailError(f"smtp_{phase}_temporarily_unavailable")
    if 500 <= code < 600:
        failure = (
            ConfigurationEmailError
            if phase in {"connection", "greeting", "tls", "authentication", "sender"}
            else PermanentEmailError
        )
        raise failure(f"smtp_{phase}_rejected")
    if phase == "data":
        raise UncertainEmailError("smtp_confirmation_unknown")
    raise ConfigurationEmailError("smtp_protocol_invalid")


def compose_smtp_message(
    message: EmailMessage, config: SMTPConfig
) -> tuple[str, str, bytes]:
    """Serialize entirely before connection; HTML is derived only from escaped text."""
    sender, recipient = config.validate_message(message)
    if not isinstance(message.delivery_id, UUID):
        raise PermanentEmailError("invalid_smtp_delivery_id")
    if (
        not isinstance(message.locale, str)
        or len(message.locale) > 128
        or not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", message.locale)
    ):
        raise PermanentEmailError("invalid_smtp_locale")
    content = MIMEMessage(policy=SMTP)
    content["From"] = sender
    content["To"] = recipient
    content["Subject"] = message.subject
    content["Message-ID"] = (
        f"<synergia.{message.delivery_id.hex}@{sender.split('@')[1]}>"
    )
    content["Date"] = format_datetime(datetime.now(UTC))
    body = message.body.replace("\r\n", "\n").replace("\r", "\n")
    escaped = html.escape(body, quote=True).replace("\n", "<br>\n")
    content.set_content(body, charset="utf-8", cte="quoted-printable")
    content.add_alternative(
        f"<!doctype html><html><body><div>{escaped}</div></body></html>",
        subtype="html",
        charset="utf-8",
        cte="quoted-printable",
    )
    content["Content-Language"] = message.locale
    return sender, recipient, content.as_bytes()


class SMTPEmailProvider:
    """One connection and one envelope recipient per delivery, without local retries.

    A successful DATA response confirms server acceptance, not inbox receipt.
    UUID-derived Message-ID/reference support correlation, not exactly-once SMTP.
    Queue activation and uncertain-result reconciliation belong to the worker.
    """

    name = "smtp"

    def __init__(
        self, config: SMTPConfig, *, authenticator: SMTPAuthenticator | None = None
    ):
        self.config = config
        self.authenticator = (
            authenticator
            if authenticator is not None
            else (
                PasswordSMTPAuthenticator(config)
                if config.auth_mode == "password"
                else RelaySMTPAuthenticator()
            )
        )

    def send(self, message: EmailMessage) -> str:
        client: smtplib.SMTP | None = None
        data_started = confirmed = False
        phase = "configuration"
        try:
            sender, recipient, payload = compose_smtp_message(message, self.config)
            self.authenticator.validate()
            context = ssl.create_default_context()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            phase = "connection"
            options = {
                "timeout": self.config.timeout_seconds,
                "local_hostname": "synergia.invalid",
            }
            # Create before connecting so every partial connection is closed.
            if self.config.tls_mode == "implicit":
                client = smtplib.SMTP_SSL(context=context, **options)
            else:
                client = smtplib.SMTP(**options)
            client.set_debuglevel(0)
            # smtplib.connect does not update _host. Its TLS implementation uses
            # this field for SNI and certificate hostname verification.
            client._host = self.config.host
            code, _ = client.connect(self.config.host, self.config.port)
            _require_reply(code, {220}, phase)
            phase = "greeting"
            code, _ = client.ehlo()
            _require_reply(code, {250}, phase)
            if self.config.tls_mode == "starttls":
                phase = "tls"
                code, _ = client.starttls(context=context)
                _require_reply(code, {220}, phase)
                phase = "greeting"
                code, _ = client.ehlo()
                _require_reply(code, {250}, phase)
            phase = "authentication"
            self.authenticator.authenticate(client)
            phase = "sender"
            code, _ = client.mail(sender)
            _require_reply(code, {250}, phase)
            phase = "recipient"
            code, _ = client.rcpt(recipient)
            _require_reply(code, {250, 251}, phase)
            phase = "data"
            data_started = True
            code, _ = client.data(payload)
            _require_reply(code, {250}, phase)
            confirmed = True
            return f"smtp-{message.delivery_id}"
        except (
            ConfigurationEmailError,
            PermanentEmailError,
            TemporaryEmailError,
            UncertainEmailError,
        ):
            raise
        except ssl.SSLCertVerificationError:
            if data_started:
                raise UncertainEmailError("smtp_confirmation_unknown") from None
            raise ConfigurationEmailError("smtp_tls_certificate_invalid") from None
        except smtplib.SMTPResponseException as error:
            # smtplib.data raises SMTPDataError only for refusal of the DATA
            # command before body transmission. Final refusal is a return code.
            response_phase = (
                "data_command" if isinstance(error, smtplib.SMTPDataError) else phase
            )
            try:
                _require_reply(error.smtp_code, set(), response_phase)
            except (
                ConfigurationEmailError,
                PermanentEmailError,
                TemporaryEmailError,
                UncertainEmailError,
            ) as classified:
                raise classified from None
            raise AssertionError("unreachable") from None
        except smtplib.SMTPNotSupportedError:
            if data_started:
                raise UncertainEmailError("smtp_confirmation_unknown") from None
            raise ConfigurationEmailError("smtp_capability_unavailable") from None
        except ssl.SSLError:
            if data_started:
                raise UncertainEmailError("smtp_confirmation_unknown") from None
            raise ConfigurationEmailError("smtp_tls_negotiation_failed") from None
        except (OSError, smtplib.SMTPServerDisconnected):
            if data_started:
                raise UncertainEmailError("smtp_confirmation_unknown") from None
            if phase == "configuration":
                raise ConfigurationEmailError(
                    "smtp_tls_configuration_invalid"
                ) from None
            raise TemporaryEmailError("smtp_connection_unavailable") from None
        except Exception:
            if data_started:
                raise UncertainEmailError("smtp_confirmation_unknown") from None
            raise ConfigurationEmailError("smtp_transport_invalid") from None
        finally:
            if client is not None:
                # After uncertain DATA, close immediately: never send more bytes
                # into a possibly unfinished message. QUIT errors after a 250
                # must not turn confirmed acceptance into an automatic resend.
                if not data_started or confirmed:
                    with suppress(Exception):
                        client.quit()
                with suppress(Exception):
                    client.close()
