"""Closed GELF fields, opt-in, TLS and HTTP ambiguity without corporate access."""

from __future__ import annotations

import io
import json
import os
import ssl
import subprocess
import sys
import urllib.error
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID

import pytest
import yaml

from app.graylog import (
    GelfTransport,
    GraylogConfig,
    GraylogError,
    NoRedirect,
    stable_id,
    to_gelf,
)

ROOT = Path(__file__).resolve().parents[2]
ORG = UUID("44444444-4444-4444-8444-444444444444")


@pytest.fixture
def config():
    return GraylogConfig(
        endpoint="https://graylog.example.invalid/gelf",
        environment="test",
        application_version="synthetic-v1",
        enabled=True,
        authorization_confirmed=True,
        include_global_events=True,
        organization_ids=(ORG,),
        headers={"Authorization": "synthetic-input-secret"},
    )


@pytest.fixture
def event():
    return {
        "id": "identity:41",
        "occurred_at": datetime(2026, 11, 6, tzinfo=UTC),
        "organization_id": ORG,
        "actor_id": ORG,
        "actor_type": "user",
        "action": "auth.login_failed",
        "resource_type": "credential",
        "resource_id": "refresh_token_value",
        "outcome": "failure",
        "correlation_id": ORG,
        "metadata": {},
        "origin": "identity_access_events",
    }


def test_mapping_keeps_stable_id_utc_and_default_privacy(config, event):
    result = to_gelf(event, config)
    assert result["version"] == "1.1"
    assert result["timestamp"] == event["occurred_at"].timestamp()
    assert result["_event_id"] == stable_id(
        event["origin"], event["id"], event["occurred_at"]
    )
    assert "_id" not in result
    assert "_actor_id" not in result and "_resource_id" not in result
    assert result["_correlation_id"] == str(ORG)
    assert result["short_message"] == "auth.login_failed"
    assert result["level"] == 4
    assert (
        stable_id(event["origin"], "identity:42", event["occurred_at"])
        != result["_event_id"]
    )


@pytest.mark.parametrize(
    "forbidden",
    [
        "token",
        "credentials",
        "cookie",
        "prompt",
        "response",
        "cells",
        "files",
        "stack_trace",
        "private_config",
        "full_message",
        "streams",
        "index",
    ],
)
def test_nested_forbidden_content_never_enters_projection(config, event, forbidden):
    event["metadata"] = {
        forbidden: {"nested": ["private-value"]},
        "duration_ms": {forbidden: "private-value"},
        "from_state": "private-value",
        "version": "private-value",
        "model": "private-value",
        "model_digest": {forbidden: "private-value"},
    }
    event[forbidden] = ["private-value"]
    text = json.dumps(to_gelf(event, config))
    assert "private-value" not in text


def test_event_identity_survives_timezone_serialization_and_sequence_reuse(event):
    origin, key, when = event["origin"], event["id"], event["occurred_at"]
    assert stable_id(origin, key, when) == stable_id(
        origin, key, "2026-11-05T20:00:00-04:00"
    )
    assert stable_id(origin, key, when) != stable_id(
        origin, key, when + timedelta(seconds=1)
    )
    with pytest.raises(GraylogError, match="event_timezone_required"):
        stable_id(origin, key, datetime(2026, 11, 6))


def test_approved_metadata_retains_only_typed_values(config, event):
    event["metadata"] = {
        "duration_ms": 15,
        "version": True,
        "state_version": -1,
        "from_state": "queued",
        "to_state": ["queued"],
    }
    result = to_gelf(event, config)
    assert result["_meta_duration_ms"] == 15
    assert result["_meta_from_state"] == "queued"
    assert "_meta_version" not in result and "_meta_state_version" not in result


def test_gelf_boolean_metadata_is_numeric_and_all_additional_values_are_portable(
    config, event
):
    event["metadata"] = {"consent": True, "is_active": False, "fallback": True}
    result = to_gelf(event, config)
    assert result["_meta_consent"] == 1 and result["_meta_is_active"] == 0
    assert type(result["_meta_fallback"]) is int
    assert all(
        type(value) in {str, int, float}
        for key, value in result.items()
        if key.startswith("_")
    )


def test_personal_identifiers_need_approval_and_sensitive_resources_stay_redacted(
    config, event
):
    result = to_gelf(
        event, replace(config, include_actor_id=True, include_resource_id=True)
    )
    assert result["_actor_id"] == str(ORG)
    assert result["_resource_id"] == "[redacted]"


def test_organization_and_global_scopes_are_independent(config, event):
    with pytest.raises(GraylogError, match="scope_not_approved"):
        to_gelf(event, replace(config, organization_ids=()))
    event["organization_id"] = None
    with pytest.raises(GraylogError, match="scope_not_approved"):
        to_gelf(event, replace(config, include_global_events=False))


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://graylog.example.invalid/gelf",
        "https://user:pass@example.invalid/gelf",
        "https://example.invalid/gelf?token=value",
        "https://example.invalid/gelf#secret",
        "https://example.invalid:99999/gelf",
        "https://example.invalid/other",
        "https://example.invalid/gelf\n",
        "file:///gelf",
    ],
)
def test_destination_cannot_bypass_tls_or_contain_credentials(config, endpoint):
    with pytest.raises((GraylogError, ValueError)):
        replace(config, endpoint=endpoint)


