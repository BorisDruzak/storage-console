"""Bounded pull subscription through native Windows Event Log APIs only."""

from __future__ import annotations

import ctypes
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import PureWindowsPath
from typing import Any
from xml.etree import ElementTree as ET

from collectors.windows.diagnostics import RuntimeFailure

P, D, W = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p
RESUME_FLAGS = 0x10003  # StartAfterBookmark | Strict
INITIAL_FLAGS = 0x10002  # StartAtOldestRecord | Strict; explicit initial baseline only
QUERY = "*[System[(EventID=4663 or EventID=4660 or EventID=4624 or EventID=1102)]]"
STALE = {1168, 15011, 15012}


class EventLogError(Exception):
    def __init__(self, code: int) -> None:
        self.code = code
        super().__init__("AUDIT_BOOKMARK_STALE" if code in STALE else "AUDIT_READ_FAILED")


class AuditReadFailure(RuntimeFailure):
    """Preserve only the original traceback and a bounded Win32 error number."""

    def __init__(self, error: EventLogError) -> None:
        super().__init__("AUDIT_READ_FAILED", error, "runtime")
        self.native_code = (
            error.code if type(error.code) is int and 0 <= error.code < 2**32 else None
        )


class EventLogPending(Exception):
    """A timed-out native read does not prove the subscription was drained."""


def api() -> Any:
    if os.name != "nt":
        raise EventLogError(50)
    dll = vars(ctypes)["WinDLL"]("wevtapi", use_last_error=True)
    signatures = {
        "EvtQuery": ([P, W, W, D], P),
        "EvtSubscribe": ([P, P, W, W, P, P, P, D], P),
        "EvtCreateBookmark": ([W], P),
        "EvtUpdateBookmark": ([P, P], D),
        "EvtRender": ([P, P, D, D, P, ctypes.POINTER(D), ctypes.POINTER(D)], D),
        "EvtNext": ([P, D, ctypes.POINTER(P), D, D, ctypes.POINTER(D)], D),
        "EvtSeek": ([P, ctypes.c_int64, P, D, D], D),
        "EvtClose": ([P], D),
        "EvtOpenLog": ([P, W, D], P),
        "EvtGetLogInfo": ([P, D, D, P, ctypes.POINTER(D)], D),
        "EvtOpenChannelConfig": ([P, W, D], P),
        "EvtGetChannelConfigProperty": ([P, D, D, D, P, ctypes.POINTER(D)], D),
    }
    for name, (arguments, result) in signatures.items():
        getattr(dll, name).argtypes, getattr(dll, name).restype = arguments, result
    return dll


def check(result: object) -> None:
    if not result:
        raise EventLogError(vars(ctypes)["get_last_error"]())


