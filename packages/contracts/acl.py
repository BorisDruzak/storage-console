from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .common import Code, Contract, Identity, NonNegative, Record
from .inventory import Path


class AceRecord(Contract):
    principal_identity: Identity
    ace_type: Literal["ALLOW", "DENY"]
    access_mask: NonNegative
    inherited: bool
    inheritance_flags: Code | None = None


class ACLRecord(Record):
    scope_identity: Path
    volume_identity: Identity | None = None
    file_id: Identity | None = None
    owner_identity: Identity | None = None
    dacl_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    inheritance_enabled: bool
    aces: Annotated[list[AceRecord], Field(max_length=4096)]

    @model_validator(mode="after")
    def complete_object_identity(self) -> Self:
        if (self.volume_identity is None) != (self.file_id is None):
            raise ValueError("Object identity requires both volume and file")
        return self
