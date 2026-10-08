from typing import Literal, Self

from pydantic import Field, model_validator

from .common import Code, Identity, Record
from .inventory import Path

EventType = Literal["CREATE", "WRITE", "RENAME", "DELETE", "METADATA_CHANGE", "SECURITY_CHANGE"]


class ChangeRecord(Record):
    volume_identity: Identity
    file_id: Identity
    parent_file_id: Identity | None = None
    event_type: EventType
    old_relative_path: Path | None = None
    new_relative_path: Path | None = None
    reason_mask: Code | None = None
    source_event_id: Identity | None = None
    path_quality: Literal["COMPLETE", "UNAVAILABLE"] = Field(
        default="COMPLETE", exclude_if=lambda value: value == "COMPLETE"
    )

    @model_validator(mode="after")
    def validate_paths(self) -> Self:
        if self.event_type == "RENAME" and self.path_quality == "COMPLETE" and (
            not self.old_relative_path or not self.new_relative_path
        ):
            raise ValueError("Rename requires old and new paths")
        return self