def render(dll: Any, handle: Any, flag: int = 1) -> str:
    used, count = D(), D()
    dll.EvtRender(None, handle, flag, 0, None, ctypes.byref(used), ctypes.byref(count))
    if vars(ctypes)["get_last_error"]() != 122 or not 0 < used.value <= 524288:
        raise EventLogError(13)
    buffer = ctypes.create_unicode_buffer((used.value + 1) // 2)
    check(
        dll.EvtRender(
            None,
            handle,
            flag,
            ctypes.sizeof(buffer),
            buffer,
            ctypes.byref(used),
            ctypes.byref(count),
        )
    )
    return buffer.value


def _time_of_day_boot() -> datetime:
    if os.name != "nt":
        raise EventLogError(50)

    class TimeOfDay(ctypes.Structure):
        _fields_ = [
            ("boot", ctypes.c_int64),
            ("current", ctypes.c_int64),
            ("zone", ctypes.c_int64),
            ("zone_id", D),
            ("reserved", D),
            ("boot_bias", ctypes.c_uint64),
            ("sleep_bias", ctypes.c_uint64),
        ]

    dll = vars(ctypes)["WinDLL"]("ntdll")
    function = dll.NtQuerySystemInformation
    function.argtypes, function.restype = [D, P, D, ctypes.POINTER(D)], ctypes.c_int32
    value, used = TimeOfDay(), D()
    if function(3, ctypes.byref(value), ctypes.sizeof(value), ctypes.byref(used)) < 0:
        raise EventLogError(13)
    return datetime(1601, 1, 1, tzinfo=UTC) + timedelta(microseconds=value.boot // 10)


def boot_epoch() -> tuple[str, datetime]:
    """An immutable local kernel boot event identifies an epoch, not clock ticks.

    TimeOfDay.BootTime follows clock corrections even during the same boot. Use it
    only to reject an old System-log witness (within two seconds of kernel time).
    Missing/rolled-over/invalid witnesses fail closed; never infer a new baseline.
    The bounded boot record stays local and is never uploaded as audit evidence.
    """
    dll = api()
    provider = "{a68ca8b7-004f-d7b6-a698-07e2de0f1f5d}"
    query = dll.EvtQuery(
        None, "System", f"*[System[Provider[@Guid='{provider}'] and EventID=12]]", 0x201
    )
    check(query)
    handles, count = (P * 1)(), D()
    try:
        check(dll.EvtNext(query, 1, handles, 1000, 0, ctypes.byref(count)))
        if count.value != 1 or not handles[0]:
            raise EventLogError(13)
        xml = render(dll, handles[0])
        try:
            if len(xml) > 32768:
                raise ValueError
            ns = "{http://schemas.microsoft.com/win/2004/08/events/event}"
            event = ET.fromstring(xml)
            system = event.find(ns + "System")
            if system is None:
                raise ValueError
            source = system.find(ns + "Provider")
            created = system.find(ns + "TimeCreated")
            if (
                source is None
                or source.get("Guid", "").lower() != provider
                or system.findtext(ns + "EventID") != "12"
                or system.findtext(ns + "Channel") != "System"
                or int(system.findtext(ns + "EventRecordID", "0")) <= 0
                or created is None
            ):
                raise ValueError
            fields = event.findall(ns + "EventData/" + ns + "Data[@Name='StartTime']")
            if len(fields) != 1:
                raise ValueError
            started = datetime.fromisoformat((fields[0].text or "").replace("Z", "+00:00"))
            written = datetime.fromisoformat(created.get("SystemTime", "").replace("Z", "+00:00"))
            if (
                started.utcoffset() != timedelta(0)
                or written.utcoffset() != timedelta(0)
                or written < started
                or abs((_time_of_day_boot() - started).total_seconds()) > 2
            ):
                raise ValueError
            return "kernel-boot:" + sha256(xml.encode()).hexdigest(), started.astimezone(UTC)
        except (ET.ParseError, ValueError, OverflowError):
            raise EventLogError(13) from None
    finally:
        for handle in (handles[0], query):
            if handle:
                dll.EvtClose(handle)


class SecurityReader:
    def __init__(
        self,
        bookmark: str | None,
        *,
        initial_baseline: bool = False,
        anchor_digest: str | None = None,
    ) -> None:
        self.api, self.bookmark, self.subscription, self.signal = api(), None, None, None
        self._draining = False
        self.kernel = vars(ctypes)["WinDLL"]("kernel32", use_last_error=True)
        self.kernel.CreateEventW.argtypes = [P, D, D, W]
        self.kernel.CreateEventW.restype = P
        self.kernel.CloseHandle.argtypes, self.kernel.CloseHandle.restype = [P], D
        self.kernel.WaitForSingleObject.argtypes = [P, D]
        self.kernel.WaitForSingleObject.restype = D
        self.kernel.ResetEvent.argtypes, self.kernel.ResetEvent.restype = [P], D
        try:
            if bookmark is None and not initial_baseline:
                raise EventLogError(1168)
            self.bookmark = self.api.EvtCreateBookmark(bookmark)
            check(self.bookmark)
            if bookmark and anchor_digest:
                self._validate_anchor(anchor_digest)
            self.signal = self.kernel.CreateEventW(None, True, True, None)
            check(self.signal)
            self.subscription = self.api.EvtSubscribe(
                None,
                self.signal,
                "Security",
                QUERY,
                self.bookmark if bookmark else None,
                None,
                None,
                RESUME_FLAGS if bookmark else INITIAL_FLAGS,
            )
            check(self.subscription)
        except BaseException:
            self.close()
            raise

    def _validate_anchor(self, digest: str) -> None:
        # A bookmark's numeric RecordID alone can be reused after a clear. Verify
        # the exact original event before accepting the persisted generation.
        query = self.api.EvtQuery(None, "Security", "*", 1)
        check(query)
        handles, returned = (P * 1)(), D()
        try:
            check(self.api.EvtSeek(query, 0, self.bookmark, 0, 0x10004))
            check(self.api.EvtNext(query, 1, handles, 0, 0, ctypes.byref(returned)))
            if sha256(render(self.api, handles[0]).encode()).hexdigest() != digest:
                raise EventLogError(15011)
        finally:
            if handles[0]:
                self.api.EvtClose(handles[0])
            self.api.EvtClose(query)

    def next(self) -> tuple[str, str] | None:
        if not self._draining:
            ready = self.kernel.WaitForSingleObject(self.signal, 0)
            if ready == 258:  # WAIT_TIMEOUT: no subscription signal; never block SCM stop.
                return None
            if ready != 0:  # WAIT_OBJECT_0 is the only valid event-object result.
                raise EventLogError(vars(ctypes)["get_last_error"]())
            # Reset before draining, retaining this state across bounded next()
            # calls. An arrival after the empty snapshot retains its wakeup.
            check(self.kernel.ResetEvent(self.signal))
            self._draining = True
        handles, returned = (P * 1)(), D()
        if not self.api.EvtNext(self.subscription, 1, handles, 0, 0, ctypes.byref(returned)):
            code = vars(ctypes)["get_last_error"]()
            # Pull subscriptions also report ERROR_INVALID_OPERATION with zero
            # results when drained (same native edge handled by upstream pywin32).
            if code == 259 or (code == 4317 and returned.value == 0):
                self._draining = False
                return None
            if code == 1460:
                raise EventLogPending()
            raise EventLogError(code)
        handle = handles[0]
        try:
            xml = render(self.api, handle)
            check(self.api.EvtUpdateBookmark(self.bookmark, handle))
            return xml, render(self.api, self.bookmark, 2)
        finally:
            self.api.EvtClose(handle)

    def bounds(self) -> dict[str, int]:
        class Variant(ctypes.Structure):
            _fields_ = [("value", ctypes.c_uint64), ("count", D), ("kind", D)]

        log = self.api.EvtOpenLog(None, "Security", 1)
        check(log)
        channel = None
        query = None
        handle = (P * 1)()
        try:
            result: dict[str, int] = {}
            for name, prop in (("oldest_record_id", 6), ("record_count", 5), ("file_bytes", 3)):
                value, used = Variant(), D()
                check(
                    self.api.EvtGetLogInfo(
                        log, prop, ctypes.sizeof(value), ctypes.byref(value), ctypes.byref(used)
                    )
                )
                result[name] = decode_uint64(value.value, value.kind, value.count)
            channel = self.api.EvtOpenChannelConfig(None, "Security", 0)
            check(channel)
            value, used = Variant(), D()
            check(
                self.api.EvtGetChannelConfigProperty(
                    channel, 8, 0, ctypes.sizeof(value), ctypes.byref(value), ctypes.byref(used)
                )
            )
            result["maximum_bytes"] = decode_uint64(value.value, value.kind, value.count)
            query = self.api.EvtQuery(None, "Security", "*", 0x201)
            check(query)
            returned = D()
            if self.api.EvtNext(query, 1, handle, 0, 0, ctypes.byref(returned)):
                xml = ET.fromstring(render(self.api, handle[0]))
                result["newest_record_id"] = int(
                    xml.findtext(
                        "{http://schemas.microsoft.com/win/2004/08/events/event}System/"
                        "{http://schemas.microsoft.com/win/2004/08/events/event}EventRecordID",
                        "0",
                    )
                )
            elif vars(ctypes)["get_last_error"]() == 259:
                result["newest_record_id"] = 0
            else:
                raise EventLogError(vars(ctypes)["get_last_error"]())
            return result
        finally:
            for owned in (handle[0], query, channel, log):
                if owned:
                    self.api.EvtClose(owned)

    def close(self) -> None:
        for handle in (self.subscription, self.bookmark):
            if handle:
                self.api.EvtClose(handle)
        if self.signal:
            self.kernel.CloseHandle(self.signal)
        self.subscription = self.bookmark = self.signal = None

    def __enter__(self) -> SecurityReader:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def no_reparse_ancestry(path: str, *, attributes: Callable[[str], int] | None = None) -> bool:
    """Conservative present-time privacy guard; NOT a claim about historical ancestry."""
    if attributes is None:
        kernel = vars(ctypes)["WinDLL"]("kernel32", use_last_error=True)
        reader = kernel.GetFileAttributesW
        reader.argtypes, reader.restype = [W], D
        attributes = reader
    value = PureWindowsPath(path)
    # Deleted leaf may be absent; every parent must still be a known local directory.
    for parent in reversed(value.parents):
        value_attributes = attributes(str(parent))
        if (
            value_attributes == 0xFFFFFFFF
            or value_attributes & 0x400
            or not value_attributes & 0x10
        ):
            return False
    value_attributes = attributes(str(value))
    return safe_leaf_attributes(value_attributes, vars(ctypes)["get_last_error"]())


def safe_leaf_attributes(attributes: int, error: int) -> bool:
    if attributes == 0xFFFFFFFF:
        return error == 2  # ERROR_FILE_NOT_FOUND only; an unreadable leaf is unknown.
    return not attributes & 0x400


def decode_uint64(value: int, kind: int, count: int) -> int:
    # Microsoft defines Count only for array variants; scalar Count may be 0xFFFFFFFF.
    if kind != 10:
        raise EventLogError(13)
    return value


def latest_baseline() -> tuple[str, str]:
    """Explicit operator enrollment anchor, never an implicit gap recovery."""
    dll = api()
    query = dll.EvtQuery(None, "Security", "*", 0x201)
    check(query)
    handles, count = (P * 1)(), D()
    bookmark = None
    try:
        check(dll.EvtNext(query, 1, handles, 0, 0, ctypes.byref(count)))
        bookmark = dll.EvtCreateBookmark(None)
        check(bookmark)
        check(dll.EvtUpdateBookmark(bookmark, handles[0]))
        return render(dll, handles[0]), render(dll, bookmark, 2)
    finally:
        for handle in (handles[0], bookmark, query):
            if handle:
                dll.EvtClose(handle)


def recent_session_xml() -> list[str]:
    """At most 64 recent sessions, local cache only; never an unbounded server login export."""
    dll = api()
    query = dll.EvtQuery(None, "Security", "*[System[EventID=4624]]", 0x201)
    check(query)
    rows: list[str] = []
    try:
        for _ in range(64):
            handles, count = (P * 1)(), D()
            if not dll.EvtNext(query, 1, handles, 0, 0, ctypes.byref(count)):
                if vars(ctypes)["get_last_error"]() == 259:
                    break
                raise EventLogError(vars(ctypes)["get_last_error"]())
            try:
                rows.append(render(dll, handles[0]))
            finally:
                dll.EvtClose(handles[0])
        return rows
    finally:
        dll.EvtClose(query)
