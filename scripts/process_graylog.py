"""Host/container entrypoint; configuration and credentials stay outside Git."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.audit import ORIGINS  # noqa: E402
from app.graylog import GelfTransport, GraylogConfig, GraylogError  # noqa: E402
from app.graylog_delivery import GraylogRepository, run_batch  # noqa: E402


def instant(raw):
    value = datetime.fromisoformat(raw)
    if value.utcoffset() is None:
        raise argparse.ArgumentTypeError("Informe UTC ou fuso explicito")
    return value.astimezone(UTC)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--config", type=Path)
    sub = result.add_subparsers(dest="action", required=True)
    init = sub.add_parser(
        "init", help="Criar modelo privado desabilitado, sem rede/banco"
    )
    init.add_argument("--output", type=Path, required=True)
    sub.add_parser("check", help="Validar arquivo local; nao testa acesso")
    status = sub.add_parser(
        "status", help="Contagens e IDs de eventos retidos, sem rede"
    )
    status.add_argument("--from", dest="start", type=instant)
    status.add_argument("--to", dest="end", type=instant)
    status.add_argument("--event-id")
    run = sub.add_parser("run", help="Processar um lote; agendamento externo")
    run.add_argument("--allow-network", action="store_true")
    backfill = sub.add_parser("backfill", help="Enfileirar um lote de janela historica")
    backfill.add_argument("--origin", choices=sorted(ORIGINS), required=True)
    backfill.add_argument("--from", dest="start", type=instant, required=True)
    backfill.add_argument("--to", dest="end", type=instant, required=True)
    reconcile = sub.add_parser(
        "reconcile", help="Resolver somente um evento com evidencia"
    )
    reconcile.add_argument("--event-id", required=True)
    reconcile.add_argument(
        "--resolution",
        choices=["confirm_received", "confirm_absent", "requeue"],
        required=True,
    )
    for command in (backfill, reconcile):
        command.add_argument("--authorize", action="store_true")
        command.add_argument("--operator-id", type=UUID, required=True)
        command.add_argument("--evidence-id", type=UUID, required=True)
    return result


def initialize(path):
    if path.resolve().is_relative_to(ROOT):
        raise GraylogError("configuration_must_be_external")
    template = {
        "endpoint": "https://graylog.example.invalid/gelf",
        "environment": "homologation",
        "application_version": "CHANGE-ME",
        "host": "synergia",
        "enabled": False,
        "authorization_confirmed": False,
        "include_global_events": False,
        "organization_ids": [],
        "include_actor_id": False,
        "include_resource_id": False,
        "headers": {},
        "ca_file": None,
        "client_cert_file": None,
        "client_key_file": None,
        "timeout_seconds": 10,
        "batch_size": 50,
        "max_attempts": 5,
        "retry_seconds": 30,
        "retryable_statuses": [],
    }
    with os.fdopen(
        os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
    ) as stream:
        json.dump(template, stream, indent=2)
        stream.write("\n")
    return {"status": "template_created_disabled"}


def execute(args):
    if args.action == "init":
        return initialize(args.output)
    if not args.config:
        raise GraylogError("configuration_required")
    if args.config.resolve().is_relative_to(ROOT):
        raise GraylogError("configuration_must_be_external")
    config = GraylogConfig.load(args.config)
    revision = os.getenv("SYNERGIA_BUILD_REVISION", "")
    if (
        re.fullmatch(r"[0-9a-f]{40}", revision)
        and config.application_version != revision
    ):
        raise GraylogError("application_version_mismatch")
    if args.action == "check":
        GelfTransport(config)  # Validate CA/client key locally; no request is sent.
        return {"status": "configuration_valid_no_network", "enabled": config.enabled}
    if args.action == "run":
        if not config.enabled:
            return {"status": "disabled", "processed": 0}
        if not args.allow_network:
            raise GraylogError("network_opt_in_required")
    if args.action in {"reconcile", "backfill"} and not args.authorize:
        raise GraylogError("operation_authorization_required")
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise GraylogError("database_not_configured")
    repository = GraylogRepository(database_url)
    if args.action == "run":
        return run_batch(repository, config, GelfTransport(config))
    with repository.locked() as connection:
        if args.action == "status":
            clauses, values = [], []
            if bool(args.start) != bool(args.end):
                raise GraylogError("window_invalid")
            if args.start:
                if not 0 < (args.end - args.start).total_seconds() <= 31 * 86400:
                    raise GraylogError("window_invalid")
                clauses += ["occurred_at >= %s", "occurred_at < %s"]
                values += [args.start, args.end]
            if args.event_id:
                if not re.fullmatch(r"[0-9a-f]{64}", args.event_id):
                    raise GraylogError("event_id_invalid")
                clauses.append("event_id = %s")
                values.append(args.event_id)
            if not clauses:
                clauses.append("state IN ('uncertain', 'blocked', 'exhausted')")
            held = connection.execute(
                """SELECT event_id, state, attempts, last_code
                FROM synergia.graylog_deliveries WHERE """
                + " AND ".join(clauses)
                + " ORDER BY created_at LIMIT 100",
                values,
            ).fetchall()
            return {
                "status": "inspected",
                "queue": repository.status(connection),
                "events_first_100": held,
            }
        repository.bind(connection, config)
        repository.recover(connection)
        if args.action == "backfill":
            scanned, completed = repository.backfill(
                connection,
                args.origin,
                args.start,
                args.end,
                config.batch_size,
                args.operator_id,
                args.evidence_id,
            )
            return {
                "status": "window_scanned",
                "scanned": scanned,
                "completed": completed,
            }
        if not re.fullmatch(r"[0-9a-f]{64}", args.event_id):
            raise GraylogError("event_id_invalid")
        repository.reconcile(
            connection,
            args.event_id,
            args.resolution,
            args.operator_id,
            args.evidence_id,
        )
    return {"status": "reconciled", "resolution": args.resolution}


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args)
    except GraylogError as exc:
        print(json.dumps({"error_code": str(exc)}))
        return 2
    except (psycopg.Error, OSError, ValueError, TypeError):
        # No exception messages: URLs, cert paths and DB errors can contain secrets.
        print(json.dumps({"error_code": "local_configuration_or_storage_failed"}))
        return 1
    except Exception:
        # Last CLI boundary: fail visibly without leaking stack locals/secrets.
        # An outstanding intent remains durable for reconciliation on restart.
        print(json.dumps({"error_code": "unexpected_worker_failure"}))
        return 1
    print(json.dumps(result))
    queue = result.get("queue", {})
    return int(
        args.action == "run"
        and any(queue.get(state, 0) for state in ("uncertain", "blocked", "exhausted"))
    )


if __name__ == "__main__":
    raise SystemExit(main())
