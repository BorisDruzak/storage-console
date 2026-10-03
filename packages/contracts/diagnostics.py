from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from .common import Code, Identity, Record


class DiagnosticRecord(Record):
    trigger_type: Code
    first_event_at: AwareDatetime
    last_event_at: AwareDatetime
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    status: Literal["METADATA_ONLY", "AVAILABLE", "UNAVAILABLE"]
    storage_reference: Identity | None = None

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if not self.first_event_at <= self.occurred_at <= self.last_event_at:
            raise ValueError("Diagnostic trigger outside bundle interval")
        return self
