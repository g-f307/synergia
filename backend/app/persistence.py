from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class ProcessingPersistenceError(ValueError):
    """Raised when a processing unit cannot be mapped safely to the database."""


class PostgresProcessingRepository:
    """Persist each consolidated Workorder in an independent transaction."""

    def __init__(self, database_url: str, connect: Callable | None = None) -> None:
        self.database_url = database_url
        self._connector = connect or psycopg.connect

    def _connect(self):
        return self._connector(self.database_url, row_factory=dict_row)

    def persist(self, execution_id: str, processing: Mapping[str, Any]) -> dict:
        if processing.get("execution_id") != execution_id:
            raise ProcessingPersistenceError(
                "O processamento deve pertencer à execução persistida"
            )
        consolidation = processing.get("consolidation", {})
        classifications = processing.get("classifications", {})
        confirmed: list[str] = []
        failures: list[dict[str, str]] = []
        for workorder in sorted(
            consolidation.get("workorders", []),
            key=lambda item: str(item["workorder_number"]),
        ):
            number = str(workorder["workorder_number"])
            events = [
                item
                for item in classifications.get("current_classifications", [])
                if item.get("workorder_number") == number
            ]
            evaluations = [
                item
                for item in classifications.get("rule_evaluations", [])
                if item.get("workorder_number") == number
            ]
            try:
                with self._connect() as connection:
                    self._persist_workorder(
                        connection,
                        execution_id,
                        workorder,
                        events,
                        evaluations,
                    )
                confirmed.append(number)
            except Exception as exc:
                failure = {"workorder_number": number, "reason": str(exc)}
                failures.append(failure)
                self._record_failure(execution_id, failure)
        return {
            "confirmed_workorders": confirmed,
            "failed_workorders": failures,
        }

    def _record_failure(self, execution_id: str, failure: dict[str, str]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO synergia.audit_events
                    (execution_id, entity_type, entity_id, event_type, payload)
                VALUES (%s, 'workorder', %s, 'processing_persistence_failed', %s)
                """,
                (
                    execution_id,
                    failure["workorder_number"],
                    Jsonb({"reason": failure["reason"]}),
                ),
            )

    @staticmethod
    def _origins(workorder: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [
            origin
            for values in workorder.get("provenance", {}).values()
            for origin in values
            if origin.get("source_file_id") is not None
        ]

    @classmethod
    def _source_file_id(
        cls, workorder: Mapping[str, Any], *, field: str | None = None, value=None
    ) -> int:
        origins = cls._origins(workorder)
        matching = [
            origin
            for origin in origins
            if (field is None or origin.get("field") == field)
            and (value is None or str(origin.get("value")) == str(value))
        ]
        candidates = matching or origins
        if not candidates:
            raise ProcessingPersistenceError("Workorder sem arquivo de proveniência")
        return min(int(origin["source_file_id"]) for origin in candidates)

    def _persist_workorder(
        self,
        connection,
        execution_id: str,
        workorder: Mapping[str, Any],
        events: list[dict[str, Any]],
        evaluations: list[dict[str, Any]],
    ) -> None:
        number = str(workorder["workorder_number"])
        source_file_id = self._source_file_id(workorder)
        organization_ids: list[int] = []
        for code in workorder.get("organization_codes", []):
            row = connection.execute(
                """
                INSERT INTO synergia.organizations
                    (organization_code, execution_id, source_file_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (execution_id, organization_code) DO UPDATE
                    SET organization_code = EXCLUDED.organization_code
                RETURNING id
                """,
                (
                    code,
                    execution_id,
                    self._source_file_id(
                        workorder, field="organization_code", value=code
                    ),
                ),
            ).fetchone()
            organization_ids.append(row["id"])
        row = connection.execute(
            """
            INSERT INTO synergia.workorders (
                workorder_number, organization_id, execution_id, source_file_id,
                processing_status, planned_quantity, produced_quantity,
                received_quantity, released_quantity, pending_quantity,
                retained_quantity, partially_released
            ) VALUES (%s, %s, %s, %s, 'consolidated', %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                number,
                organization_ids[0] if len(organization_ids) == 1 else None,
                execution_id,
                source_file_id,
                workorder.get("planned_quantity"),
                workorder.get("produced_quantity"),
                workorder.get("received_quantity"),
                workorder.get("released_quantity"),
                workorder.get("pending_quantity"),
                workorder.get("retained_quantity"),
                workorder.get("partially_released"),
            ),
        ).fetchone()
        workorder_id = row["id"]
        lot_ids = self._persist_lots(connection, execution_id, workorder_id, workorder)
        serial_ids = self._persist_serials(
            connection, execution_id, workorder_id, workorder, lot_ids
        )
        self._persist_provenance(connection, execution_id, workorder_id, workorder)
        classification_ids = self._persist_classifications(
            connection,
            execution_id,
            workorder_id,
            source_file_id,
            lot_ids,
            serial_ids,
            events,
        )
        self._persist_evaluations(connection, execution_id, workorder_id, evaluations)
        self._persist_operational_events(
            connection,
            execution_id,
            workorder_id,
            source_file_id,
            lot_ids,
            serial_ids,
            events,
            classification_ids,
        )
        connection.execute(
            """
            INSERT INTO synergia.audit_events
                (execution_id, source_file_id, entity_type, entity_id,
                 event_type, payload)
            VALUES (%s, %s, 'workorder', %s, 'processing_unit_persisted', %s)
            """,
            (
                execution_id,
                source_file_id,
                number,
                Jsonb(
                    {
                        "classification_count": len(events),
                        "rule_evaluation_count": len(evaluations),
                    }
                ),
            ),
        )

    def _persist_lots(self, connection, execution_id, workorder_id, workorder):
        result: dict[str, int] = {}
        for number in workorder.get("lot_numbers", []):
            row = connection.execute(
                """
                INSERT INTO synergia.lots
                    (lot_number, workorder_id, execution_id, source_file_id)
                VALUES (%s, %s, %s, %s) RETURNING id
                """,
                (
                    number,
                    workorder_id,
                    execution_id,
                    self._source_file_id(workorder, field="lot_number", value=number),
                ),
            ).fetchone()
            result[str(number)] = row["id"]
        return result

    def _persist_serials(
        self, connection, execution_id, workorder_id, workorder, lot_ids
    ):
        result: dict[str, tuple[int, int | None]] = {}
        facts = workorder.get("classification_facts", [])
        for number in workorder.get("serial_numbers", []):
            related = [
                fact for fact in facts if str(fact.get("serial_number")) == str(number)
            ]
            lots = {
                str(fact["lot_number"])
                for fact in related
                if fact.get("lot_number") not in (None, "")
            }
            containers = {
                str(fact["container_number"])
                for fact in related
                if fact.get("container_number") not in (None, "")
            }
            if len(lots) > 1 or len(containers) > 1:
                raise ProcessingPersistenceError(
                    f"Serial {number} possui relacionamentos incompatíveis"
                )
            lot_id = lot_ids.get(next(iter(lots))) if lots else None
            row = connection.execute(
                """
                INSERT INTO synergia.serials (
                    serial_number, container_number, workorder_id, lot_id,
                    execution_id, source_file_id
                ) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    number,
                    next(iter(containers)) if containers else None,
                    workorder_id,
                    lot_id,
                    execution_id,
                    self._source_file_id(
                        workorder, field="serial_number", value=number
                    ),
                ),
            ).fetchone()
            result[str(number)] = (row["id"], lot_id)
        return result

    def _persist_provenance(
        self, connection, execution_id, workorder_id, workorder
    ) -> None:
        for field, origins in workorder.get("provenance", {}).items():
            for origin in origins:
                connection.execute(
                    """
                    INSERT INTO synergia.consolidated_field_provenance (
                        execution_id, workorder_id, source_file_id, field_name,
                        source, sheet_name, row_number, observed_value
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        execution_id,
                        workorder_id,
                        origin["source_file_id"],
                        field,
                        origin["source"],
                        origin.get("sheet"),
                        origin.get("row"),
                        Jsonb(origin.get("value")),
                    ),
                )

    def _persist_classifications(
        self,
        connection,
        execution_id,
        workorder_id,
        default_source_file_id,
        lot_ids,
        serial_ids,
        events,
    ):
        result: dict[str, tuple[int | None, int | None, int]] = {}
        for event in events:
            serial = serial_ids.get(str(event.get("serial_number")))
            serial_id = serial[0] if serial else None
            lot_id = lot_ids.get(str(event.get("lot_number")))
            if lot_id is None and serial:
                lot_id = serial[1]
            evidence = event.get("evidence", {})
            source_file_id = int(
                evidence.get("source_file_id") or default_source_file_id
            )
            connection.execute(
                """
                INSERT INTO synergia.classifications (
                    classification_id, execution_id, workorder_id, lot_id,
                    serial_id, source_file_id, rule_id, rule_catalog_version,
                    state, entity_type, entity_id, justification, reason,
                    data_quality, priority, priority_score, responsible_area,
                    occurred_at, classified_at, evidence
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    event["classification_id"],
                    execution_id,
                    workorder_id,
                    lot_id,
                    serial_id,
                    source_file_id,
                    event["rule_id"],
                    event["rule_catalog_version"],
                    event["state"],
                    event["entity_type"],
                    str(event["entity_id"]),
                    event["justification"],
                    event.get("reason"),
                    event["data_quality"],
                    event["priority"],
                    event["priority_score"],
                    event.get("responsible_area"),
                    event.get("occurred_at"),
                    event["classified_at"],
                    Jsonb(evidence),
                ),
            )
            result[event["classification_id"]] = (lot_id, serial_id, source_file_id)
        return result

    def _persist_evaluations(
        self, connection, execution_id, workorder_id, evaluations
    ) -> None:
        for evaluation in evaluations:
            evidence = {
                key: evaluation.get(key)
                for key in ("source", "sheet", "row")
                if evaluation.get(key) is not None
            }
            connection.execute(
                """
                INSERT INTO synergia.rule_evaluations (
                    execution_id, workorder_id, source_file_id, rule_id,
                    rule_catalog_version, result, justification, evidence
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    execution_id,
                    workorder_id,
                    evaluation.get("source_file_id"),
                    evaluation["rule_id"],
                    evaluation["rule_catalog_version"],
                    evaluation["result"],
                    evaluation["justification"],
                    Jsonb(evidence),
                ),
            )

    def _persist_operational_events(
        self,
        connection,
        execution_id,
        workorder_id,
        default_source_file_id,
        lot_ids,
        serial_ids,
        events,
        classification_ids,
    ) -> None:
        for event in events:
            lot_id, serial_id, source_file_id = classification_ids[
                event["classification_id"]
            ]
            rule_id = event["rule_id"]
            if rule_id == "post_release_hold":
                connection.execute(
                    """
                    INSERT INTO synergia.holds (
                        serial_id, workorder_id, execution_id, source_file_id,
                        reason, status, post_release, classification_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, true, %s)
                    """,
                    (
                        serial_id,
                        workorder_id,
                        execution_id,
                        source_file_id,
                        event.get("reason"),
                        "active" if event["state"] == "active" else "released",
                        event["classification_id"],
                    ),
                )
            if rule_id in {"oqc_pass", "oqc_pending", "oqc_hold"}:
                decision = {
                    "oqc_pass": "approved",
                    "oqc_pending": "pending",
                    "oqc_hold": "rejected",
                }[rule_id]
                connection.execute(
                    """
                    INSERT INTO synergia.oqc_decisions (
                        workorder_id, lot_id, serial_id, execution_id,
                        source_file_id, decision_state, reason, decided_at,
                        classification_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        workorder_id,
                        lot_id,
                        serial_id,
                        execution_id,
                        source_file_id,
                        decision,
                        event.get("reason"),
                        event.get("occurred_at"),
                        event["classification_id"],
                    ),
                )
            if event["state"] == "active" and rule_id != "oqc_pass":
                connection.execute(
                    """
                    INSERT INTO synergia.pending_items (
                        workorder_id, lot_id, serial_id, execution_id,
                        source_file_id, category, reason, status,
                        classification_id, rule_id, rule_catalog_version,
                        priority, priority_score, responsible_area, evidence
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', %s,
                              %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        workorder_id,
                        lot_id,
                        serial_id,
                        execution_id,
                        source_file_id,
                        rule_id,
                        event.get("reason"),
                        event["classification_id"],
                        rule_id,
                        event["rule_catalog_version"],
                        event["priority"],
                        event["priority_score"],
                        event.get("responsible_area"),
                        Jsonb(event.get("evidence", {})),
                    ),
                )
