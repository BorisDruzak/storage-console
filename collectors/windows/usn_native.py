"""Only QUERY/READ USN controls, on pinned volumes of explicitly configured roots."""

import ctypes
import struct
from dataclasses import dataclass

from packages.contracts.inventory import VolumeRecord

from .inventory import CaptureError, Scope
from .native import NativeInventory, _Api
from .usn import MAX_READ_BYTES, UsnError, UsnRecord, parse_buffer

QUERY_USN = 0x900F4
READ_USN = 0x900BB


def _error(code: int) -> UsnError:
    return UsnError({
        5: "USN_ACCESS_DENIED", 2: "USN_VOLUME_LOST", 3: "USN_VOLUME_LOST",
        21: "USN_VOLUME_LOST", 1167: "USN_VOLUME_LOST", 1178: "CONTINUITY_GAP",
        1179: "USN_UNAVAILABLE", 1181: "CONTINUITY_GAP", 87: "USN_UNSUPPORTED",
        1: "USN_UNSUPPORTED", 50: "USN_UNSUPPORTED",
    }.get(code, "USN_UNAVAILABLE"))


@dataclass(frozen=True)
class JournalInfo:
    journal_id: int
    first_usn: int
    next_usn: int
    lowest_valid_usn: int
    maximum_size: int
    allocation_delta: int

    def require_cursor(self, journal_id: int, cursor: int) -> None:
        if (
            journal_id != self.journal_id or cursor < max(self.first_usn, self.lowest_valid_usn)
            or cursor > self.next_usn
        ):
            raise UsnError("CONTINUITY_GAP")


class JournalStream:
    def __init__(self, api: _Api, volume: str) -> None:
        self._api = api
        p, d = ctypes.c_void_p, ctypes.c_uint32
        api._bind("DeviceIoControl", [p, d, p, d, p, d, p, p], ctypes.c_int32)
        self._handle = api.functions["CreateFileW"](
            volume.rstrip("\\"), 0x80000000, 7, None, 3, 0, None
        )
        if self._handle in (None, ctypes.c_void_p(-1).value):
            raise _error(int(vars(ctypes)["get_last_error"]()))

    def close(self) -> None:
        if self._handle is not None:
            self._api.close(self._handle)
            self._handle = None

    def _control(self, code: int, request: bytes, size: int) -> bytes:
        if self._handle is None or code not in (QUERY_USN, READ_USN):
            raise UsnError("USN_UNAVAILABLE")
        supplied, result = ctypes.create_string_buffer(request), ctypes.create_string_buffer(size)
        used = ctypes.c_uint32()
        if not self._api.functions["DeviceIoControl"](
            self._handle, code, supplied if request else None, len(request), result,
            size, ctypes.byref(used), None,
        ):
            raise _error(int(vars(ctypes)["get_last_error"]()))
        if used.value > size:
            raise UsnError("USN_MALFORMED")
        return result.raw[:used.value]

    def query(self) -> JournalInfo:
        data = self._control(QUERY_USN, b"", 128)
        if len(data) < 56:
            raise UsnError("USN_MALFORMED")
        journal, first, next_usn, lowest, maximum, size, delta = struct.unpack_from(
            "<QqqqqQQ", data
        )
        if not 0 <= first <= next_usn <= maximum or lowest < 0 or size <= 0 or delta <= 0:
            raise UsnError("USN_MALFORMED")
        return JournalInfo(journal, first, next_usn, lowest, size, delta)

    def read(self, journal_id: int, cursor: int) -> tuple[int, tuple[UsnRecord, ...]]:
        self.query().require_cursor(journal_id, cursor)
        # BytesToWaitFor=0 prevents waiting for future journal data. Explicitly
        # request supported V2/V3 layouts; no FSCTL that changes journal state.
        request = struct.pack("<qIIQQQHH4x", cursor, 0xFFFFFFFF, 0, 0, 0, journal_id, 2, 3)
        next_usn, records = parse_buffer(self._control(READ_USN, request, MAX_READ_BYTES))
        if next_usn < cursor or any(record.usn < cursor for record in records):
            raise UsnError("USN_MALFORMED")
        return next_usn, records


class NativeJournal:
    def __init__(self, scope: Scope) -> None:
        self._api = _Api()
        volumes: dict[str, str] = {}
        for root in scope.roots:
            iterator = NativeInventory(api=self._api)._root(self._api, root)
            try:
                observation = next(iterator)
                record = observation.record
                if not isinstance(record, VolumeRecord) or record.filesystem != "NTFS":
                    raise UsnError("USN_UNSUPPORTED")
                volumes[record.unique_identity] = (
                    "\\\\?\\Volume{" + record.unique_identity[7:] + "}\\"
                )
            except CaptureError as error:
                raise UsnError("USN_ACCESS_DENIED" if error.code == "ACCESS_DENIED"
                               else "USN_VOLUME_LOST") from None
            finally:
                iterator.close()
        self._volumes = volumes

    @property
    def volumes(self) -> tuple[str, ...]:
        return tuple(sorted(self._volumes))

    def open(self, volume: str) -> JournalStream:
        if volume not in self._volumes:
            raise UsnError("USN_VOLUME_LOST")
        return JournalStream(self._api, self._volumes[volume])