@pytest.mark.parametrize(
    "changes",
    [
        {"authorization_confirmed": False},
        {"headers": {}},
        {"enabled": "false"},
        {"timeout_seconds": 31},
        {"batch_size": 0},
        {"max_attempts": True},
        {"retryable_statuses": (200,)},
        {"headers": {"Host": "evil"}},
        {"headers": {"Authorization": "secret\nInjected: true"}},
        {"host": "person@example.invalid"},
        {"client_cert_file": "client.pem"},
    ],
)
def test_invalid_contract_is_rejected_before_network(config, changes):
    with pytest.raises(GraylogError):
        replace(config, **changes)


def test_destination_and_policy_are_bound_but_credentials_can_rotate(config):
    assert (
        config.destination_hash()
        == replace(
            config,
            headers={"Authorization": "rotated"},
            application_version="v2",
        ).destination_hash()
    )
    assert (
        config.destination_hash()
        != replace(config, include_actor_id=True).destination_hash()
    )


@pytest.mark.parametrize(
    "status,state",
    [
        (202, "accepted"),
        (200, "uncertain"),
        (204, "uncertain"),
        (500, "uncertain"),
        (503, "uncertain"),
        (429, "blocked"),
        (302, "blocked"),
        (401, "blocked"),
    ],
)
def test_http_acceptance_is_distinct_from_unexpected_or_refused(config, status, state):
    transport = GelfTransport(config)
    transport.opener = Mock()
    transport.opener.open.side_effect = urllib.error.HTTPError(
        config.endpoint,
        status,
        "private-response",
        {},
        io.BytesIO(b"private-body"),
    )
    result = transport.send({"version": "1.1"})
    assert result.state == state
    assert "private" not in repr(result)
    assert transport.opener.open.call_count == 1


def test_automatic_retry_requires_explicit_no_acceptance_contract(config):
    transport = GelfTransport(replace(config, retryable_statuses=(429, 503)))
    transport.opener = Mock()
    transport.opener.open.side_effect = urllib.error.HTTPError(
        config.endpoint,
        503,
        "private",
        {},
        io.BytesIO(),
    )
    assert transport.send({}).state == "pending"


@pytest.mark.parametrize(
    "error",
    [TimeoutError("secret"), OSError("secret"), urllib.error.URLError("secret")],
)
def test_network_failures_are_uncertain_without_automatic_retry(config, error):
    transport = GelfTransport(config)
    transport.opener = Mock()
    transport.opener.open.side_effect = error
    result = transport.send({})
    assert (result.state, result.code) == ("uncertain", "network_result_unknown")
    assert transport.opener.open.call_count == 1


def test_tls_context_verifies_hostname_and_disables_proxies(config, monkeypatch):
    build = Mock()
    monkeypatch.setattr("urllib.request.build_opener", build)
    GelfTransport(config)
    handlers = build.call_args.args
    assert handlers[0].proxies == {}
    context = handlers[-1]._context
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    assert (
        NoRedirect().redirect_request(
            None, None, 302, None, None, "https://evil.invalid"
        )
        is None
    )


def test_config_is_private_bounded_and_unknown_keys_fail(config, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "endpoint": config.endpoint,
                "environment": "test",
                "application_version": "v1",
                "surprise": "secret",
            }
        )
    )
    path.chmod(0o600)
    with pytest.raises(GraylogError, match="configuration_invalid"):
        GraylogConfig.load(path)
    path.write_text("[]")
    with pytest.raises(GraylogError):
        GraylogConfig.load(path)


def test_collector_credentials_mount_only_on_opt_in_worker():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    worker = compose["services"]["graylog-worker"]
    assert worker["profiles"] == ["graylog"]
    assert worker["restart"] == "no"
    assert worker["volumes"][0]["read_only"]
    for name, service in compose["services"].items():
        if name != "graylog-worker":
            assert "GRAYLOG_CONFIG_DIR" not in json.dumps(service)


def test_cli_init_check_and_disabled_run_need_no_database_or_network(tmp_path):
    path = tmp_path / "config.json"
    script = str(ROOT / "scripts/process_graylog.py")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DATABASE_URL", "SYNERGIA_BUILD_REVISION"}
    }
    for args, status in [
        (["init", "--output", str(path)], "template_created_disabled"),
        (["--config", str(path), "check"], "configuration_valid_no_network"),
        (["--config", str(path), "run"], "disabled"),
    ]:
        process = subprocess.run(
            [sys.executable, script, *args],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(process.stdout)["status"] == status
        assert process.stderr == ""


def test_cli_error_does_not_print_private_configuration(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"secret": "must-not-appear"}')
    path.chmod(0o600)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/process_graylog.py"),
            "--config",
            str(path),
            "check",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "must-not-appear" not in result.stdout + result.stderr
    assert json.loads(result.stdout)["error_code"] == "configuration_invalid"
