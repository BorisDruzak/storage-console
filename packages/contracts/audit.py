"""Versioned minimal Windows Security evidence contracts; no raw XML or invented confidence."""

import json
from hashlib import sha256
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .common import Contract

Text = Annotated[str, Field(min_length=1, max_length=32768)]
Number = Annotated[int, Field(ge=0, le=2**64 - 1, strict=True)]


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    host_id: UUID
    boot_id: Text
    generation: UUID
    channel: Literal["Security"] = "Security"
    record_id: Annotated[int, Field(gt=0, le=2**63 - 1)]
    provider: UUID
    event_id: Literal[4663, 4660, 4624, 1102]
    version: Annotated[int, Field(ge=0, le=3)]
    occurred_at: AwareDatetime
    sid: Text | None = None
    domain: Text | None = None
    account: Text | None = None
    logon_id: Number | None = None
    handle_id: Number | None = None
    process_id: Number | None = None
    process_name: Text | None = None
    object_type: Text | None = None
    path: Text | None = None
    access_mask: Number | None = None
    logon_type: Number | None = None
    client_ip: Text | None = None
    workstation: Text | None = None
    quality: Literal["COMPLETE", "PARTIAL"] = "PARTIAL"
    volume_id: Text | None = None
    path_quality: Literal["UNKNOWN"] = "UNKNOWN"
    linked_record_ids: list[int] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def supported_extended_version(self) -> Self:
        if self.version == 3 and self.event_id != 4624:
            raise ValueError("AUDIT_EVENT_VERSION_UNSUPPORTED")
        return self

    def digest(self) -> str:
        return sha256(
            json.dumps(
                self.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()


class AuditInput(AuditEvent):
    digest_value: Annotated[str, Field(pattern="^[0-9a-f]{64}$")] = Field(alias="digest")

    def event(self) -> AuditEvent:
        return AuditEvent.model_validate(self.model_dump(exclude={"digest_value"}))

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.event().digest() != self.digest_value:
            raise ValueError("AUDIT_DIGEST_INVALID")
        if self.event_id == 4660 and self.path is not None:
            raise ValueError("AUDIT_DELETE_HAS_NO_PATH")
        if self.event_id == 4624 and self.path is not None:
            raise ValueError("AUDIT_LOGON_HAS_NO_PATH")
        for value in (self.sid, self.account, self.domain, self.volume_id, self.boot_id):
            if value is not None and len(value) > 255:
                raise ValueError("AUDIT_FIELD_TOO_LONG")
        return self


class AuditBatch(Contract):
    collector_id: UUID
    batch_id: Annotated[str, Field(min_length=1, max_length=255)]
    schema_version: Literal[1]
    sent_at: AwareDatetime
    records: Annotated[list[AuditInput], Field(min_length=1, max_length=512)]


class AuditHealth(Contract):
    configured: bool
    state: Literal["NOT_CONFIGURED", "OBSERVE", "HEALTHY", "GAP", "BACKPRESSURE", "ERROR"]
    host_id: UUID
    generation: UUID | None = None
    boot_id: str | None = Field(default=None, max_length=255)
    gap: str | None = Field(default=None, max_length=64)
    last_collected_at: AwareDatetime | None = None
    last_accepted_at: AwareDatetime | None = None
    bookmark_age_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    remaining_record_margin: Annotated[int, Field(ge=0)] | None = None
    read_count: Annotated[int, Field(ge=0)] = 0
    filtered_count: Annotated[int, Field(ge=0)] = 0
    backlog_count: Annotated[int, Field(ge=0)] = 0
    backlog_bytes: Annotated[int, Field(ge=0)] = 0
    quarantine: bool = False
    error_code: str | None = Field(default=None, max_length=64)
    policy_verified: bool = False
    sacl_verified: bool = False
    readiness_complete: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    readiness_stale: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    readiness_checked_at: AwareDatetime | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    readiness_objects: Annotated[int, Field(ge=0, le=100000)] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    readiness_age_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    readiness_duration_seconds: (
        Annotated[float, Field(ge=0, le=30, allow_inf_nan=False)] | None
    ) = Field(default=None, exclude_if=lambda value: value is None)
    readiness_error: str | None = Field(
        default=None, max_length=64, exclude_if=lambda value: value is None
    )


class AuditStream(Contract):
    collector_id: UUID | None = None
    enabled: bool = False
    state: Literal[
        "NOT_CONFIGURED", "UNKNOWN", "HEALTHY", "STALE", "GAP", "ERROR", "OBSERVE", "BACKPRESSURE"
    ]
    evaluated_at: AwareDatetime
    reported_at: AwareDatetime | None = None
    accepted_at: AwareDatetime | None = None
    diagnostics: AuditHealth | None = None


class AuditSearch(Contract):
    source_id: UUID | None = None
    event_id: Literal[4663, 4660, 4624] | None = None
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    sid: str | None = Field(default=None, min_length=1, max_length=255)
    account: str | None = Field(default=None, min_length=1, max_length=255)
    client_ip: str | None = Field(default=None, min_length=1, max_length=255)
    file_id: str | None = Field(default=None, min_length=1, max_length=255)
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)


class AuditRecordView(Contract):
    id: UUID
    source_id: UUID
    audit_collector_id: UUID
    first_received_at: AwareDatetime
    digest: str
    evidence: AuditEvent
    numeric_fields: dict[str, str]


class AuditPage(Contract):
    items: list[AuditRecordView]
    limit: int
    offset: int
    has_more: bool
    evaluated_at: AwareDatetime


class AuditCandidateView(Contract):
    method: str
    classification: str
    reason: str
    rule_version: str
    evidence: AuditRecordView


class AuditActor(Contract):
    sid: str
    account: str | None
    domain: str | None
    logon_id: str
    host_id: UUID
    boot_id: str
    client_ip: str | None
    workstation: str | None
    identity_evidence_id: UUID


class ChangeAudit(Contract):
    change_id: UUID
    object_id: UUID | None
    classification: Literal[
        "CORRELATED_HIGH", "ACCESS_OBSERVED", "AMBIGUOUS", "UNKNOWN", "GAP", "NOT_CONFIGURED"
    ]
    reason: str
    rule_version: str | None
    actor: AuditActor | None
    candidates: list[AuditCandidateView]
    stream: AuditStream


class AuditObject(Contract):
    object_id: UUID
    source_id: UUID
    file_id: str
    volume_identity: str
