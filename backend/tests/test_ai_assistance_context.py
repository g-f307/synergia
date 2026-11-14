from __future__ import annotations

import copy
import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from pydantic import ValidationError

from app.ai_assistance_context import (
    CONTEXT_BYTES,
    CONTEXTS,
    TRUNCATIONS,
    ExecutionContextBuilder,
    canonical_bytes,
    serialize_snapshot,
)
from app.ai_assistance_context_models import (
    SECTIONS,
    ContextCounts,
    ExecutionAssistanceContext,
)
from app.ai_assistance_context_policy import normalized_text
from app.authorization import ActorContext
from app.errors import ApiError

pytestmark = pytest.mark.security
EXECUTION = UUID("00000000-0000-4000-8000-000000000186")
ORG = UUID("00000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 11, 14, tzinfo=UTC)
FIXTURES = Path(__file__).parent / "fixtures"


def actor(scopes=frozenset({ORG})):
    return ActorContext(uuid4(), uuid4(), uuid4(), {"execution.read": scopes}, uuid4())


class Reader:
    def __init__(self, number=1, status="completed"):
        self.calls = []
        self.row = {
            "execution_id": str(EXECUTION),
            "organization_id": ORG,
            "source": "OWM",
            "status": status,
            "attempt": 1,
            "pipeline_version": "1.0.0",
            "rule_catalog_version": "1.0.0",
            "started_at": NOW,
            "finished_at": NOW + timedelta(seconds=1),
        }
        self.collections = {section: [] for section in SECTIONS}
        for index in range(number):
            self.collections["divergences"].append(
                {
                    "id": index,
                    "severity": "error",
                    "code": "invalid_value",
                    "scope": "record",
                    "occurred_at": NOW,
                }
            )
            self.collections["pending_items"].append(
                {
                    "id": index,
                    "rule_id": "oqc_pending",
                    "status": "open",
                    "priority_score": None,
                    "created_at": NOW,
                }
            )
            self.collections["classifications"].append(
                {
                    "id": str(index),
                    "rule_id": "oqc_pending",
                    "state": "active",
                    "data_quality": "partial",
                    "priority_score": 40,
                    "classified_at": NOW,
                }
            )
            self.collections["evidences"].append(
                {
                    "id": index,
                    "extension": "csv",
                    "size_bytes": None,
                    "sha256": "a" * 64,
                    "available": True,
                }
            )
            self.collections["state_history"].append(
                {
                    "id": index,
                    "from_state": "validating",
                    "to_state": "completed",
                    "state_version": index,
                    "occurred_at": NOW,
                }
            )

    @contextmanager
    def snapshot(self):
        self.calls.append("snapshot")
        yield self
        self.calls.append("closed")

    def subject(self, execution, scopes):
        self.calls.append(("subject", execution, scopes))
        return self.row

    def counts(self, execution, organization):
        self.calls.append(("counts", execution, organization))
        counts = {key: 0 for key in ContextCounts.model_fields}
        counts.update(
            files=len(self.collections["evidences"]),
            files_received=len(self.collections["evidences"]),
            files_accepted=len(self.collections["evidences"]),
            errors=len(self.collections["divergences"]),
            pending_items=len(self.collections["pending_items"]),
            classifications=len(self.collections["classifications"]),
        )
        return counts

    def items(self, section, execution, organization):
        self.calls.append((section, execution, organization))
        return self.collections[section]


def build(reader=None, generated_at=NOW):
    return ExecutionContextBuilder(reader or Reader()).build(
        actor(),
        EXECUTION,
        generated_at=generated_at,
    )


@pytest.mark.parametrize(
    "name,number",
    [
        ("complete", 1),
        ("empty", 0),
        ("insufficient", 1),
        ("truncated", 21),
    ],
)
def test_versioned_snapshots_and_known_hashes(name, number):
    reader = Reader(number)
    if name == "insufficient":
        for section in SECTIONS[:3]:
            reader.collections[section] = []
        reader.collections["evidences"][0]["available"] = False
    context = build(reader)
    expected = json.loads((FIXTURES / f"ai_context_1_0_0_{name}.json").read_text())
    assert context.model_dump(mode="json") == expected
    assert (
        hashlib.sha256(canonical_bytes(context)).hexdigest()
        == expected["context_sha256"]
    )
    assert len(serialize_snapshot(context)) <= 8192


def test_hash_ignores_generation_time_and_normalizes_utc():
    first = build()
    second_reader = Reader()
    for key in ("started_at", "finished_at"):
        second_reader.row[key] = second_reader.row[key].astimezone(
            timezone(timedelta(hours=-4))
        )
    second = build(second_reader, NOW + timedelta(days=1, microseconds=123))
    assert first.generated_at != second.generated_at
    assert canonical_bytes(first) == canonical_bytes(second)
    assert first.context_sha256 == second.context_sha256
    assert len(serialize_snapshot(first)) == len(serialize_snapshot(second))
    assert first.model_dump(mode="json")["generated_at"].endswith(".000000Z")


def test_truncation_is_deterministic_and_preserves_highest_ranked_items():
    first, second = build(Reader(21)), build(Reader(21))
    assert canonical_bytes(first) == canonical_bytes(second)
    assert first.truncated_sections == list(SECTIONS)
    assert len(first.divergences) == 20
    assert not first.state_history
    assert len(first.evidence_refs()) == sum(len(getattr(first, s)) for s in SECTIONS)


def test_empty_and_history_only_are_insufficient():
    reader = Reader()
    for section in SECTIONS[:-1]:
        reader.collections[section] = []
    context = build(reader)
    assert context.sufficiency == "insufficient"
    assert len(context.state_history) == 1


@pytest.mark.parametrize(
    "status,lifecycle",
    [
        ("completed", "completed"),
        ("duplicate", "completed"),
        ("completed_with_errors", "partial"),
        ("failed", "failed"),
        ("validation_failed", "failed"),
        ("cancelled", "failed"),
    ],
)
def test_terminal_statuses(status, lifecycle):
    assert build(Reader(status=status)).lifecycle == lifecycle


@pytest.mark.parametrize(
    "status",
    [
        "pending",
        "validating",
        "normalizing",
        "consolidating",
        "applying_rules",
        "reprocessing",
    ],
)
def test_active_execution_denied_before_detail_queries(status):
    reader = Reader(status=status)
    with pytest.raises(ApiError) as failure:
        build(reader)
    assert failure.value.status_code == 409
    assert not any(isinstance(c, tuple) and c[0] == "counts" for c in reader.calls)


@pytest.mark.parametrize("missing", [False, True])
def test_cross_tenant_and_nonexistent_are_identical(missing):
    reader = Reader()
    reader.row = None if missing else {**reader.row, "organization_id": uuid4()}
    with pytest.raises(ApiError) as failure:
        build(reader)
    assert (failure.value.status_code, failure.value.code) == (
        404,
        "resource_not_found",
    )
    assert len(reader.calls) == 2  # transaction + authorized subject, never details


def test_missing_permission_does_not_open_connection():
    reader = Reader()
    with pytest.raises(ApiError) as failure:
        ExecutionContextBuilder(reader).build(actor(frozenset()), EXECUTION)
    assert failure.value.status_code == 403
    assert not reader.calls


def test_projection_excludes_sensitive_free_text_and_unknown_vocabulary(caplog):
    reader = Reader()
    forbidden = "user@example.invalid /private/file.csv access_token=private-secret"
    reader.row.update(user_email=forbidden, actor_identifier=forbidden)
    for rows in reader.collections.values():
        rows[0].update(
            reason=forbidden,
            details={"original_values": forbidden},
            storage_key=forbidden,
            original_file_name=forbidden,
        )
    reader.collections["divergences"][0]["code"] = forbidden
    reader.collections["pending_items"][0]["rule_id"] = forbidden
    reader.collections["classifications"][0]["id"] = forbidden
    reader.collections["evidences"][0]["extension"] = forbidden
    context = build(reader)
    serialized = serialize_snapshot(context).decode()
    for marker in (
        "user@example",
        "/private",
        "private-secret",
        "storage_key",
        "original_values",
        "original_file_name",
        "actor_identifier",
    ):
        assert marker not in serialized
        assert marker not in caplog.text
    assert context.divergences[0].code is None
    assert context.pending_items[0].rule_id is None
    assert context.evidences[0].safe_name.endswith(".bin")


@pytest.mark.parametrize(
    "text,limit,expected",
    [
        ("Não\x00há\nliberação", 64, "Não há liberação"),
        ("a" * 64, 64, "a" * 64),
        ("a" * 65, 64, None),
        ("Não remover", 5, None),
        (None, 64, None),
        ("\x00", 64, None),
    ],
)
def test_normalization_never_slices_text_or_negations(text, limit, expected):
    assert normalized_text(text, limit) == expected


def test_mutation_is_detected_and_invalid_persisted_data_is_not_exposed(caplog):
    context = build()
    context.divergences.clear()
    with pytest.raises(ValueError, match="integrity"):
        serialize_snapshot(context)
    reader = Reader()
    reader.row["pipeline_version"] = "private-secret@example.invalid"
    with pytest.raises(ApiError) as failure:
        build(reader)
    assert failure.value.status_code == 422
    assert "private-secret" not in str(failure.value)
    assert "private-secret" not in caplog.text


def test_schema_is_strict_and_versioned():
    context = build().model_dump(mode="json")
    for field, value in (
        ("secret", "forbidden"),
        ("lifecycle", "active"),
        ("contract_version", "2.0.0"),
        ("sufficiency", "insufficient"),
    ):
        damaged = copy.deepcopy(context)
        damaged[field] = value
        with pytest.raises(ValidationError):
            ExecutionAssistanceContext.model_validate_json(json.dumps(damaged))
    context["counts"]["files"] = "0"
    with pytest.raises(ValidationError):
        ExecutionAssistanceContext.model_validate_json(json.dumps(context))


def test_internal_schema_matches_versioned_artifact():
    path = (
        FIXTURES.parents[2]
        / "docs/contracts/execution-assistance-context-1.0.0.schema.json"
    )
    assert ExecutionAssistanceContext.model_json_schema() == json.loads(
        path.read_text()
    )


def test_database_failure_is_sanitized_and_metrics_have_only_bounded_labels(caplog):
    class FailedReader(Reader):
        def counts(self, execution, organization):
            raise psycopg.OperationalError(
                "private-token user@example.invalid /private"
            )

    with pytest.raises(ApiError) as failure:
        build(FailedReader())
    assert failure.value.status_code == 503
    assert "private" not in str(failure.value)
    assert "private" not in caplog.text
    build()
    for collector in (CONTEXTS, CONTEXT_BYTES, TRUNCATIONS):
        for metric in collector.collect():
            for sample in metric.samples:
                assert set(sample.labels) <= {"sufficiency", "section", "le"}


@pytest.mark.parametrize("section", SECTIONS)
def test_duplicate_references_and_wrong_prefix_are_rejected(section):
    payload = build().model_dump(mode="json")
    payload[section].append(copy.deepcopy(payload[section][0]))
    with pytest.raises(ValidationError, match="duplicate"):
        ExecutionAssistanceContext.model_validate_json(json.dumps(payload))
    payload = build().model_dump(mode="json")
    payload[section][0]["ref_id"] = "BAD-" + "0" * 32
    with pytest.raises(ValidationError):
        ExecutionAssistanceContext.model_validate_json(json.dumps(payload))
