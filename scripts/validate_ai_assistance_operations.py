"""Synthetic #191 drill against the project's owned local Graylog laboratory.

No real model, dependency overrides, operational database or company credentials.
Private connection details stay outside Git. A receipt requires indexed search.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from scripts.graylog_lab import (  # noqa: E402
    ENDPOINT,
    Laboratory,
    private_write,
)
from scripts.serve_assistance_e2e import ControlledProvider  # noqa: E402


class SyntheticRuntime:
    """Local HTTP protocol double. Never loads weights or executes model text."""

    model = "synthetic-ai191"
    digest = "sha256:" + "1" * 64

    def __init__(self):
        self.mode = "healthy"
        self.calls = []
        runtime = self

        class Handler(BaseHTTPRequestHandler):
            def respond(self, body, status=200):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                runtime.calls.append(self.path)
                if runtime.mode == "unavailable":
                    self.respond({}, 503)
                elif self.path == "/api/version":
                    self.respond({"version": "0.40.15"})
                elif self.path in {"/api/tags", "/api/ps"}:
                    self.respond(
                        {"models": [{"name": runtime.model, "digest": "1" * 64}]}
                    )
                else:
                    self.respond({}, 404)

            def do_POST(self):
                runtime.calls.append(self.path)
                size = int(self.headers.get("Content-Length", "0"))
                if self.path != "/api/chat" or not 0 < size <= 65536:
                    self.respond({}, 400)
                    return
                payload = json.loads(self.rfile.read(size))
                if runtime.mode == "unavailable":
                    self.respond({}, 503)
                    return
                text = (
                    "<script>AI191_REJECTED_OUTPUT</script>"
                    if runtime.mode == "malicious"
                    else ControlledProvider()
                    .generate(
                        payload["messages"][0]["content"],
                        payload["messages"][1]["content"],
                        payload["format"],
                    )
                    .decode()
                )
                self.respond(
                    {
                        "model": "sha256-" + "1" * 64,
                        "done": True,
                        "message": {"role": "assistant", "content": text},
                    }
                )

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    @property
    def endpoint(self):
        return f"http://127.0.0.1:{self.server.server_port}"


def run(lab: Laboratory):
    import psycopg
    from argon2 import PasswordHasher
    from fastapi.testclient import TestClient
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    from psycopg.rows import dict_row

    # Ownership and running input are checked before credentials can be used.
    configured = lab.configure()
    lab.wait_input(True)
    access = lab.access()
    admin = make_conninfo(
        host="127.0.0.1",
        port=15479,
        user="postgres",
        password=access["postgres_password"],
        dbname="postgres",
    )
    name = "synergia_ai191_" + uuid4().hex
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    database = make_conninfo(
        host="127.0.0.1",
        port=15479,
        user="postgres",
        password=access["postgres_password"],
        dbname=name,
    )
    private_write(lab.workspace / "ai191-private-run.json", {"database_url": database})
    org, foreign, actor = uuid4(), uuid4(), uuid4()
    executions = [uuid4() for _ in range(5)]
    with psycopg.connect(database) as connection:
        for migration in sorted((ROOT / "database/migrations").glob("*.sql")):
            connection.execute(migration.read_text(), prepare=False)
        for index, organization in enumerate((org, foreign)):
            connection.execute(
                "INSERT INTO synergia.iam_organizations "
                "(id,organization_code,display_name) VALUES (%s,%s,'Synthetic AI Lab')",
                (organization, f"ai191-{index}"),
            )
        connection.execute(
            "INSERT INTO synergia.identity_users "
            "(id,status,display_name,local_password_hash) VALUES (%s,'active',"
            "'Synthetic Operator',%s)",
            (actor, PasswordHasher().hash(access["application_password"])),
        )
        connection.execute(
            "INSERT INTO synergia.user_emails "
            "(user_id,email,is_primary,is_verified,verified_at) "
            "VALUES (%s,'ai191@example.invalid',true,true,now())",
            (actor,),
        )
        connection.execute(
            "INSERT INTO synergia.user_role_assignments "
            "(user_id,role_id,organization_id) SELECT %s,id,%s FROM synergia.roles "
            "WHERE normalized_key='gestor'",
            (actor, org),
        )
        for index, execution in enumerate(executions):
            connection.execute(
                "INSERT INTO synergia.executions "
                "(id,organization_id,status,source,finished_at) "
                "VALUES (%s,%s,'completed','N-FP',now())",
                (str(execution), foreign if index == 3 else org),
            )
            source = connection.execute(
                "INSERT INTO synergia.source_files "
                "(execution_id,file_name,content_hash,source,size_bytes) "
                "VALUES (%s,'synthetic.csv',%s,'N-FP',10) RETURNING id",
                (str(execution), uuid4().hex * 2),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO synergia.pipeline_issues "
                "(execution_id,source_file_id,scope,severity,code,reason) "
                "VALUES (%s,%s,'record','error','invalid_value','Synthetic')",
                (str(execution), source),
            )

    os.environ.update(
        {
            "DATABASE_URL": database,
            "SYNERGIA_ENV": "test",
            "SYNERGIA_LOCAL_AUTH_ENABLED": "true",
            "AUTH_IDENTITY_PROVIDER": "local",
            "AUTH_JWT_SIGNING_KEY": access["signing_key"],
            "AUTH_JWT_ISSUER": "synergia-ai191-lab",
            "AUTH_JWT_AUDIENCE": "ai191-lab",
            "AUTH_REFRESH_COOKIE_SECURE": "false",
            "RATE_LIMIT_KEY_SECRET": access["signing_key"],
            "OBSERVABILITY_METRICS_TOKEN": access["input_key"],
            "IMPORT_STORAGE_DIR": str(lab.workspace / "ai191-storage"),
            "SYNERGIA_AI_ASSISTANCE_ENABLED": "true",
            "SYNERGIA_AI_ASSISTANCE_GENERATION_ENABLED": "true",
            "SYNERGIA_AI_ASSISTANCE_ALLOWED_SERVICE": "",
            "SYNERGIA_AI_ASSISTANCE_MODEL": SyntheticRuntime.model,
            "SYNERGIA_AI_ASSISTANCE_DIGEST": SyntheticRuntime.digest,
            "SYNERGIA_AI_ASSISTANCE_RETENTION_DAYS": "30",
        }
    )
    from app.ai_assistance_maintenance import run_maintenance
    from app.ai_assistance_repository import (
        AssistanceKey,
        PostgresAiAssistanceRepository,
    )
    from app.graylog import GelfTransport, GraylogConfig
    from app.graylog_delivery import GraylogRepository, run_batch

    def client():
        from app.main import create_app

        application = create_app()
        assert not application.dependency_overrides
        return TestClient(application)

    def path(index):
        return f"/executions/{executions[index]}/ai-assistance"

    phases = []
    started = datetime.now(UTC).isoformat()
    with SyntheticRuntime() as runtime:
        os.environ["SYNERGIA_AI_ASSISTANCE_ENDPOINT"] = runtime.endpoint
        technical = {"Authorization": "Bearer " + access["input_key"]}
        with client() as http:
            login = http.post(
                "/auth/login",
                json={
                    "email": "ai191@example.invalid",
                    "password": access["application_password"],
                },
            )
            assert login.status_code == 200
            headers = {"Authorization": "Bearer " + login.json()["access_token"]}

        def phase(label, suspended=False):
            os.environ["SYNERGIA_AI_ASSISTANCE_GENERATION_ENABLED"] = (
                "false" if suspended else "true"
            )
            with client() as http:
                before = len(runtime.calls)
                probe = http.get("/operations/ai-assistance/health", headers=technical)
                assert probe.status_code == 200
                # A metadata probe must never infer.
                assert "/api/chat" not in runtime.calls[before:]
                response = http.post(
                    path(0 if label == "baseline" else 1), headers=headers
                )
                ready = http.get("/health/ready")
                core = http.get(f"/executions/{executions[0]}", headers=headers)
                read = http.get(path(0) + "/latest", headers=headers)
                assert ready.status_code == core.status_code == read.status_code == 200
                if suspended:
                    assert len(runtime.calls) == before
                phases.append(
                    {
                        "phase": label,
                        "probe": probe.json()["status"],
                        "post_status": response.status_code,
                        "read_status": read.status_code,
                        "ready_status": ready.status_code,
                        "core_status": core.status_code,
                    }
                )
                return response

        baseline = phase("baseline")
        assert (
            baseline.status_code == 200
            and baseline.json()["provenance"]["origin"] == "model"
        )
        runtime.mode = "unavailable"
        assert phase("failure").status_code == 503
        suspended = phase("suspension", suspended=True)
        assert suspended.status_code == 503
        assert suspended.json()["error"]["code"] == "ai_assistance_generation_disabled"
        runtime.mode = "healthy"
        recovered = phase("recovery")
        assert recovered.status_code == 200
        with client() as http:
            before = len(runtime.calls)
            assert http.post(path(1), headers=headers).json() == recovered.json()
            assert len(runtime.calls) == before
            denied = http.get(path(3) + "/latest", headers=headers)
            assert denied.status_code == 404 and len(runtime.calls) == before
            runtime.mode = "malicious"
            rejected = http.post(path(2), headers=headers)
            assert (
                rejected.status_code == 200 and rejected.json()["state"] == "rejected"
            )
            assert "AI191_REJECTED_OUTPUT" not in rejected.text

        # Workers have returned. Suspend before recovering the expired test lease.
        os.environ["SYNERGIA_AI_ASSISTANCE_GENERATION_ENABLED"] = "false"
        repo = PostgresAiAssistanceRepository(database)
        key = AssistanceKey(org, executions[4], "a" * 64, "b" * 64, None, None)
        reservation = repo.reserve(key, actor, uuid4())
        with psycopg.connect(database) as connection:
            connection.execute(
                "UPDATE synergia.ai_assistances "
                "SET reservation_until=now()-interval '1 second' "
                "WHERE id=%s",
                (reservation,),
            )
        before = len(runtime.calls)
        preview = run_maintenance(repo, "recovery", actor, uuid4(), dry_run=True)
        recovery = run_maintenance(repo, "recovery", actor, uuid4(), dry_run=False)
        retention_preview = run_maintenance(
            repo, "retention", actor, uuid4(), dry_run=True
        )
        retention = run_maintenance(repo, "retention", actor, uuid4(), dry_run=False)
        assert preview["count"] == recovery["count"] == 1
        assert retention_preview["count"] == retention["count"] == 0
        assert len(runtime.calls) == before
        with client() as http:
            assert http.get(path(0) + "/latest", headers=headers).status_code == 200
            metrics = http.get("/metrics", headers=technical)
            assert metrics.status_code == 200
            for forbidden in ("AI191_REJECTED_OUTPUT", access["input_key"], str(org)):
                assert forbidden not in metrics.text
            samples = "\n".join(
                line
                for line in metrics.text.splitlines()
                if line.startswith(
                    (
                        "synergia_ai_assistance_",
                        "# HELP synergia_ai_assistance_",
                        "# TYPE synergia_ai_assistance_",
                    )
                )
            )
            private_write(lab.workspace / "ai191-metrics.prom", samples)
        with psycopg.connect(database) as connection:
            retained = connection.execute(
                "SELECT count(*) FROM synergia.ai_assistances "
                "WHERE state <> 'processing'"
            ).fetchone()[0]
        assert retained == 3
        inference_count = runtime.calls.count("/api/chat")
        # Baseline, recovery, rejected output; no automatic retry.
        assert inference_count == 3

    config = GraylogConfig(
        endpoint=ENDPOINT,
        environment="test",
        application_version="issue-191-drill",
        enabled=True,
        authorization_confirmed=True,
        include_global_events=True,
        include_resource_id=True,
        organization_ids=(org,),
        headers={"X-Synergia-Input-Key": access["input_key"]},
        ca_file=str(lab.workspace / "ca.pem"),
        batch_size=100,
    )
    repository, transport = GraylogRepository(database), GelfTransport(config)
    for _ in range(10):
        batch = run_batch(repository, config, transport)
        if batch["processed"] == 0:
            break
    with psycopg.connect(database, row_factory=dict_row) as connection:
        expected = connection.execute(
            "SELECT d.event_id,d.event_key,d.origin,d.source_snapshot "
            "FROM synergia.graylog_deliveries d "
            "WHERE d.origin IN ('ai_assistance_events','data_operation_events')"
        ).fetchall()
    assert expected
    assert sum(row["origin"] == "data_operation_events" for row in expected) == 4
    query = (
        "service:synergia-audit-projector AND ("
        + " OR ".join('event_id:"' + row["event_id"] + '"' for row in expected)
        + ")"
    )
    indexed = lab.wait_search(query, len(expected))
    by_id = {row["event_id"]: row for row in indexed}
    assert len(by_id) == len(expected)
    receipts = []
    evidence_id = uuid4()
    with repository.locked() as connection:
        for row in expected:
            received, source = by_id[row["event_id"]], row["source_snapshot"]
            for field in ("origin", "outcome", "correlation_id"):
                assert received[field] == str(source[field])
            assert received["message"] == source["action"]
            assert (
                connection.execute(
                    "SELECT count(*) AS n FROM synergia.audit_event_catalog "
                    "WHERE id=%s",
                    (row["event_key"],),
                ).fetchone()["n"]
                == 1
            )
            repository.reconcile(
                connection,
                row["event_id"],
                "confirm_received",
                actor,
                evidence_id,
            )
            receipts.append(
                {
                    key: received[key]
                    for key in (
                        "event_id",
                        "message",
                        "origin",
                        "outcome",
                        "correlation_id",
                    )
                }
            )
    repeated = run_batch(repository, config, transport)
    assert repeated["processed"] == 0
    assert len(lab.wait_search(query, len(expected))) == len(expected)
    result = {
        "status": "validated_ai191_real_graylog",
        "evidence_id": str(evidence_id),
        "started_at": started,
        "finished_at": datetime.now(UTC).isoformat(),
        "graylog_version": configured["version"],
        "runtime": "synthetic_http_no_model",
        "real_authentication": True,
        "dependency_overrides": False,
        "phases": phases,
        "inferences": inference_count,
        "reuse_without_inference": True,
        "cross_org_status": denied.status_code,
        "malicious_output": "rejected_without_raw_content",
        "recovered_reservations": recovery["count"],
        "retained_results": retained,
        "retention_empty_batch_succeeded": True,
        "confirmed_receipts": receipts,
        "repeated_export_processed": repeated["processed"],
        "graylog_query": query,
    }
    private_write(lab.workspace / "ai191-validation.json", result)
    return {"status": result["status"], "receipts": len(receipts)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--runtime", choices=("docker", "podman"), default="docker")
    args = parser.parse_args(argv)
    logging.disable(logging.CRITICAL)
    try:
        result = run(Laboratory(args.workspace, args.runtime))
    except Exception:
        print(json.dumps({"error_code": "ai191_drill_failed"}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
