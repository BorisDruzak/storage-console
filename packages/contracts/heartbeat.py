from .common import Code, Identity, NonNegative32, Record


class HeartbeatRecord(Record):
    version: Code
    cursor: Identity | None = None
    lag_seconds: NonNegative32 | None = None
    error_code: Code | None = None
