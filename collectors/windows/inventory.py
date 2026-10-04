"""Private capture configuration and typed, value-free observation failures."""

import json
import re
from dataclasses import dataclass, field
from hashlib import sha256

from packages.contracts.inventory import (
    FileObjectRecord,
    InventoryRecord,
    ShareRecord,
    VolumeRecord,
)

CODES = frozenset(
    {
        "INVALID_SCOPE",
        "PLATFORM_UNSUPPORTED",
        "ACCESS_DENIED",
        "NOT_FOUND",
        "SHARING_VIOLATION",
        "REPARSE_POINT",
        "SCOPE_CHANGED",
        "NOT_DIRECTORY",
        "DEPTH_LIMIT",
        "NATIVE_FAILED",
        "METADATA_INVALID",
        "CAPACITY",
        "STOPPED",
        "STATE_MISMATCH",
    }
)
_DEVICE = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.IGNORECASE)


class CaptureError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code if code in CODES else "NATIVE_FAILED"
        super().__init__(self.code)


@dataclass(frozen=True)
class Scope:
    roots: tuple[str, ...] = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.roots) is not tuple or not 1 <= len(self.roots) <= 32:
            raise CaptureError("INVALID_SCOPE")
        normalized = []
        for root in self.roots:
            if not isinstance(root, str):
                raise CaptureError("INVALID_SCOPE")
            try:
                length = len(root.encode("utf-16-le")) // 2
            except UnicodeError:
                raise CaptureError("INVALID_SCOPE") from None
            if (
                not 3 <= length <= 32700
                or not re.match(r"^[A-Za-z]:\\", root)
                or any(ord(c) < 32 for c in root)
                or "/" in root
            ):
                raise CaptureError("INVALID_SCOPE")
            parts = root[3:].rstrip("\\").split("\\") if root[3:].rstrip("\\") else []
            if len(parts) > 64:
                raise CaptureError("INVALID_SCOPE")
            if any(
                not p
                or p in {".", ".."}
                or p.endswith((" ", "."))
                or any(c in p for c in ':*?"<>|')
                or _DEVICE.match(p)
                for p in parts
            ):
                raise CaptureError("INVALID_SCOPE")
            normalized.append(root[0].upper() + ":\\" + "\\".join(parts))
        folded = sorted(r.casefold().rstrip("\\") for r in normalized)
        if any(
            b == a or b.startswith(a + "\\")
            for index, a in enumerate(folded)
            for b in folded[index + 1 :]
        ):
            raise CaptureError("INVALID_SCOPE")
        object.__setattr__(self, "roots", tuple(normalized))

    @property
    def fingerprint(self) -> str:
        # Directory case can be significant on Windows. Normalize only the drive
        # and separators; configuration changes must not reuse another scope's state.
        values = sorted(self.roots)
        return sha256(json.dumps(values, ensure_ascii=True).encode()).hexdigest()


@dataclass(frozen=True)
class Observation:
    record: InventoryRecord | None = field(default=None, repr=False)
    error_code: str | None = None

    def __post_init__(self) -> None:
        if (
            (self.record is None) == (self.error_code is None)
            or self.record is not None
            and not isinstance(self.record, (VolumeRecord, ShareRecord, FileObjectRecord))
            or self.error_code is not None
            and self.error_code not in CODES
        ):
            raise CaptureError("METADATA_INVALID")
