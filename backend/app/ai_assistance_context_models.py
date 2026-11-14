"""Version 1.0.0 of the minimized, deterministic execution snapshot."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.ai_assistance_context_policy import ISSUE_CODES, LIFECYCLES, RULE_IDS
from app.ai_assistance_contract import StrictContract

CONTEXT_VERSION = "1.0.0"
SECTIONS = (
    "divergences",
    "pending_items",
    "classifications",
    "evidences",
    "state_history",
)
Section = Literal[
    "divergences", "pending_items", "classifications", "evidences", "state_history"
]
State = Literal[
    "pending",
    "validating",
    "validation_failed",
    "normalizing",
    "consolidating",
    "applying_rules",
    "completed",
    "completed_with_errors",
    "failed",
    "reprocessing",
    "duplicate",
    "cancelled",
]
Count = Annotated[int, Field(ge=0)]
Version = Annotated[str, Field(pattern=r"^\d{1,4}\.\d{1,4}\.\d{1,4}$")]
Ref = Annotated[str, Field(pattern=r"^(DIV|PEN|CLA|EVI|HIS)-[a-f0-9]{32}$")]


class ContextModel(StrictContract):
    @field_serializer("*", when_used="json", check_fields=False)
    def utc_dates(self, value):
        if isinstance(value, datetime):
            return (
                value.astimezone(UTC)
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
            )
        return value


class ContextSubject(ContextModel):
    execution_id: UUID
    organization_id: UUID
    source: (
        Literal["N-FP", "OWM", "GMES/OQC", "TMS", "WO Status", "Total Decision"] | None
    )
    status: State
    attempt: int = Field(ge=1)
    pipeline_version: Version
    rule_catalog_version: Version
    started_at: AwareDatetime
    finished_at: AwareDatetime | None

    @model_validator(mode="after")
    def coherent_dates(self):
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("invalid context chronology")
        return self


class ContextCounts(ContextModel):
    files: Count
    files_received: Count
    files_accepted: Count
    files_rejected: Count
    rows_read: Count
    valid_records: Count
    rejected_records: Count
    normalized_records: Count
    workorders: Count
    lots: Count
    serials: Count
    classifications: Count
    pending_items: Count
    errors: Count
    warnings: Count


class ContextDivergence(ContextModel):
    ref_id: Ref
    severity: Literal["error", "warning"]
    code: str | None = Field(
        max_length=64,
        json_schema_extra={"enum": [*sorted(ISSUE_CODES), None]},
    )
    scope: Literal["file", "structure", "record"]
    occurred_at: AwareDatetime

    @field_validator("code")
    @classmethod
    def known_code(cls, value):
        if value is not None and value not in ISSUE_CODES:
            raise ValueError("unknown context issue code")
        return value


class ContextPending(ContextModel):
    ref_id: Ref
    rule_id: str | None = Field(
        max_length=64,
        json_schema_extra={"enum": [*sorted(RULE_IDS), None]},
    )
    status: Literal["open", "resolved", "cancelled"]
    priority_score: int | None = Field(ge=0)
    created_at: AwareDatetime

    @field_validator("rule_id")
    @classmethod
    def known_rule(cls, value):
        if value is not None and value not in RULE_IDS:
            raise ValueError("unknown context rule")
        return value


class ContextClassification(ContextModel):
    ref_id: Ref
    rule_id: str | None = Field(
        max_length=64,
        json_schema_extra={"enum": [*sorted(RULE_IDS), None]},
    )
    state: Literal["active", "closed"]
    data_quality: Literal["complete", "partial"]
    priority_score: int = Field(ge=0)
    classified_at: AwareDatetime

    @field_validator("rule_id")
    @classmethod
    def known_rule(cls, value):
        return ContextPending.known_rule(value)


class ContextEvidence(ContextModel):
    ref_id: Ref
    safe_name: str = Field(pattern=r"^evidence-[a-f0-9]{32}\.(csv|json|xlsx|bin)$")
    evidence_type: Literal["source_file"]
    media_type: Literal[
        "text/csv",
        "application/json",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
    ]
    size_bytes: Count | None
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    available: bool


class ContextHistory(ContextModel):
    ref_id: Ref
    from_state: State | None
    to_state: State
    state_version: Count
    occurred_at: AwareDatetime


class ExecutionAssistanceContext(ContextModel):
    contract_version: Literal["1.0.0"]
    subject: ContextSubject
    lifecycle: Literal["completed", "partial", "failed"]
    counts: ContextCounts
    divergences: list[ContextDivergence] = Field(max_length=20)
    pending_items: list[ContextPending] = Field(max_length=20)
    classifications: list[ContextClassification] = Field(max_length=20)
    evidences: list[ContextEvidence] = Field(max_length=20)
    state_history: list[ContextHistory] = Field(max_length=10)
    sufficiency: Literal["sufficient", "insufficient"]
    truncated_sections: list[Section] = Field(max_length=5)
    generated_at: AwareDatetime
    context_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def unique_references(self):
        if LIFECYCLES.get(self.subject.status) != self.lifecycle:
            raise ValueError("incompatible execution lifecycle")
        sufficient = bool(
            self.divergences
            or self.pending_items
            or self.classifications
            or any(item.available for item in self.evidences)
        )
        if (self.sufficiency == "sufficient") != sufficient:
            raise ValueError("incompatible context sufficiency")
        prefixes = dict(zip(SECTIONS, ("DIV", "PEN", "CLA", "EVI", "HIS"), strict=True))
        refs = []
        for section, prefix in prefixes.items():
            for item in getattr(self, section):
                if not item.ref_id.startswith(prefix + "-"):
                    raise ValueError("reference prefix does not match section")
                refs.append(item.ref_id)
        if len(refs) != len(set(refs)):
            raise ValueError("duplicate context references")
        if self.truncated_sections != [
            s for s in SECTIONS if s in self.truncated_sections
        ]:
            raise ValueError("truncated sections must be unique and in canonical order")
        return self

    def evidence_refs(self) -> frozenset[str]:
        return frozenset(
            item.ref_id for section in SECTIONS for item in getattr(self, section)
        )
