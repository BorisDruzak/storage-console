"""Bounded, value-free decoding of documented USN V2/V3 records."""

import struct
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

MAX_READ_BYTES = 1024 * 1024
USN_CODES = frozenset(
    {
        "USN_MALFORMED", "USN_UNSUPPORTED", "USN_UNAVAILABLE", "USN_ACCESS_DENIED",
        "USN_VOLUME_LOST", "CONTINUITY_GAP", "USN_STATE_INVALID", "USN_BOOTSTRAP",
        "USN_PATH_UNKNOWN", "USN_CAPACITY", "USN_STALE", "USN_LAG",
    }
)


class UsnError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code if code in USN_CODES else "USN_UNAVAILABLE"
        super().__init__(self.code)


@dataclass(frozen=True)
class UsnRecord:
    file_id: str
    parent_id: str
    usn: int
    occurred_at: datetime
    reason: int
    attributes: int
    name: str


def parse_buffer(data: bytes) -> tuple[int, tuple[UsnRecord, ...]]:
    """Parse the entire read response or fail; never silently consume bad records."""
    if not isinstance(data, bytes) or not 8 <= len(data) <= MAX_READ_BYTES:
        raise UsnError("USN_MALFORMED")
    cursor = struct.unpack_from("<q", data)[0]
    if cursor < 0:
        raise UsnError("USN_MALFORMED")
    records = []
    offset, previous = 8, -1
    while offset < len(data):
        if len(data) - offset < 8:
            raise UsnError("USN_MALFORMED")
        size, version, _minor = struct.unpack_from("<IHH", data, offset)
        if version not in (2, 3):
            raise UsnError("USN_UNSUPPORTED")
        identity_bytes, header = (8, 60) if version == 2 else (16, 76)
        if size < header or size % 8 or size > len(data) - offset:
            raise UsnError("USN_MALFORMED")
        start = offset + 8
        file_id = data[start:start + identity_bytes].ljust(16, b"\0").hex()
        start += identity_bytes
        parent_id = data[start:start + identity_bytes].ljust(16, b"\0").hex()
        start += identity_bytes
        usn, ticks, reason, _source, _security, attributes, length, name_offset = (
            struct.unpack_from("<qqIIIIHH", data, start)
        )
        if (
            not previous < usn < cursor or ticks <= 0 or name_offset < header
            or name_offset % 2 or not 2 <= length <= 510 or length % 2
            or name_offset + length > size
        ):
            raise UsnError("USN_MALFORMED")
        try:
            name = data[offset + name_offset:offset + name_offset + length].decode("utf-16-le")
            stamp = datetime(1601, 1, 1, tzinfo=UTC) + timedelta(microseconds=ticks // 10)
        except (UnicodeError, OverflowError):
            raise UsnError("USN_MALFORMED") from None
        if name in (".", "..") or any(c in name for c in "\\/\0"):
            raise UsnError("USN_MALFORMED")
        records.append(UsnRecord(file_id, parent_id, usn, stamp, reason, attributes, name))
        previous, offset = usn, offset + size
    return cursor, tuple(records)
