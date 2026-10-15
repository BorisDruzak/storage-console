"""Canonicalize only stable Win32 volume GUID aliases; never resolve a path."""

import re
from uuid import UUID


def canonical_volume_identity(value: str) -> str:
    if not value.lower().startswith("\\\\?\\volume"):
        return value
    match = re.fullmatch(
        r"\\\\\?\\Volume\{([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\}\\",
        value, re.IGNORECASE,
    )
    if match is None:
        raise ValueError("VOLUME_IDENTITY_INVALID")
    return "volume:" + str(UUID(match[1]))
