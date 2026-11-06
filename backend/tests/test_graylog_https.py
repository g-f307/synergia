"""Actual HTTPS on loopback: verified CA/name, header, acceptance and redirect."""

from __future__ import annotations

import json
import shutil
import ssl
import subprocess
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.graylog import GelfTransport, GraylogConfig


@pytest.fixture(scope="module")
def receiver(tmp_path_factory):
    if shutil.which("openssl") is None:
        pytest.skip("openssl is required to create ephemeral TLS test certificates")
    root = tmp_path_factory.mktemp("graylog-tls")
    cert, key = root / "server.pem", root / "server.key"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
    )
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, self.headers.get("X-Input-Key"), body))
            self.send_response(self.server.response_code)
            if self.server.response_code == 302:
                self.send_header(
                    "Location", "https://must-not-contact.example.invalid/gelf"
                )
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server.response_code = 202
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, requests, cert
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def config(receiver):
    server, _, certificate = receiver
    return GraylogConfig(
        endpoint=f"https://localhost:{server.server_port}/gelf",
        environment="test",
        application_version="synthetic-v1",
        enabled=True,
        authorization_confirmed=True,
        include_global_events=True,
        headers={"X-Input-Key": "synthetic-local-input"},
        ca_file=str(certificate),
    )


def test_actual_https_request_is_accepted_and_authenticated(receiver):
    server, requests, _ = receiver
    server.response_code = 202
    payload = {"version": "1.1", "host": "synergia", "short_message": "synthetic.test"}
    result = GelfTransport(config(receiver)).send(payload)
    assert (result.state, result.code) == ("accepted", "http_202")
    assert requests[-1] == ("/gelf", "synthetic-local-input", payload)


def test_untrusted_certificate_and_wrong_hostname_never_reach_handler(receiver):
    _, requests, _ = receiver
    before = len(requests)
    base = config(receiver)
    assert GelfTransport(replace(base, ca_file=None)).send({}).state == "uncertain"
    wrong_name = replace(base, endpoint=base.endpoint.replace("localhost", "127.0.0.1"))
    assert GelfTransport(wrong_name).send({}).state == "uncertain"
    assert len(requests) == before


def test_redirect_does_not_forward_credentials_or_payload(receiver):
    server, requests, _ = receiver
    server.response_code = 302
    before = len(requests)
    result = GelfTransport(config(receiver)).send({"synthetic": True})
    assert result.state == "blocked"
    assert len(requests) == before + 1


def test_client_certificate_authentication_is_enforced(receiver):
    server, requests, certificate = receiver
    server.response_code = 202
    context = server.socket.context
    context.load_verify_locations(cafile=str(certificate))
    context.verify_mode = ssl.CERT_REQUIRED
    before = len(requests)
    try:
        assert GelfTransport(config(receiver)).send({}).state == "uncertain"
        assert len(requests) == before
        authenticated = replace(
            config(receiver),
            headers={},
            client_cert_file=str(certificate),
            client_key_file=str(certificate.with_name("server.key")),
        )
        assert GelfTransport(authenticated).send({}).state == "accepted"
        assert len(requests) == before + 1
    finally:
        context.verify_mode = ssl.CERT_NONE
