"""Tenant-bound, short transactions for validated assistance results."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from app.ai_assistance_contract import PRODUCT_NOTICE, AiAssistanceResponse
from app.ai_assistance_fallback import (
    FAILED,
    INSUFFICIENT,
    MISSING,
    NOTICE,
    TRUNCATED,
    validate_triage_finding_coherence,
)
from app.ai_assistance_generator import validate_language
from app.ai_assistance_telemetry import persistence


class AssistancePersistenceError(Exception):
    """Stable error code, no database or result content."""


@dataclass(frozen=True)
class AssistanceKey:
    organization_id: UUID
    execution_id: UUID
    context_sha256: str
    prompt_sha256: str
    model_name: str | None
    model_digest: str | None
    contract_version: str = "1.0.0"


def _validate_result_text(result: AiAssistanceResponse) -> None:
    """Only persist text the closed #187 generator can emit or contract examples."""
    summary = result.summary
    summary_pattern = (
        r"(?:A execução registra|Foram registrados) \d{1,19} (?:erro|erros), "
        r"\d{1,19} (?:aviso|avisos) e \d{1,19} (?:pendência|pendências)\."
        r"(?: Referências disponíveis: (?:DIV|PEN|CLA|EVI|HIS)-[a-f0-9]{32}"
        r"(?:, (?:DIV|PEN|CLA|EVI|HIS)-[a-f0-9]{32}){0,2}\.)?"
    )
    if summary not in {
        "Os fatos autorizados estão disponíveis para conferência humana.",
        "As evidências disponíveis são insuficientes.",
        "A resposta gerada foi recusada pela validação.",
    } and not re.fullmatch(summary_pattern, summary):
        raise ValueError("invalid result summary")
    if not set(result.human_checks) <= {
        NOTICE,
        "Conferência humana das referências disponíveis.",
        "Conferência humana das evidências disponíveis.",
    } or not set(result.limitations) <= {
        NOTICE,
        FAILED,
        INSUFFICIENT,
        MISSING,
        TRUNCATED,
        PRODUCT_NOTICE,
    }:
        raise ValueError("invalid result text")
    refs = []
    for finding in result.findings:
        selected = finding.evidence_refs
        if not validate_triage_finding_coherence(
            finding.title, finding.explanation, selected
        ):
            raise ValueError("invalid result finding")
        refs.extend(finding.evidence_refs)
    if len(refs) != len(set(refs)):
        raise ValueError("duplicate result references")


def _validate_actor(connection, actor_id):
    # Keep the identity alive until the event and its Graylog projection commit.
    if (
        connection.execute(
            "SELECT id FROM synergia.identity_users WHERE id=%s FOR KEY SHARE",
            (actor_id,),
        ).fetchone()
        is None
    ):
        raise AssistancePersistenceError("actor_not_found")


