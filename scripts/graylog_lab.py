"""Local Graylog Open laboratory. No company credentials or production deployment."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

PREFIX = "synergia-graylog-lab-178"
LABEL = "io.synergia.graylog-lab"
WORKSPACE_LABEL = "io.synergia.graylog-lab.workspace"
IMAGES = {
    "mongo": "docker.io/library/mongo:7.0",
    "opensearch": "docker.io/opensearchproject/opensearch:2.19.6",
    "graylog": "docker.io/graylog/graylog:7.2.2",
    "postgres": "docker.io/library/postgres:16-alpine",
}
UI = "http://localhost:19000"
ENDPOINT = "https://127.0.0.1:12202/gelf"
ORGANIZATION = UUID("78000000-0000-4000-8000-000000000001")


class LabError(RuntimeError):
    pass


def private_write(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, indent=2))
        stream.write("\n")


class Laboratory:
    def __init__(self, workspace: Path, runtime: str):
        self.workspace = workspace.expanduser().resolve()
        if self.workspace.is_relative_to(ROOT):
            raise LabError("workspace_must_be_outside_git")
        self.runtime = runtime
        self.access_path = self.workspace / "access.json"
        self.workspace_id = hashlib.sha256(
            os.path.normcase(str(self.workspace)).encode()
        ).hexdigest()

    def command(self, *args, optional=False):
        result = subprocess.run(
            [self.runtime, *args],
            capture_output=True,
            text=True,
            timeout=None if args and args[0] == "pull" else 900,
        )
        if result.returncode and not optional:
            raise LabError("container_command_failed")
        return result

    def access(self):
        return json.loads(self.access_path.read_text(encoding="utf-8"))

    def inspect(self, kind, name):
        result = self.command(kind, "inspect", name, optional=True)
        if result.returncode:
            return None
        value = json.loads(result.stdout)
        return value[0] if isinstance(value, list) else value

    def owned(self, kind, name):
        value = self.inspect(kind, name)
        if value is not None:
            labels = (
                value.get("Config", {}).get("Labels")
                or value.get("Labels")
                or value.get("labels")
                or {}
            )
            if labels.get(LABEL) != "178":
                raise LabError("resource_not_owned_by_lab")
            if labels.get(WORKSPACE_LABEL) != self.workspace_id:
                raise LabError("resource_belongs_to_another_lab_workspace")
        return value

    def initialize(self):
        self.workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.workspace.chmod(0o700)
        if not self.access_path.exists():
            private_write(
                self.access_path,
                {
                    "username": "admin",
                    "password": secrets.token_urlsafe(32),
                    "password_secret": secrets.token_urlsafe(64),
                    "input_key": secrets.token_urlsafe(32),
                    "postgres_password": secrets.token_urlsafe(32),
                    "application_password": secrets.token_urlsafe(32),
                    "signing_key": secrets.token_urlsafe(48),
                },
            )
        access = self.access()
        certs = self.workspace / "certs"
        if not (self.workspace / "ca.pem").exists():
            openssl = shutil.which("openssl")
            if not openssl:
                candidate = (
                    Path(os.getenv("ProgramFiles", "C:/Program Files"))
                    / "Git/usr/bin/openssl.exe"
                )
                openssl = str(candidate) if candidate.is_file() else None
            if not openssl:
                raise LabError("openssl_required_for_local_certificate")
            certs.mkdir(mode=0o700, exist_ok=True)
            result = subprocess.run(
                [
                    openssl,
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "30",
                    "-subj",
                    "/CN=synergia-graylog-lab",
                    "-addext",
                    "subjectAltName=DNS:localhost,IP:127.0.0.1",
                    "-keyout",
                    str(certs / "server.key"),
                    "-out",
                    str(certs / "server.pem"),
                ],
                capture_output=True,
                check=False,
            )
            if result.returncode:
                raise LabError("local_certificate_generation_failed")
            (certs / "server.key").chmod(0o600)
            private_write(self.workspace / "ca.pem", (certs / "server.pem").read_text())
        private_write(
            self.workspace / "graylog.env",
            "\n".join(
                [
                    "GRAYLOG_PASSWORD_SECRET=" + access["password_secret"],
                    "GRAYLOG_ROOT_PASSWORD_SHA2="
                    + hashlib.sha256(access["password"].encode()).hexdigest(),
                    "GRAYLOG_HTTP_BIND_ADDRESS=0.0.0.0:9000",
                    "GRAYLOG_HTTP_EXTERNAL_URI=" + UI + "/",
                    "GRAYLOG_MONGODB_URI=mongodb://" + PREFIX + "-mongo:27017/graylog",
                    "GRAYLOG_ELASTICSEARCH_HOSTS=http://" + PREFIX + "-opensearch:9200",
                    "GRAYLOG_SERVER_JAVA_OPTS=-Xms512m -Xmx512m",
                    "GRAYLOG_TELEMETRY_ENABLED=false",
                ]
            ),
        )
        private_write(
            self.workspace / "postgres.env",
            "\n".join(
                [
                    "POSTGRES_USER=postgres",
                    "POSTGRES_DB=synergia_graylog_lab",
                    "POSTGRES_PASSWORD=" + access["postgres_password"],
                ]
            ),
        )
        return {"status": "private_lab_configuration_ready", "ui": UI}

    def ensure_resource(self, kind, name):
        if self.owned(kind, name) is None:
            options = ["--internal"] if kind == "network" else []
            self.command(
                kind,
                "create",
                *options,
                "--label",
                LABEL + "=178",
                "--label",
                WORKSPACE_LABEL + "=" + self.workspace_id,
                name,
            )

    def ensure_container(self, name, options, role, command=()):
        current = self.owned("container", name)
        if current is None:
            self.command(
                "run",
                "-d",
                "--name",
                name,
                "--label",
                LABEL + "=178",
                "--label",
                WORKSPACE_LABEL + "=" + self.workspace_id,
                "--network",
                PREFIX,
                *options,
                IMAGES[role],
                *command,
            )
        elif not current["State"]["Running"]:
            self.command("start", name)

    def start(self):
        self.initialize()
        for role, image in IMAGES.items():
            if self.inspect("image", image) is None:
                print(
                    json.dumps({"stage": "pulling_image", "component": role}),
                    flush=True,
                )
                self.command("pull", image)
        self.ensure_resource("network", PREFIX)
        for role in IMAGES:
            self.ensure_resource("volume", PREFIX + "-" + role)
        # Only this lab's certificate directory is changed, inside an ephemeral
        # container. Graylog reads its key as UID 1100; no broad chmod is needed.
        self.command(
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            "0:0",
            "--entrypoint",
            "chown",
            "-v",
            str(self.workspace / "certs") + ":/lab",
            IMAGES["graylog"],
            "-R",
            "1100:1100",
            "/lab",
        )
        self.ensure_container(
            PREFIX + "-mongo",
            [
                "--memory",
                "768m",
                "-v",
                PREFIX + "-mongo:/data/db",
            ],
            "mongo",
            ["--wiredTigerCacheSizeGB", "0.25", "--bind_ip_all"],
        )
        self.ensure_container(
            PREFIX + "-opensearch",
            [
                "--memory",
                "2g",
                "--ulimit",
                "nofile=65536:65536",
                "-e",
                "discovery.type=single-node",
                "-e",
                "DISABLE_INSTALL_DEMO_CONFIG=true",
                "-e",
                "DISABLE_SECURITY_PLUGIN=true",
                "-e",
                "OPENSEARCH_JAVA_OPTS=-Xms1g -Xmx1g",
                "-v",
                PREFIX + "-opensearch:/usr/share/opensearch/data",
            ],
            "opensearch",
        )
        self.ensure_container(
            PREFIX + "-postgres",
            [
                "--env-file",
                str(self.workspace / "postgres.env"),
                "-p",
                "127.0.0.1:15479:5432",
                "-v",
                PREFIX + "-postgres:/var/lib/postgresql/data",
            ],
            "postgres",
        )
        self.ensure_container(
            PREFIX + "-graylog",
            [
                "--memory",
                "2g",
                "--env-file",
                str(self.workspace / "graylog.env"),
                "-p",
                "127.0.0.1:19000:9000",
                "-p",
                "127.0.0.1:12202:12202",
                "-v",
                PREFIX + "-graylog:/usr/share/graylog/data",
                "-v",
                str(self.workspace / "certs") + ":/run/graylog-lab:ro",
            ],
            "graylog",
        )
        print(json.dumps({"stage": "waiting_for_graylog", "ui": UI}), flush=True)
        return {"status": "containers_started", "ui": UI}

    def api(self, method, path, body=None):
        from app.graylog import NoRedirect

        server = self.owned("container", PREFIX + "-graylog")
        if not server or not server["State"]["Running"]:
            raise LabError("owned_graylog_container_not_running")
        access = self.access()
        authorization = base64.b64encode(
            (access["username"] + ":" + access["password"]).encode()
        ).decode()
        request = urllib.request.Request(
            UI + "/api/" + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": "Basic " + authorization,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Requested-By": "synergia-lab",
            },
        )
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect()
        )
        with opener.open(request, timeout=15) as response:
            data = response.read(4 * 1024 * 1024)
            return json.loads(data) if data else {}

    def configure(self):
        for role in IMAGES:
            container = self.owned("container", PREFIX + "-" + role)
            if not container or not container["State"]["Running"]:
                raise LabError(role + "_not_running")
        deadline = time.monotonic() + 180
        while True:
            try:
                system = self.api("GET", "system")
                break
            except (urllib.error.URLError, OSError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise LabError("graylog_not_ready") from None
                time.sleep(2)
        inputs = self.api("GET", "system/inputs")["inputs"]
        found = next((item for item in inputs if item["title"] == PREFIX), None)
        if found is None:
            details = self.api(
                "GET", "system/inputs/types/org.graylog2.inputs.gelf.http.GELFHttpInput"
            )
            schema = details.get("requested_configuration", {})
            configuration = {
                key: value["default_value"]
                for key, value in schema.items()
                if value.get("default_value") is not None
            }
            configuration.update(
                {
                    "bind_address": "0.0.0.0",
                    "port": 12202,
                    "tls_enable": True,
                    "tls_cert_file": "/run/graylog-lab/server.pem",
                    "tls_key_file": "/run/graylog-lab/server.key",
                    "number_worker_threads": 2,
                    "authorization_header_name": "X-Synergia-Input-Key",
                    "authorization_header_value": self.access()["input_key"],
                }
            )
            found = self.api(
                "POST",
                "system/inputs",
                {
                    "title": PREFIX,
                    "type": "org.graylog2.inputs.gelf.http.GELFHttpInput",
                    "global": True,
                    "configuration": configuration,
                },
            )
        input_id = found.get("id") or found.get("input_id")
        private_write(self.workspace / "input.json", {"id": input_id})
        return {
            "status": "input_configured",
            "version": system.get("version"),
            "input_id": input_id,
        }

    def search(self, query):
        result = self.api(
            "POST",
            "search/messages",
            {
                "query": query,
                "fields": [
                    "timestamp",
                    "message",
                    "event_id",
                    "correlation_id",
                    "origin",
                    "outcome",
                    "environment",
                    "service",
                    "resource_type",
                    "resource_id",
                    "meta_from_state",
                    "meta_to_state",
                ],
                "timerange": {"type": "relative", "range": 3600},
                "size": 100,
            },
        )
        fields = [column["field"] for column in result["schema"]]
        return [dict(zip(fields, row, strict=True)) for row in result["datarows"]]

    def wait_messages(self, correlation, expected):
        query = f'service:synergia-audit-projector AND correlation_id:"{correlation}"'
        return self.wait_search(query, expected)

    def wait_search(self, query, expected):
        deadline = time.monotonic() + 60
        while True:
            rows = self.search(query)
            if len(rows) == expected:
                return rows
            if len(rows) > expected or time.monotonic() > deadline:
                raise LabError("indexed_count_does_not_match")
            time.sleep(1)

    def wait_input(self, listening):
        input_id = json.loads((self.workspace / "input.json").read_text())["id"]
        expected_state = "RUNNING" if listening else "STOPPED"
        deadline = time.monotonic() + 30
        while True:
            try:
                state = self.api("GET", "system/inputstates/" + input_id)["state"]
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
                # Graylog can remove a stopped input from the node's registry.
                # Its persisted configuration must still exist before treating
                # that absence as the result of our controlled stop.
                self.api("GET", "system/inputs/" + input_id)
                state = "ABSENT"
            if state == expected_state:
                return
            if not listening and state == "ABSENT":
                return
            if time.monotonic() > deadline:
                raise LabError("input_state_timeout")
            time.sleep(0.25)

    def validate(self):
        import psycopg
        from argon2 import PasswordHasher
        from fastapi.testclient import TestClient
        from psycopg import sql
        from psycopg.conninfo import make_conninfo
        from psycopg.rows import dict_row

        from app.graylog import GelfTransport, GraylogConfig, to_gelf
        from app.graylog_delivery import GraylogRepository, run_batch

        configured = self.configure()
        self.wait_input(True)
        access = self.access()
        run_id, correlation, recovery_correlation, import_correlation = [
            uuid4() for _ in range(4)
        ]
        started_at = datetime.now(UTC)
        database = "synergia_graylog_demo_" + run_id.hex
        admin_url = make_conninfo(
            host="127.0.0.1",
            port=15479,
            user="postgres",
            password=access["postgres_password"],
            dbname="postgres",
        )
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database))
            )
        database_url = make_conninfo(
            host="127.0.0.1",
            port=15479,
            user="postgres",
            password=access["postgres_password"],
            dbname=database,
        )
        environment = dict(os.environ, DATABASE_URL=database_url)
        migrated = subprocess.run(
            [sys.executable, str(ROOT / "scripts/apply_migrations.py")],
            env=environment,
            capture_output=True,
        )
        if migrated.returncode:
            raise LabError("lab_migrations_failed")
        os.environ.update(
            {
                "DATABASE_URL": database_url,
                "SYNERGIA_ENV": "test",
                "SYNERGIA_LOCAL_AUTH_ENABLED": "true",
                "AUTH_IDENTITY_PROVIDER": "local",
                "AUTH_JWT_SIGNING_KEY": access["signing_key"],
                "AUTH_JWT_ISSUER": "synergia-graylog-lab",
                "AUTH_JWT_AUDIENCE": "synergia-lab",
                "AUTH_REFRESH_COOKIE_SECURE": "false",
                "RATE_LIMIT_KEY_SECRET": access["signing_key"],
                "IMPORT_STORAGE_DIR": str(self.workspace / "imports" / run_id.hex),
            }
        )
        user_id = uuid4()
        email = "graylog-lab@example.invalid"
        with psycopg.connect(database_url) as connection:
            connection.execute(
                """INSERT INTO synergia.iam_organizations
                (id, organization_code, display_name)
                VALUES (%s, 'syn-graylog-lab', 'Synthetic Graylog Lab')""",
                (ORGANIZATION,),
            )
            connection.execute(
                """INSERT INTO synergia.identity_users
                (id, status, display_name, local_password_hash)
                VALUES (%s, 'active', 'Synthetic Graylog Operator', %s)""",
                (user_id, PasswordHasher().hash(access["application_password"])),
            )
            connection.execute(
                """INSERT INTO synergia.user_emails
                (user_id, email, is_primary, is_verified, verified_at)
                VALUES (%s, %s, true, true, now())""",
                (user_id, email),
            )
            connection.execute(
                """INSERT INTO synergia.user_role_assignments
                (user_id, role_id, organization_id)
                SELECT %s, id, %s FROM synergia.roles
                WHERE normalized_key = 'operador'""",
                (user_id, ORGANIZATION),
            )
        from app.main import app

        if app.dependency_overrides:
            raise LabError("demo_requires_real_authentication_dependencies")
        config = GraylogConfig(
            endpoint=ENDPOINT,
            environment="test",
            application_version="issue-178-working-tree",
            enabled=True,
            authorization_confirmed=True,
            include_global_events=True,
            include_resource_id=True,
            organization_ids=(ORGANIZATION,),
            headers={"X-Synergia-Input-Key": access["input_key"]},
            ca_file=str(self.workspace / "ca.pem"),
            batch_size=100,
        )
        repository, transport = GraylogRepository(database_url), GelfTransport(config)
        # Rejection of an incorrect input credential is tested on the real server.
        probe = to_gelf(
            {
                "id": "identity:lab-probe",
                "occurred_at": started_at,
                "organization_id": None,
                "actor_id": None,
                "actor_type": "system",
                "action": "security.synthetic_probe",
                "resource_type": "security_control",
                "resource_id": "synthetic",
                "outcome": "failure",
                "correlation_id": run_id,
                "metadata": {},
                "origin": "identity_access_events",
            },
            config,
        )
        refused = GelfTransport(
            replace(
                config,
                headers={
                    "X-Synergia-Input-Key": secrets.token_urlsafe(32),
                },
            )
        ).send(probe)
        if refused.state != "blocked" or refused.code not in {"http_401", "http_403"}:
            raise LabError("input_did_not_refuse_incorrect_credential")

        with TestClient(app) as client:
            headers = {
                "Origin": "http://localhost:4200",
                "X-Correlation-ID": str(correlation),
            }
            failed = client.post(
                "/auth/login",
                json={"email": email, "password": "synthetic-wrong"},
                headers=headers,
            )
            logged_in = client.post(
                "/auth/login",
                json={"email": email, "password": access["application_password"]},
                headers=headers,
            )
            if failed.status_code != 401 or logged_in.status_code != 200:
                raise LabError("synthetic_login_scenario_failed")
            denied = client.get(
                "/admin/access/roles",
                headers={
                    **headers,
                    "Authorization": "Bearer " + logged_in.json()["access_token"],
                },
            )
            if denied.status_code != 403:
                raise LabError("synthetic_denial_scenario_failed")
            with psycopg.connect(database_url) as connection:
                expected_access = connection.execute(
                    "SELECT count(*) FROM synergia.graylog_deliveries "
                    "WHERE source_snapshot->>'correlation_id' = %s",
                    (str(correlation),),
                ).fetchone()[0]
            delivered = run_batch(repository, config, transport)
            rows = self.wait_messages(correlation, expected_access)
            if not {
                "auth.login_failed",
                "auth.login_succeeded",
                "authorization.denied",
            } <= {row["message"] for row in rows}:
                raise LabError("unexpected_indexed_actions")
            repeated = run_batch(repository, config, transport)
            if (
                repeated["processed"] != 0
                or len(self.wait_messages(correlation, expected_access))
                != expected_access
            ):
                raise LabError("accepted_events_were_resent")

            rejected_import = client.post(
                "/imports",
                data={"source": "N-FP", "organization_id": str(ORGANIZATION)},
                files={"file": ("synthetic-empty.csv", b"", "text/csv")},
                headers={
                    "Authorization": "Bearer " + logged_in.json()["access_token"],
                    "X-Correlation-ID": str(import_correlation),
                },
            )
            if rejected_import.status_code != 422:
                raise LabError("synthetic_import_rejection_failed")
            with psycopg.connect(database_url) as connection:
                expected_import = connection.execute(
                    "SELECT count(*) FROM synergia.graylog_deliveries "
                    "WHERE source_snapshot->>'correlation_id' = %s",
                    (str(import_correlation),),
                ).fetchone()[0]
            if not expected_import:
                raise LabError("import_did_not_emit_audit")
            run_batch(repository, config, transport)
            import_rows = self.wait_messages(import_correlation, expected_import)
            if not any(row["message"] == "file_rejected" for row in import_rows):
                raise LabError("rejected_file_not_indexed")

            input_id = json.loads((self.workspace / "input.json").read_text())["id"]
            self.api("DELETE", "system/inputstates/" + input_id)
            try:
                self.wait_input(False)
                during_outage = client.post(
                    "/auth/login",
                    json={"email": email, "password": "synthetic-wrong"},
                    headers={"X-Correlation-ID": str(recovery_correlation)},
                )
                if during_outage.status_code != 401:
                    raise LabError("graylog_outage_changed_business_response")
                outage = run_batch(repository, config, transport)
                if outage["queue"]["uncertain"] != 1:
                    raise LabError("unavailable_input_event_not_preserved")
                with repository.locked() as connection:
                    held = connection.execute(
                        "SELECT event_id FROM synergia.graylog_deliveries "
                        "WHERE state = 'uncertain'"
                    ).fetchone()["event_id"]
                if self.search(f'event_id:"{held}"'):
                    raise LabError("unexpected_receipt_during_stopped_input")
            finally:
                self.api("PUT", "system/inputstates/" + input_id)
                self.wait_input(True)
            with repository.locked() as connection:
                repository.reconcile(
                    connection, held, "confirm_absent", run_id, uuid4()
                )
            recovered = run_batch(repository, config, transport)
            recovered_rows = self.wait_messages(recovery_correlation, 1)
            again = run_batch(repository, config, transport)
            if again["processed"] != 0:
                raise LabError("recovered_event_was_resent")
        all_rows = rows + import_rows + recovered_rows
        expected_total = expected_access + expected_import + 1
        if len({row["event_id"] for row in all_rows}) != expected_total:
            raise LabError("duplicate_indexed_event_id")
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            saved_payloads = connection.execute(
                "SELECT payload FROM synergia.graylog_deliveries "
                "WHERE state = 'accepted'"
            ).fetchall()
            accepted_ids = {
                item["event_id"]
                for item in connection.execute(
                    "SELECT event_id FROM synergia.graylog_deliveries "
                    "WHERE state = 'accepted'"
                )
            }
        expected_total = len(accepted_ids)
        all_rows = self.wait_search(
            "event_id:("
            + " OR ".join(f'"{key}"' for key in sorted(accepted_ids))
            + ")",
            expected_total,
        )
        if {item["event_id"] for item in all_rows} != accepted_ids:
            raise LabError("source_and_index_event_ids_differ")
        for secret in access.values():
            if len(secret) > 12 and secret in json.dumps(saved_payloads):
                raise LabError("private_value_found_in_projection")
        private_write(
            self.workspace / "last-run.json",
            {
                "database_url": database_url,
                "correlation_id": str(correlation),
                "recovery_correlation_id": str(recovery_correlation),
                "import_correlation_id": str(import_correlation),
            },
        )
        result = {
            "status": "validated_real_graylog",
            "graylog_version": configured["version"],
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "correlation_id": str(correlation),
            "recovery_correlation_id": str(recovery_correlation),
            "import_correlation_id": str(import_correlation),
            "http_statuses": {
                "invalid_login": 401,
                "valid_login": 200,
                "denied_access": 403,
                "login_while_input_stopped": during_outage.status_code,
            },
            "import_http_status": rejected_import.status_code,
            "indexed_events": all_rows,
            "distinct_event_ids": expected_total,
            "scenario_counts": {
                "access": expected_access,
                "import": expected_import,
                "recovery": 1,
            },
            "source_and_index_ids_match": True,
            "first_batch": delivered,
            "outage_batch": outage,
            "recovery_batch": recovered,
            "accepted_repeat_processed": repeated["processed"],
            "recovered_repeat_processed": again["processed"],
            "incorrect_input_credential": refused.code,
            "corporate_deployment": "not_evaluated",
            "ui": UI,
        }
        private_write(self.workspace / "validation.json", result)
        return {
            "status": result["status"],
            "indexed_events": expected_total,
            "ui": UI,
            "evidence": str(self.workspace / "validation.json"),
        }

    def stop(self):
        for role in ("graylog", "opensearch", "mongo", "postgres"):
            name = PREFIX + "-" + role
            if self.owned("container", name) is not None:
                self.command("stop", "--time", "15", name)
        return {"status": "lab_stopped_data_preserved"}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--workspace", type=Path, required=True)
    result.add_argument("--runtime", choices=["docker", "podman"], default="docker")
    result.add_argument(
        "action", choices=["init", "start", "configure", "validate", "status", "stop"]
    )
    return result


def main(argv=None):
    logging.disable(logging.CRITICAL)
    args = parser().parse_args(argv)
    try:
        lab = Laboratory(args.workspace, args.runtime)
        if args.action == "status":
            result = {
                "status": "inspected",
                "running": {
                    role: bool(
                        (lab.owned("container", PREFIX + "-" + role) or {})
                        .get("State", {})
                        .get("Running")
                    )
                    for role in IMAGES
                },
                "ui": UI,
            }
        else:
            result = getattr(
                lab, {"init": "initialize"}.get(args.action, args.action)
            )()
    except LabError as exc:
        print(json.dumps({"error_code": str(exc)}))
        return 1
    except urllib.error.HTTPError as exc:
        print(json.dumps({"error_code": "graylog_api_http_" + str(exc.code)}))
        return 1
    except Exception:
        # Private API/config/engine errors must not print credentials or bodies.
        print(json.dumps({"error_code": "local_lab_operation_failed"}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
