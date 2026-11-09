"""Isolated, dependency-free LG HTTP mail spike (#171), never a mail provider."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import http.client
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

CASES = (
    "single",
    "unicode",
    "to_multiple",
    "cc",
    "cc_empty",
    "html",
    "subject_missing",
    "subject_empty",
    "body_missing",
    "body_empty",
    "to_missing",
    "to_empty",
    "invalid_recipient",
    "over_limit",
    "timeout",
)
NEGATIVE = frozenset(CASES[6:])
FORMATS = ("comma", "semicolon", "repeated", "json_array")
OUTCOMES = (
    "received",
    "not_received",
    "not_accepted",
    "unknown",
    "unexpected_delivery",
)
MAX_REQUEST = 128 * 1024
MAX_RESPONSE = 1024 * 1024
TEMPLATE = {
    "endpoint": "https://CHANGE-ME.invalid/SMTP",
    "openapi_url": "https://CHANGE-ME.invalid/openapi.json",
    "approved_internal_hosts": [],
    "approved_internal_domains": [],
    "approved_recipients": [],
    "to": [],
    "cc": [],
    "recipient_format": "comma",
    "authorization_confirmed": False,
    "headers_env": {},
    "ca_file": None,
    "client_cert_file": None,
    "client_key_file": None,
    "use_system_proxy": False,
    "allow_http": False,
    "timeout_seconds": 15,
    "short_timeout_seconds": 1,
    "known_body_limit_bytes": None,
}


class PocError(ValueError):
    """Only constant, public error codes may be used as messages."""


def require(condition, code="configuration_invalid"):
    if not condition:
        raise PocError(code)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_private(path, value):
    raw = json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n"
    write_private_bytes(path, raw.encode())


def write_private_bytes(path, raw):
    # Exclusive creation: never replace an attempt or its reconciliation.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def bounded_number(value, minimum, maximum):
    return type(value) in (int, float) and minimum <= value <= maximum


def checked_url(value, config):
    require(isinstance(value, str) and not re.search(r"[\s\x00-\x1f]", value))
    url = urllib.parse.urlsplit(value)
    require(url.scheme in ("http", "https") and bool(url.hostname))
    require(
        not url.username and not url.password and not url.query and not url.fragment
    )
    require(url.hostname.lower() in config["approved_internal_hosts"])
    require(url.scheme == "https" or config["allow_http"] is True, "https_required")
    return url


def load_config(workspace):
    config = read_json(workspace / "config.json")
    require(set(config) == set(TEMPLATE))
    for key in ("authorization_confirmed", "allow_http", "use_system_proxy"):
        require(type(config[key]) is bool)
    require(config["authorization_confirmed"], "authorization_not_confirmed")
    for key in ("approved_internal_hosts", "approved_internal_domains"):
        require(isinstance(config[key], list) and bool(config[key]))
        require(all(isinstance(x, str) and x == x.lower() and x for x in config[key]))
        require(not any(x.endswith(".invalid") for x in config[key]))
    endpoint = checked_url(config["endpoint"], config)
    specification = checked_url(config["openapi_url"], config)
    require(endpoint.path.endswith("/SMTP"), "endpoint_path_must_end_in_smtp")
    require(
        (endpoint.scheme, endpoint.hostname, endpoint.port)
        == (specification.scheme, specification.hostname, specification.port),
        "specification_origin_mismatch",
    )
    for key in ("approved_recipients", "to", "cc"):
        require(isinstance(config[key], list))
        require(len(config[key]) <= 10)
        for address in config[key]:
            require(isinstance(address, str))
            require(
                re.fullmatch(
                    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+", address
                )
            )
            domain = address.rsplit("@", 1)[1].lower()
            require(domain in config["approved_internal_domains"])
            require(address in config["approved_recipients"])
    require(bool(config["to"]), "recipient_required")
    require(config["recipient_format"] in FORMATS)
    require(bounded_number(config["timeout_seconds"], 1, 120))
    require(bounded_number(config["short_timeout_seconds"], 0.1, 5))
    limit = config["known_body_limit_bytes"]
    require(limit is None or (type(limit) is int and 1 <= limit <= 65536))
    require(isinstance(config["headers_env"], dict))
    for header, env_name in config["headers_env"].items():
        require(re.fullmatch(r"[A-Za-z0-9-]+", header) is not None)
        require(
            header.lower()
            not in {
                "host",
                "content-type",
                "content-length",
                "transfer-encoding",
                "connection",
                "proxy-authorization",
                "accept-encoding",
            }
        )
        require(isinstance(env_name, str) and bool(env_name))
        value = os.environ.get(env_name, "")
        require(
            bool(value) and not re.search(r"[\r\n\x00]", value),
            "credential_unavailable",
        )
    for key in ("ca_file", "client_cert_file", "client_key_file"):
        require(config[key] is None or isinstance(config[key], str))
    require(not config["client_key_file"] or config["client_cert_file"])
    return config


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_request(config, request, timeout):
    context = ssl.create_default_context(cafile=config["ca_file"])
    if config["client_cert_file"]:
        context.load_cert_chain(config["client_cert_file"], config["client_key_file"])
    proxy = (
        urllib.request.ProxyHandler()
        if config["use_system_proxy"]
        else (urllib.request.ProxyHandler({}))
    )
    opener = urllib.request.build_opener(
        proxy,
        NoRedirect(),
        urllib.request.HTTPSHandler(context=context),
    )
    for header, env_name in config["headers_env"].items():
        request.add_header(header, os.environ[env_name])
    # urllib performs no application retry; redirects are explicitly disabled.
    return opener.open(request, timeout=timeout)


def capture_spec(workspace, config, *, local_file=None, allow_network=False):
    target = workspace / "specification.json"
    require(not target.exists(), "specification_already_recorded")
    if local_file:
        with Path(local_file).open("rb") as stream:
            raw = stream.read(8 * MAX_RESPONSE + 1)
    else:
        require(allow_network, "network_opt_in_required")
        request = urllib.request.Request(config["openapi_url"], method="GET")
        with open_request(config, request, config["timeout_seconds"]) as response:
            raw = response.read(8 * MAX_RESPONSE + 1)
    require(len(raw) <= 8 * MAX_RESPONSE, "specification_too_large")
    # JSON export only; never resolve references or OpenAPI servers automatically.
    spec = json.loads(raw)
    operation = spec.get("paths", {}).get("/SMTP", {}).get("post", {})
    multipart = "multipart/form-data" in operation.get("requestBody", {}).get(
        "content", {}
    ) or "multipart/form-data" in operation.get("consumes", spec.get("consumes", []))
    require(bool(operation) and multipart, "specification_contract_not_found")
    digest = hashlib.sha256(raw).hexdigest()
    write_private_bytes(workspace / "openapi-private.json", raw)
    write_private(target, {"sha256": digest, "bytes": len(raw)})
    return {"status": "specification_recorded", "sha256": digest}


def recipient_parts(name, addresses, style):
    if style == "repeated":
        return [(name, address) for address in addresses]
    value = (
        json.dumps(addresses)
        if style == "json_array"
        else (("," if style == "comma" else ";").join(addresses))
    )
    return [(name, value)]


def build_message(config, case, marker):
    require(case in CASES)
    to = config["to"] if case == "to_multiple" else config["to"][:1]
    require(case != "to_multiple" or len(set(to)) >= 2, "multiple_recipients_required")
    fields = [
        ("Subject", f"SYNERGIA POC {marker}"),
        ("Body", f"Synthetic POC {marker}"),
    ]
    if case == "unicode":
        fields = [
            ("Subject", f"Validação — ação 日本語 {marker}"),
            ("Body", f"Conteúdo sintético: ação, café, 日本語.\nLinha 2.\n{marker}"),
        ]
    if case == "html":
        fields[1] = ("Body", f"<p>Synthetic POC <strong>{marker}</strong></p>")
    fields += recipient_parts("To", to, config["recipient_format"])
    if case == "cc":
        require(bool(config["cc"]), "cc_recipient_required")
        fields += recipient_parts("CC", config["cc"], config["recipient_format"])
    if case == "cc_empty":
        fields.append(("CC", ""))
    for prefix, field in (("subject", "Subject"), ("body", "Body"), ("to", "To")):
        if case == f"{prefix}_missing":
            fields = [(k, v) for k, v in fields if k != field]
        if case == f"{prefix}_empty":
            fields = [(k, v) for k, v in fields if k != field] + [(field, "")]
    if case == "invalid_recipient":
        fields = [(k, v) for k, v in fields if k != "To"] + [
            ("To", "invalid@@invalid.invalid")
        ]
    if case == "over_limit":
        limit = config["known_body_limit_bytes"]
        require(limit is not None, "known_limit_required")
        fields = [(k, "X" * (limit + 1) if k == "Body" else v) for k, v in fields]
    boundary = f"synergia-{uuid4().hex}"
    body = b""
    for name, value in fields:
        body += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
            f"\r\n\r\n{value}\r\n"
        ).encode()
    body += f"--{boundary}--\r\n".encode("ascii")
    require(len(body) <= MAX_REQUEST, "request_budget_exceeded")
    logical = [{"field": name, "empty": not value} for name, value in fields]
    return body, f"multipart/form-data; boundary={boundary}", logical


def ensure_previous_resolved(workspace):
    for path in workspace.glob("attempt-*.json"):
        case = path.stem.removeprefix("attempt-")
        reconciliation = workspace / f"receipt-{case}.json"
        require(reconciliation.exists(), "previous_attempt_unresolved")
        result = read_json(reconciliation)
        require(
            result["outcome"] in {"received", "not_accepted"},
            "previous_attempt_unresolved_or_unexpected",
        )
        require(
            result["outcome"] != "not_accepted" or result["source"] == "corporate_log"
        )


def response_class(code):
    if 200 <= code < 300:
        return "http_accepted_unconfirmed"
    if 300 <= code < 400:
        return "redirect_blocked"
    if 400 <= code < 500:
        return "http_client_error"
    return "http_server_or_other_error"


@contextlib.contextmanager
def send_lock(workspace):
    path = workspace / "send.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise PocError("send_in_progress_or_stale_lock") from None
    try:
        os.close(fd)
        yield
    finally:
        path.unlink()


def probe(workspace, config, case, *, send=False, approved_negative=False):
    if send:
        with send_lock(workspace):
            return _probe(
                workspace, config, case, send=True, approved_negative=approved_negative
            )
    return _probe(workspace, config, case)


def _probe(workspace, config, case, *, send=False, approved_negative=False):
    marker = str(uuid4())
    body, content_type, logical = build_message(config, case, marker)
    timeout = (
        config["short_timeout_seconds"]
        if case == "timeout"
        else (config["timeout_seconds"])
    )
    if not send:
        return {
            "status": "dry_run_no_network",
            "case": case,
            "fields": logical,
            "request_bytes": len(body),
            "timeout_seconds": timeout,
        }
    require(case not in NEGATIVE or approved_negative, "negative_case_opt_in_required")
    require((workspace / "specification.json").is_file(), "specification_required")
    ensure_previous_resolved(workspace)
    require(not (workspace / f"result-{case}.json").exists(), "case_already_attempted")
    spec = read_json(workspace / "specification.json")
    attempt = {
        "case": case,
        "marker": marker,
        "started_at": datetime.now(UTC).isoformat(),
        "specification_sha256": spec["sha256"],
        "fields": logical,
        "request_bytes": len(body),
        "timeout_seconds": timeout,
        "recipient_format": config["recipient_format"],
        "authorization": ("headers" if config["headers_env"] else "network_only")
        + ("_mtls" if config["client_cert_file"] else ""),
    }
    request = urllib.request.Request(
        config["endpoint"],
        data=body,
        method="POST",
        headers={"Content-Type": content_type},
    )
    # Persist intent before any I/O: a crash must not permit a second send.
    write_private(workspace / f"attempt-{case}.json", attempt)
    started = time.monotonic()
    code, classification = None, "transport_uncertain"
    try:
        try:
            response = open_request(config, request, timeout)
        except urllib.error.HTTPError as error:
            response = error  # Includes 3xx: no second request is made.
        with response:
            code = response.code
            classification = response_class(code)
            raw = response.read(MAX_RESPONSE + 1)
            write_private(
                workspace / f"response-private-{case}.json",
                {
                    "headers": list(response.headers.items()),
                    "body_hex": raw[:MAX_RESPONSE].hex(),
                    "truncated": len(raw) > MAX_RESPONSE,
                },
            )
    except (OSError, urllib.error.URLError, http.client.HTTPException) as error:
        if isinstance(error, TimeoutError) or isinstance(
            getattr(error, "reason", None), TimeoutError
        ):
            classification = "timeout_uncertain"
        else:
            classification = "transport_uncertain"
    result = {
        "http_status": code,
        "classification": classification,
        "duration_ms": round((time.monotonic() - started) * 1000),
        "receipt": "unconfirmed",
        "automatic_retries": 0,
    }
    write_private(workspace / f"result-{case}.json", result)
    return {"status": "attempt_recorded", "case": case, "marker": marker, **result}


def reconcile(workspace, case, outcome, source):
    require((workspace / f"attempt-{case}.json").is_file(), "attempt_required")
    require(outcome in OUTCOMES and source in ("recipient", "corporate_log"))
    require(
        outcome != "not_accepted" or source == "corporate_log",
        "not_accepted_requires_corporate_log",
    )
    write_private(
        workspace / f"receipt-{case}.json",
        {
            "outcome": outcome,
            "source": source,
            "recorded_at": datetime.now(UTC).isoformat(),
        },
    )
    return {"status": "reconciliation_recorded", "case": case, "outcome": outcome}


def export_report(workspace):
    # Rebuild an allowlisted report; never copy config, response, arbitrary keys/text.
    spec = read_json(workspace / "specification.json")
    require(re.fullmatch(r"[0-9a-f]{64}", spec["sha256"]) is not None)
    rows = []
    for case in CASES:
        path = workspace / f"attempt-{case}.json"
        row = {"case": case, "execution": "not_executed"}
        if path.exists():
            attempt = read_json(path)
            require(attempt["case"] == case)
            require(str(UUID(attempt["marker"])) == attempt["marker"])
            instant = datetime.fromisoformat(attempt["started_at"])
            require(instant.tzinfo is not None)
            require(attempt["specification_sha256"] == spec["sha256"])
            require(bounded_number(attempt["timeout_seconds"], 0.1, 120))
            require(
                type(attempt["request_bytes"]) is int
                and 0 < attempt["request_bytes"] <= MAX_REQUEST
            )
            require(attempt["recipient_format"] in FORMATS)
            require(
                attempt["authorization"]
                in {
                    "headers",
                    "network_only",
                    "headers_mtls",
                    "network_only_mtls",
                }
            )
            fields = attempt["fields"]
            require(isinstance(fields, list) and len(fields) <= 24)
            for field in fields:
                require(field["field"] in {"Subject", "Body", "To", "CC"})
                require(type(field["empty"]) is bool)
            row.update(
                {
                    "execution": "attempted",
                    "marker": str(UUID(attempt["marker"])),
                    "started_at": instant.isoformat(),
                    "timeout_seconds": attempt["timeout_seconds"],
                    "request_bytes": attempt["request_bytes"],
                    "recipient_format": attempt["recipient_format"],
                    "authorization": attempt["authorization"],
                    "fields": [
                        {"field": f["field"], "empty": f["empty"]} for f in fields
                    ],
                    "classification": "interrupted_uncertain",
                    "receipt": "unknown",
                }
            )
            result_path = workspace / f"result-{case}.json"
            if result_path.exists():
                result = read_json(result_path)
                require(
                    result["classification"]
                    in {
                        "http_accepted_unconfirmed",
                        "redirect_blocked",
                        "http_client_error",
                        "http_server_or_other_error",
                        "transport_uncertain",
                        "timeout_uncertain",
                    }
                )
                code = result["http_status"]
                require(code is None or (type(code) is int and 100 <= code <= 599))
                require(
                    type(result["duration_ms"]) is int and result["duration_ms"] >= 0
                )
                row.update(
                    {
                        "http_status": code,
                        "classification": result["classification"],
                        "duration_ms": result["duration_ms"],
                        "automatic_retries": 0,
                    }
                )
            receipt_path = workspace / f"receipt-{case}.json"
            if receipt_path.exists():
                receipt = read_json(receipt_path)
                require(receipt["outcome"] in OUTCOMES)
                require(receipt["source"] in {"recipient", "corporate_log"})
                row.update(
                    {"receipt": receipt["outcome"], "receipt_source": receipt["source"]}
                )
        rows.append(row)
    report = {
        "issue": 171,
        "environment": "internal_validation",
        "specification_sha256": spec["sha256"],
        "cases": rows,
        "decision": "pending_human_review",
        "issue_170": "blocked_pending_contract",
    }
    write_private(workspace / f"sanitized-report-{uuid4().hex}.json", report)
    return {"status": "sanitized_report_created", "decision": report["decision"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("check")
    spec = sub.add_parser("spec")
    spec.add_argument("--file", type=Path)
    spec.add_argument("--allow-network", action="store_true")
    run = sub.add_parser("probe")
    run.add_argument("--case", choices=CASES, required=True)
    run.add_argument("--send", action="store_true")
    run.add_argument("--allow-real-send", action="store_true")
    run.add_argument("--approved-negative-case", action="store_true")
    receipt = sub.add_parser("reconcile")
    receipt.add_argument("--case", choices=CASES, required=True)
    receipt.add_argument("--outcome", choices=OUTCOMES, required=True)
    receipt.add_argument(
        "--source", choices=("recipient", "corporate_log"), required=True
    )
    sub.add_parser("export")
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    try:
        if args.command == "init":
            workspace.mkdir(mode=0o700, parents=True, exist_ok=False)
            write_private(workspace / "config.json", TEMPLATE)
            result = {"status": "private_workspace_initialized"}
        elif args.command in {"reconcile", "export"}:
            result = (
                reconcile(workspace, args.case, args.outcome, args.source)
                if (args.command == "reconcile")
                else export_report(workspace)
            )
        else:
            config = load_config(workspace)
            if args.command == "check":
                # Validate CA/client identity before any network operation.
                context = ssl.create_default_context(cafile=config["ca_file"])
                if config["client_cert_file"]:
                    context.load_cert_chain(
                        config["client_cert_file"], config["client_key_file"]
                    )
                result = {"status": "configuration_valid_no_network"}
            elif args.command == "spec":
                result = capture_spec(
                    workspace,
                    config,
                    local_file=args.file,
                    allow_network=args.allow_network,
                )
            else:
                require(args.send == args.allow_real_send, "both_send_flags_required")
                result = probe(
                    workspace,
                    config,
                    args.case,
                    send=args.send,
                    approved_negative=args.approved_negative_case,
                )
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        if args.command == "probe" and result.get("status") == "attempt_recorded":
            return 0 if result["classification"] == "http_accepted_unconfirmed" else 1
        return 0
    except PocError as error:
        print(json.dumps({"error_code": str(error)}))
        return 2
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        urllib.error.URLError,
        http.client.HTTPException,
    ):
        # External input/errors may contain credentials, URLs or response bodies.
        print(json.dumps({"error_code": "local_configuration_or_operation_failed"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