def _event(connection, row, actor_id, correlation_id, action):
    _validate_actor(connection, actor_id)
    connection.execute(
        """INSERT INTO synergia.ai_assistance_events
        (id, assistance_id, execution_id, organization_id, actor_user_id,
         correlation_id, action, state, origin, contract_version, model_name,
         model_digest, context_sha256,
         prompt_sha256, response_sha256, rejection_code, elapsed_ms)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            uuid4(),
            row["id"],
            row["execution_id"],
            row["organization_id"],
            actor_id,
            correlation_id,
            action,
            row["state"],
            row["origin"],
            row["contract_version"],
            row["model_name"],
            row["model_digest"],
            row["context_sha256"],
            row["prompt_sha256"],
            row["response_sha256"],
            row["rejection_code"],
            row["elapsed_ms"],
        ),
    )


def _validated(row, evidence_refs):
    try:
        result = AiAssistanceResponse.model_validate_json(
            json.dumps(row["result"]), context={"evidence_refs": evidence_refs}
        )
        for text in (
            result.summary,
            *result.human_checks,
            *result.limitations,
            *(
                text
                for finding in result.findings
                for text in (finding.title, finding.explanation)
            ),
        ):
            validate_language(text)
        _validate_result_text(result)
        summary_refs = set(
            re.findall(r"\b(?:DIV|PEN|CLA|EVI|HIS)-[a-f0-9]{32}\b", result.summary)
        )
        if not summary_refs <= set(evidence_refs):
            raise ValueError("invalid summary references")
        provenance = result.provenance
        if (
            str(result.assistance_id) != str(row["id"])
            or str(result.execution_id) != row["execution_id"]
            or result.state != row["state"]
            or provenance.origin != row["origin"]
            or provenance.context_hash != row["context_sha256"]
            or provenance.prompt_hash != row["prompt_sha256"]
            or provenance.model != row["model_name"]
            or provenance.digest != row["model_digest"]
            or provenance.contract_version != row["contract_version"]
            or provenance.timings.total_ms != row["elapsed_ms"]
        ):
            raise ValueError("inconsistent result")
        return result
    except (ValueError, TypeError, KeyError, ValidationError):
        raise AssistancePersistenceError("integrity_error") from None


class PostgresAiAssistanceRepository:
    """Each operation opens and commits its own transaction; no inference here."""

    def __init__(self, database_url: str, retention_days: int = 30):
        if type(retention_days) is not int or not 1 <= retention_days <= 365:
            raise ValueError("invalid retention")
        self.database_url = database_url
        self.retention_days = retention_days

    @persistence("reserve")
    def reserve(
        self,
        key: AssistanceKey,
        actor_id: UUID,
        correlation_id: UUID,
        *,
        enforce_inflight: bool = False,
    ):
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            # Serialize the short reservation decision across both dimensions.
            # Transaction-scoped locks are released before inference starts.
            if enforce_inflight:
                for value in sorted(
                    (
                        f"assistance-org:{key.organization_id}",
                        f"assistance-user:{actor_id}",
                    )
                ):
                    connection.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (value,),
                    )
                busy = connection.execute(
                    """SELECT 1 FROM synergia.ai_assistances
                    WHERE state='processing' AND reservation_until > clock_timestamp()
                      AND (organization_id=%s OR requested_by=%s) LIMIT 1""",
                    (key.organization_id, actor_id),
                ).fetchone()
                if busy is not None:
                    raise AssistancePersistenceError("conflict_or_not_found")
            abandoned = connection.execute(
                """DELETE FROM synergia.ai_assistances a
                USING synergia.executions e
                WHERE a.organization_id=%s AND a.execution_id=%s
                  AND e.id=a.execution_id AND e.organization_id=a.organization_id
                  AND a.context_sha256=%s AND a.prompt_sha256=%s
                  AND a.model_digest IS NOT DISTINCT FROM %s AND a.contract_version=%s
                  AND ((a.state='processing'
                        AND a.reservation_until <= clock_timestamp())
                       OR a.expires_at <= clock_timestamp())
                RETURNING a.*""",
                (
                    key.organization_id,
                    str(key.execution_id),
                    key.context_sha256,
                    key.prompt_sha256,
                    key.model_digest,
                    key.contract_version,
                ),
            ).fetchone()
            if abandoned is not None:
                _event(connection, abandoned, actor_id, correlation_id, "expired")
            row = connection.execute(
                """INSERT INTO synergia.ai_assistances
                (id,organization_id,execution_id,requested_by,state,contract_version,
                 model_name,model_digest,context_sha256,prompt_sha256,expires_at,reservation_until)
                SELECT %s,e.organization_id,e.id,%s,'processing',%s,%s,%s,%s,%s,
                       clock_timestamp() + %s, clock_timestamp() + interval '2 minutes'
                FROM synergia.executions e WHERE e.id=%s AND e.organization_id=%s
                ON CONFLICT DO NOTHING RETURNING *""",
                (
                    uuid4(),
                    actor_id,
                    key.contract_version,
                    key.model_name,
                    key.model_digest,
                    key.context_sha256,
                    key.prompt_sha256,
                    timedelta(days=self.retention_days),
                    str(key.execution_id),
                    key.organization_id,
                ),
            ).fetchone()
            if row is None:
                raise AssistancePersistenceError("conflict_or_not_found")
            _event(connection, row, actor_id, correlation_id, "requested")
        return row["id"]

    @persistence("abandon")
    def abandon(self, key, assistance_id, actor_id, correlation_id, rejection_code):
        """Release a failed reservation and audit only its safe error code."""
        allowed = {
            "runtime_busy",
            "runtime_timeout",
            "runtime_unavailable",
            "runtime_pin_mismatch",
            "runtime_redirect",
            "runtime_response_too_large",
            "runtime_invalid_response",
        }
        if rejection_code not in allowed:
            rejection_code = "runtime_unavailable"
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                """DELETE FROM synergia.ai_assistances
                WHERE id=%s AND organization_id=%s AND execution_id=%s
                  AND state='processing' RETURNING *""",
                (assistance_id, key.organization_id, str(key.execution_id)),
            ).fetchone()
            if row is not None:
                row["rejection_code"] = rejection_code
                _event(connection, row, actor_id, correlation_id, "rejected")

    @persistence("finish")
    def finish(
        self,
        key: AssistanceKey,
        assistance_id: UUID,
        actor_id: UUID,
        correlation_id: UUID,
        response: AiAssistanceResponse,
        *,
        evidence_refs: frozenset[str],
        response_sha256: str | None,
        rejection_code: str | None,
        elapsed_ms: int,
    ):
        serialized = response.model_dump(mode="json")
        _validated(
            {
                "result": serialized,
                "id": assistance_id,
                "execution_id": str(key.execution_id),
                "state": response.state,
                "origin": response.provenance.origin,
                "context_sha256": key.context_sha256,
                "prompt_sha256": key.prompt_sha256,
                "model_name": key.model_name,
                "model_digest": key.model_digest,
                "contract_version": key.contract_version,
                "elapsed_ms": elapsed_ms,
            },
            evidence_refs,
        )
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                """UPDATE synergia.ai_assistances a
                SET state=%s,origin=%s,result=%s,response_sha256=%s,rejection_code=%s,
                    elapsed_ms=%s,completed_at=clock_timestamp(),reservation_until=NULL
                FROM synergia.executions e
                WHERE a.id=%s AND a.organization_id=%s AND a.execution_id=%s
                  AND e.id=a.execution_id AND e.organization_id=a.organization_id
                  AND a.state='processing' AND a.reservation_until > clock_timestamp()
                  AND a.context_sha256=%s AND a.prompt_sha256=%s
                  AND a.model_digest IS NOT DISTINCT FROM %s AND a.contract_version=%s
                RETURNING a.*""",
                (
                    response.state,
                    response.provenance.origin,
                    Jsonb(serialized),
                    response_sha256,
                    rejection_code,
                    elapsed_ms,
                    assistance_id,
                    key.organization_id,
                    str(key.execution_id),
                    key.context_sha256,
                    key.prompt_sha256,
                    key.model_digest,
                    key.contract_version,
                ),
            ).fetchone()
            if row is None:
                raise AssistancePersistenceError("reservation_missing")
            result = _validated(row, evidence_refs)
            _event(
                connection,
                row,
                actor_id,
                correlation_id,
                "rejected" if result.state == "rejected" else "completed",
            )
        return result

    def complete(
        self, key, assistance_id, actor_id, correlation_id, response, **options
    ):
        if response.state not in {"ready", "insufficient_evidence"}:
            raise AssistancePersistenceError("invalid_completion_state")
        return self.finish(
            key, assistance_id, actor_id, correlation_id, response, **options
        )

    def reject(self, key, assistance_id, actor_id, correlation_id, response, **options):
        if response.state != "rejected":
            raise AssistancePersistenceError("invalid_rejection_state")
        return self.finish(
            key, assistance_id, actor_id, correlation_id, response, **options
        )

    @persistence("find")
    def find(
        self,
        key: AssistanceKey,
        actor_id: UUID,
        correlation_id: UUID,
        *,
        evidence_refs: frozenset[str],
    ):
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                """SELECT a.* FROM synergia.ai_assistances a
                JOIN synergia.executions e ON e.id=a.execution_id
                WHERE a.organization_id=%s AND a.execution_id=%s
                  AND e.organization_id=%s
                  AND a.context_sha256=%s AND a.prompt_sha256=%s
                  AND a.model_digest IS NOT DISTINCT FROM %s AND a.contract_version=%s
                  AND a.state <> 'processing' AND a.expires_at > clock_timestamp()""",
                (
                    key.organization_id,
                    str(key.execution_id),
                    key.organization_id,
                    key.context_sha256,
                    key.prompt_sha256,
                    key.model_digest,
                    key.contract_version,
                ),
            ).fetchone()
            if row is None:
                return None
            try:
                result = _validated(row, evidence_refs)
            except AssistancePersistenceError:
                result = None
                _event(connection, row, actor_id, correlation_id, "integrity_error")
            else:
                _event(connection, row, actor_id, correlation_id, "reused")
        if result is None:
            raise AssistancePersistenceError("integrity_error") from None
        return result

    @persistence("get")
    def get(
        self,
        organization_id: UUID,
        execution_id: UUID,
        assistance_id: UUID,
        actor_id: UUID,
        correlation_id: UUID,
        *,
        evidence_refs: frozenset[str],
    ):
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                """SELECT a.* FROM synergia.ai_assistances a
                JOIN synergia.executions e ON e.id=a.execution_id
                WHERE a.id=%s AND a.organization_id=%s AND a.execution_id=%s
                  AND e.organization_id=%s AND a.state <> 'processing'
                  AND a.expires_at > clock_timestamp()""",
                (assistance_id, organization_id, str(execution_id), organization_id),
            ).fetchone()
            if row is None:
                return None
            try:
                result = _validated(row, evidence_refs)
            except AssistancePersistenceError:
                result = None
                _event(connection, row, actor_id, correlation_id, "integrity_error")
            else:
                _event(connection, row, actor_id, correlation_id, "read")
        if result is None:
            raise AssistancePersistenceError("integrity_error") from None
        return result

    @persistence("latest")
    def latest(
        self,
        organization_id: UUID,
        execution_id: UUID,
        context_sha256: str,
        actor_id: UUID,
        correlation_id: UUID,
        *,
        evidence_refs: frozenset[str],
    ):
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                """SELECT a.* FROM synergia.ai_assistances a
                JOIN synergia.executions e ON e.id=a.execution_id
                WHERE a.organization_id=%s AND a.execution_id=%s
                  AND e.organization_id=%s AND a.context_sha256=%s
                  AND a.state <> 'processing' AND a.expires_at > clock_timestamp()
                ORDER BY a.created_at DESC, a.id DESC LIMIT 1""",
                (organization_id, str(execution_id), organization_id, context_sha256),
            ).fetchone()
            if row is None:
                return None
            try:
                result = _validated(row, evidence_refs)
            except AssistancePersistenceError:
                result = None
                _event(connection, row, actor_id, correlation_id, "integrity_error")
            else:
                _event(connection, row, actor_id, correlation_id, "read")
        if result is None:
            raise AssistancePersistenceError("integrity_error") from None
        return result

    @persistence("recover_reservations")
    def recover_reservations(
        self,
        actor_id: UUID,
        correlation_id: UUID,
        *,
        batch_size=100,
        dry_run=True,
        _maintenance_started=None,
    ):
        """Release only expired processing leases; no inference or result deletion."""
        if type(batch_size) is not int or not 1 <= batch_size <= 1000:
            raise ValueError("invalid batch size")
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            _validate_actor(connection, actor_id)
            if dry_run:
                return connection.execute(
                    """SELECT count(*) AS count, min(reservation_until) AS oldest,
                       max(reservation_until) AS newest FROM (SELECT reservation_until
                       FROM synergia.ai_assistances
                       WHERE state='processing'
                         AND reservation_until <= clock_timestamp()
                       ORDER BY reservation_until,id LIMIT %s) AS expired""",
                    (batch_size,),
                ).fetchone()
            rows = connection.execute(
                """DELETE FROM synergia.ai_assistances WHERE id IN
                (SELECT id FROM synergia.ai_assistances
                 WHERE state='processing' AND reservation_until <= clock_timestamp()
                 ORDER BY reservation_until,id LIMIT %s FOR UPDATE SKIP LOCKED)
                RETURNING *""",
                (batch_size,),
            ).fetchall()
            for row in rows:
                _event(connection, row, actor_id, correlation_id, "expired")
            if _maintenance_started is not None:
                from app.ai_assistance_maintenance import terminal_event

                terminal_event(
                    connection,
                    "recovery",
                    actor_id,
                    correlation_id,
                    len(rows),
                    _maintenance_started,
                )
        return {
            "count": len(rows),
            "oldest": min((r["reservation_until"] for r in rows), default=None),
            "newest": max((r["reservation_until"] for r in rows), default=None),
        }

    @persistence("expire")
    def expire(
        self,
        actor_id: UUID,
        correlation_id: UUID,
        *,
        batch_size=100,
        dry_run=False,
        _maintenance_started=None,
    ):
        if type(batch_size) is not int or not 1 <= batch_size <= 1000:
            raise ValueError("invalid batch size")
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            _validate_actor(connection, actor_id)
            if dry_run:
                return connection.execute(
                    """SELECT count(*) AS count, min(expires_at) AS oldest,
                       max(expires_at) AS newest FROM (SELECT expires_at
                       FROM synergia.ai_assistances
                       WHERE expires_at <= clock_timestamp()
                       ORDER BY expires_at,id LIMIT %s) AS expired""",
                    (batch_size,),
                ).fetchone()
            rows = connection.execute(
                """DELETE FROM synergia.ai_assistances WHERE id IN
                (SELECT id FROM synergia.ai_assistances
                 WHERE expires_at <= clock_timestamp()
                 ORDER BY expires_at,id LIMIT %s FOR UPDATE SKIP LOCKED) RETURNING *""",
                (batch_size,),
            ).fetchall()
            for row in rows:
                _event(connection, row, actor_id, correlation_id, "expired")
            if _maintenance_started is not None:
                from app.ai_assistance_maintenance import terminal_event

                terminal_event(
                    connection,
                    "retention",
                    actor_id,
                    correlation_id,
                    len(rows),
                    _maintenance_started,
                )
        return {
            "count": len(rows),
            "oldest": min((r["expires_at"] for r in rows), default=None),
            "newest": max((r["expires_at"] for r in rows), default=None),
        }
