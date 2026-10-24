"""Explicit, audited resolution of uncertain SMTP results. No message is sent."""

from __future__ import annotations

from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from app.email_delivery import SMTP_UNCERTAIN
from app.smtp_email_provider import SAFE_SMTP_FAILURE_CODES


class EmailReconciliationRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def inspect(self, delivery_id: UUID) -> dict:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            connection.read_only = True
            row = connection.execute(
                "SELECT id AS delivery_id, provider, state, attempt_count, "
                "failure_code, "
                "claimed_at, sent_at, correlation_id FROM synergia.email_deliveries "
                "WHERE id = %s AND provider = 'smtp'",
                (delivery_id,),
            ).fetchone()
        if row is None:
            raise ValueError("smtp_delivery_not_found")
        if row["failure_code"] not in SAFE_SMTP_FAILURE_CODES | {
            None,
            "provider_configuration_invalid",
            "provider_temporarily_unavailable",
            "provider_rejected",
            "max_attempts_exceeded",
        }:
            row["failure_code"] = "unclassified_failure"
        return dict(row)

    def reconcile(
        self,
        delivery_id: UUID,
        *,
        resolution: str,
        evidence: str,
        request_id: UUID,
        actor_id: UUID,
        workers_stopped: bool,
        max_attempts: int = 3,
    ) -> dict:
        if not workers_stopped:
            raise ValueError("stop_smtp_workers_before_reconciliation")
        if (
            resolution not in {"accepted", "not_accepted"}
            or evidence not in {"smtp_log", "recipient_confirmation"}
            or resolution == "not_accepted"
            and evidence != "smtp_log"
        ):
            raise ValueError("invalid_reconciliation_evidence")
        if (
            not all(isinstance(v, UUID) for v in (delivery_id, request_id, actor_id))
            or not isinstance(max_attempts, int)
            or isinstance(max_attempts, bool)
            or not 1 <= max_attempts <= 10
        ):
            raise ValueError("invalid_reconciliation_configuration")
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            delivery = connection.execute(
                "SELECT id, provider, state, attempt_count, failure_code, "
                "correlation_id, claimed_at < now() - interval '5 minutes' "
                "AS lease_expired "
                "FROM synergia.email_deliveries WHERE id = %s FOR UPDATE",
                (delivery_id,),
            ).fetchone()
            if delivery is None or delivery["provider"] != "smtp":
                raise ValueError("smtp_delivery_not_found")
            existing = connection.execute(
                "SELECT * FROM synergia.email_delivery_reconciliations "
                "WHERE request_id = %s",
                (request_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["delivery_id"] != delivery_id
                    or existing["resolution"] != resolution
                    or existing["evidence"] != evidence
                    or existing["actor_identifier"] != str(actor_id)
                ):
                    raise ValueError("reconciliation_request_conflict")
                return self._result(existing, True)
            if delivery["state"] == "processing" and delivery["lease_expired"]:
                # With all transmitters stopped, an expired attempt may be
                # resolved directly without starting a worker/network call.
                connection.execute(
                    "INSERT INTO synergia.email_delivery_attempts "
                    "(delivery_id, attempt_number, outcome, failure_code, "
                    "correlation_id) VALUES (%s, %s, 'failed', %s, %s)",
                    (
                        delivery_id,
                        delivery["attempt_count"],
                        SMTP_UNCERTAIN,
                        delivery["correlation_id"],
                    ),
                )
                delivery["state"] = "failed"
                delivery["failure_code"] = SMTP_UNCERTAIN
            if (
                delivery["state"] != "failed"
                or delivery["failure_code"] != SMTP_UNCERTAIN
            ):
                raise ValueError("delivery_is_not_awaiting_smtp_reconciliation")
            state = (
                "sent"
                if resolution == "accepted"
                else ("retry" if delivery["attempt_count"] < max_attempts else "failed")
            )
            connection.execute(
                "UPDATE synergia.email_deliveries SET state = %s, claimed_at = NULL, "
                "provider_reference = %s, failure_code = %s, "
                "sent_at = CASE WHEN %s = 'sent' THEN now() ELSE NULL END, "
                "available_at = now(), updated_at = now() WHERE id = %s",
                (
                    state,
                    f"smtp-{delivery_id}" if state == "sent" else None,
                    "max_attempts_exceeded" if state == "failed" else None,
                    state,
                    delivery_id,
                ),
            )
            record = connection.execute(
                "INSERT INTO synergia.email_delivery_reconciliations "
                "(delivery_id, attempt_number, request_id, resolution, evidence, "
                "actor_identifier, resulting_state, correlation_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (
                    delivery_id,
                    delivery["attempt_count"],
                    request_id,
                    resolution,
                    evidence,
                    str(actor_id),
                    state,
                    delivery["correlation_id"] or uuid4(),
                ),
            ).fetchone()
            return self._result(record, False)

    @staticmethod
    def _result(record, replay):
        return {
            "delivery_id": str(record["delivery_id"]),
            "attempt_number": record["attempt_number"],
            "resolution": record["resolution"],
            "resulting_state": record["resulting_state"],
            "audit_id": record["id"],
            "idempotent_replay": replay,
        }
