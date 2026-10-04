import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, SecretStr, field_serializer, field_validator

from .common import Contract

SourceType = Literal["FILESERVER", "PVE", "PBS"]
CollectorType = Literal["WINDOWS", "PVE", "PBS"]
SourceText = Annotated[str, Field(min_length=1, max_length=255, strict=True)]
Cadence = Annotated[int, Field(ge=1, le=86400, strict=True)]


class CreateSource(Contract):
    source_type: SourceType
    hostname: SourceText
    fqdn: SourceText | None = None
    instance_id: SourceText
    expected_cadence_seconds: Cadence = 60

    @field_validator("hostname", "fqdn", "instance_id")
    @classmethod
    def bounded_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value != value.strip() or not value.isprintable():
            raise ValueError("Invalid source identity")
        try:
            size = len(value.encode("utf-8"))
        except UnicodeEncodeError:
            raise ValueError("Invalid source identity") from None
        if size > 1020:
            raise ValueError("Invalid source identity")
        return value


class SourceRegistration(CreateSource):
    id: UUID
    created_at: AwareDatetime


class CreateCollector(Contract):
    collector_type: CollectorType


class RotateCollector(Contract):
    pass


class SetCollectorEnabled(Contract):
    enabled: Annotated[bool, Field(strict=True)]


class CollectorView(Contract):
    id: UUID
    source_node_id: UUID
    collector_type: CollectorType
    version: str | None
    enabled: Annotated[bool, Field(strict=True)]
    created_at: AwareDatetime
    last_seen_at: AwareDatetime | None


class CollectorCredential(CollectorView):
    token: SecretStr = Field(
        repr=False,
        json_schema_extra={"minLength": 43, "maxLength": 43, "pattern": "^[A-Za-z0-9_-]{43}$"},
    )

    @field_validator("token")
    @classmethod
    def generated_token(cls, value: SecretStr) -> SecretStr:
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", value.get_secret_value()) is None:
            raise ValueError("Invalid collector credential")
        return value

    @field_serializer("token", when_used="json")
    def token_json(self, value: SecretStr) -> str:
        # Only the enrollment/rotation wire response is allowed to expose this value.
        return value.get_secret_value()
