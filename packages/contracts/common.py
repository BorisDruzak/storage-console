from datetime import UTC, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

Identity = Annotated[str, Field(min_length=1, max_length=255)]
Code = Annotated[str, Field(min_length=1, max_length=64)]
NonNegative = Annotated[int, Field(ge=0, le=2**63 - 1, strict=True)]
NonNegative32 = Annotated[int, Field(ge=0, le=2**31 - 1, strict=True)]
Quality = Literal["COMPLETE", "PARTIAL", "STALE", "ESTIMATED", "UNAVAILABLE"]
HealthState = Literal["HEALTHY", "OBSERVE", "WARNING", "CRITICAL", "UNKNOWN", "NOT_APPLICABLE"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    @field_validator("*")
    @classmethod
    def normalize_utc(cls, value: object) -> object:
        if isinstance(value, datetime) and value.tzinfo is not None:
            return value.astimezone(UTC)
        return value


class Record(Contract):
    occurred_at: AwareDatetime


class BatchEnvelope[T: Record](Contract):
    collector_id: UUID
    batch_id: Identity
    schema_version: Literal[1]
    sent_at: AwareDatetime
    first_event_at: AwareDatetime
    last_event_at: AwareDatetime
    record_count: Annotated[int, Field(ge=1, le=10000, strict=True)]
    records: Annotated[list[T], Field(min_length=1, max_length=10000)]

    @field_validator("schema_version", mode="before")
    @classmethod
    def require_integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Schema version must be an integer")
        return value

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        if self.record_count != len(self.records):
            raise ValueError("Record count does not match records")
        if self.first_event_at > self.last_event_at:
            raise ValueError("Invalid event interval")
        if any(
            not self.first_event_at <= record.occurred_at <= self.last_event_at
            for record in self.records
        ):
            raise ValueError("Record outside declared interval")
        if self.first_event_at != min(
            record.occurred_at for record in self.records
        ) or self.last_event_at != max(record.occurred_at for record in self.records):
            raise ValueError("Event interval does not match record boundaries")
        return self
