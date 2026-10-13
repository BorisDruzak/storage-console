from pydantic import Field

from .audit import AuditHealth
from .common import Code, Identity, NonNegative32, Record


class HeartbeatRecord(Record):
    version: Code
    cursor: Identity | None = None
    lag_seconds: NonNegative32 | None = None
    error_code: Code | None = None
    audit: AuditHealth | None = Field(default=None, exclude_if=lambda value: value is None)
