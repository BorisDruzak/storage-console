"""Pinned local Win32 metadata handles; no file data access or reparse traversal."""

from __future__ import annotations

import ctypes
import os
import re
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PureWindowsPath
from typing import Any, Protocol, cast
from uuid import UUID

from pydantic import ValidationError

from packages.contracts.inventory import FileObjectRecord, VolumeRecord

from .inventory import CaptureError, Observation, Scope


class _IdInfo(ctypes.Structure):
    _fields_ = [("serial", ctypes.c_uint64), ("identifier", ctypes.c_ubyte * 16)]


class _BasicInfo(ctypes.Structure):
    _fields_ = [
        ("created", ctypes.c_int64),
        ("accessed", ctypes.c_int64),
        ("written", ctypes.c_int64),
        ("changed", ctypes.c_int64),
        ("attributes", ctypes.c_uint32),
    ]


class _StandardInfo(ctypes.Structure):
    _fields_ = [
        ("allocation", ctypes.c_int64),
        ("size", ctypes.c_int64),
        ("links", ctypes.c_uint32),
        ("delete_pending", ctypes.c_ubyte),
        ("directory", ctypes.c_ubyte),
    ]


class _UnicodeString(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_uint16),
        ("maximum", ctypes.c_uint16),
        ("buffer", ctypes.c_void_p),
    ]


class _ObjectAttributes(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_uint32),
        ("root", ctypes.c_void_p),
        ("name", ctypes.POINTER(_UnicodeString)),
        ("attributes", ctypes.c_uint32),
        ("security", ctypes.c_void_p),
        ("quality", ctypes.c_void_p),
    ]


class _IoStatus(ctypes.Structure):
    # NTSTATUS/pointer union occupies one pointer-sized slot.
    _fields_ = [("status", ctypes.c_void_p), ("information", ctypes.c_size_t)]


class _DirectoryInfo(ctypes.Structure):
    _fields_ = [
        ("next", ctypes.c_uint32),
        ("index", ctypes.c_uint32),
        ("created", ctypes.c_int64),
        ("accessed", ctypes.c_int64),
        ("written", ctypes.c_int64),
        ("changed", ctypes.c_int64),
        ("size", ctypes.c_int64),
        ("allocation", ctypes.c_int64),
        ("attributes", ctypes.c_uint32),
        ("name_length", ctypes.c_uint32),
        ("ea_size", ctypes.c_uint32),
        ("name", ctypes.c_uint16 * 1),
    ]


@dataclass(frozen=True)
class _Metadata:
    serial: int
    file_id: str
    directory: bool
    size: int


def _native_failure(code: int) -> CaptureError:
    return CaptureError(
        {
            2: "NOT_FOUND",
            3: "NOT_FOUND",
            5: "ACCESS_DENIED",
            32: "SHARING_VIOLATION",
            33: "SHARING_VIOLATION",
        }.get(code, "NATIVE_FAILED")
    )


def _failure(error: OSError) -> CaptureError:
    code = getattr(error, "winerror", None)
    return _native_failure(code if isinstance(code, int) else 0)


class _Function(Protocol):
    argtypes: list[type[Any]] | None
    restype: type[Any] | None

    def __call__(self, *args: object) -> Any: ...


def _volume_path(path: str) -> tuple[str, str, str]:
    match = re.fullmatch(r"\\\\\?\\Volume\{([0-9a-fA-F-]{36})\}\\(.*)", path)
    if match is None:
        raise CaptureError("SCOPE_CHANGED")
    try:
        identity = "volume:" + str(UUID(match[1]))
    except ValueError:
        raise CaptureError("SCOPE_CHANGED") from None
    return identity, path[: path.index("}") + 2], match[2]


class _Api:
    def __init__(self) -> None:
        if os.name != "nt":
            raise CaptureError("PLATFORM_UNSUPPORTED")
        dll = vars(ctypes)["WinDLL"]("kernel32.dll", use_last_error=True)
        self.functions: dict[str, _Function] = {}
        self._dll = dll
        p, w, d, b = ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_int
        self._bind("CreateFileW", [w, d, d, p, d, d, p], p)
        self._bind("CloseHandle", [p], b)
        self._bind("GetFileInformationByHandleEx", [p, b, p, d], b)
        self._bind("GetFinalPathNameByHandleW", [p, w, d, d], d)
        self._bind("GetVolumeInformationByHandleW", [p, w, d, p, p, p, w, d], b)
        self._bind("GetDiskFreeSpaceExW", [w, p, p, p], b)
        self._bind("GetVolumePathNamesForVolumeNameW", [w, w, d, p], b)
        self._bind("GetDriveTypeW", [w], d)
        self._bind("GetVolumeNameForVolumeMountPointW", [w, w, d], b)
        native = vars(ctypes)["WinDLL"]("ntdll.dll")
        bindings: list[tuple[str, list[type[Any]], type[Any]]] = [
            ("NtCreateFile", [p, d, p, p, p, d, d, d, d, p, d], ctypes.c_int32),
            ("RtlNtStatusToDosError", [ctypes.c_int32], d),
        ]
        for name, args, result in bindings:
            fn = cast(_Function, getattr(native, name))
            fn.argtypes, fn.restype = args, result
            self.functions[name] = fn

    def _bind(self, name: str, args: list[type[Any]], result: type[Any]) -> None:
        fn = cast(_Function, getattr(self._dll, name))
        fn.argtypes, fn.restype = args, result
        self.functions[name] = fn

    def _check(self, value: object) -> None:
        if not value:
            # Capture error number only; never retain the OS message/path in our error.
            raise _native_failure(int(vars(ctypes)["get_last_error"]()))

    def open(self, path: str) -> int:
        result = self.functions["CreateFileW"](path, 0x81, 0x3, None, 3, 0x02200000, None)
        if result is None or result == ctypes.c_void_p(-1).value:
            self._check(False)
        return int(result)

    def close(self, handle: int) -> None:
        self._check(self.functions["CloseHandle"](handle))

    def open_relative(self, parent: int, name: str, *, directory: bool = False) -> int:
        # A single component relative to the owned directory object. Never
        # resolve an ancestor pathname again, even after reparse mutation.
        encoded = name.encode("utf-16-le")
        if (
            not name
            or name in {".", ".."}
            or any(c in name for c in "\\/:\0")
            or len(encoded) > 65532
        ):
            raise CaptureError("METADATA_INVALID")
        buffer = ctypes.create_unicode_buffer(name)
        unicode = _UnicodeString(
            len(encoded), len(encoded) + 2, ctypes.cast(buffer, ctypes.c_void_p)
        )
        attributes = _ObjectAttributes(
            ctypes.sizeof(_ObjectAttributes), parent, ctypes.pointer(unicode), 0, None, None
        )
        result, status = ctypes.c_void_p(), _IoStatus()
        code = int(
            self.functions["NtCreateFile"](
                ctypes.byref(result),
                0x100080 | int(directory),
                ctypes.byref(attributes),
                ctypes.byref(status),
                None,
                0,
                3,
                1,
                0x200020 | (1 if directory else 0x40),
                None,
                0,
            )
        )
        if code < 0:
            raise _native_failure(int(self.functions["RtlNtStatusToDosError"](code)))
        if result.value is None:
            raise CaptureError("NATIVE_FAILED")
        return int(result.value)

    @contextmanager
    def relative(self, parent: int, name: str, *, directory: bool = False) -> Iterator[int]:
        handle = self.open_relative(parent, name, directory=directory)
        try:
            yield handle
        finally:
            self.close(handle)

    def entries(self, handle: int) -> Iterator[tuple[str, bool]]:
        # FILE_LIST_DIRECTORY on a directory handle enumerates this
        # handle's directory, rather than reopening its potentially changed name.
        buffer = ctypes.create_string_buffer(65536)
        kind = 15
        while True:
            self.metadata(handle)
            if not self.functions["GetFileInformationByHandleEx"](
                handle, kind, buffer, len(buffer)
            ):
                error = int(vars(ctypes)["get_last_error"]())
                if error == 18:  # ERROR_NO_MORE_FILES
                    return
                raise _native_failure(error)
            kind = 14
            offset = 0
            while True:
                if offset + ctypes.sizeof(_DirectoryInfo) > len(buffer):
                    raise CaptureError("METADATA_INVALID")
                info = _DirectoryInfo.from_buffer(buffer, offset)
                start = offset + _DirectoryInfo.name.offset
                end = start + info.name_length
                if not info.name_length or info.name_length % 2 or end > len(buffer):
                    raise CaptureError("METADATA_INVALID")
                name = buffer.raw[start:end].decode("utf-16-le")
                if name not in {".", ".."}:
                    yield name, bool(info.attributes & 0x10)
                step = info.next
                if not step:
                    break
                if step % 8 or offset + step < end:
                    raise CaptureError("METADATA_INVALID")
                offset += step

    @contextmanager
    def opened(self, path: str) -> Iterator[int]:
        handle = self.open(path)
        try:
            yield handle
        finally:
            self.close(handle)

    def _query(self, handle: int, kind: int, value: ctypes.Structure) -> None:
        self._check(
            self.functions["GetFileInformationByHandleEx"](
                handle, kind, ctypes.byref(value), ctypes.sizeof(value)
            )
        )

    def metadata(self, handle: int) -> _Metadata:
        basic, standard, identity = _BasicInfo(), _StandardInfo(), _IdInfo()
        self._query(handle, 0, basic)
        if basic.attributes & 0x400:
            raise CaptureError("REPARSE_POINT")
        self._query(handle, 1, standard)
        self._query(handle, 18, identity)
        if standard.size < 0 or standard.delete_pending:
            raise CaptureError("METADATA_INVALID")
        if not standard.directory and standard.links > 1:
            raise CaptureError("MULTIPLE_LINKS")
        return _Metadata(
            identity.serial,
            bytes(identity.identifier).hex(),
            bool(standard.directory),
            standard.size,
        )

    def final_path(self, handle: int) -> str:
        buffer = ctypes.create_unicode_buffer(32768)
        size = int(self.functions["GetFinalPathNameByHandleW"](handle, buffer, len(buffer), 1))
        self._check(size)
        if size >= len(buffer):
            raise CaptureError("METADATA_INVALID")
        return buffer.value

    def volume_root(self, drive: str) -> str:
        if int(self.functions["GetDriveTypeW"](drive)) not in {2, 3, 5, 6}:
            raise CaptureError("INVALID_SCOPE")
        buffer = ctypes.create_unicode_buffer(64)
        self._check(self.functions["GetVolumeNameForVolumeMountPointW"](drive, buffer, len(buffer)))
        _, root, relative = _volume_path(buffer.value)
        if relative:
            raise CaptureError("SCOPE_CHANGED")
        return root

    def volume(self, handle: int, path: str, alias: str) -> VolumeRecord:
        identity, root, _ = _volume_path(path)
        label, filesystem = ctypes.create_unicode_buffer(261), ctypes.create_unicode_buffer(261)
        self._check(
            self.functions["GetVolumeInformationByHandleW"](
                handle, label, len(label), None, None, None, filesystem, len(filesystem)
            )
        )
        total, free = ctypes.c_uint64(), ctypes.c_uint64()
        self._check(
            self.functions["GetDiskFreeSpaceExW"](
                root, None, ctypes.byref(total), ctypes.byref(free)
            )
        )
        aliases = ctypes.create_unicode_buffer(65536)
        used = ctypes.c_uint32()
        self._check(
            self.functions["GetVolumePathNamesForVolumeNameW"](
                root, aliases, len(aliases), ctypes.byref(used)
            )
        )
        if not 2 <= used.value <= len(aliases):
            raise CaptureError("METADATA_INVALID")
        multi = "".join(aliases[: used.value])
        if not multi.endswith("\0\0"):
            raise CaptureError("METADATA_INVALID")
        mounts = [value for value in multi.split("\0") if value]
        if not 1 <= len(mounts) <= 128 or len(set(mounts)) != len(mounts):
            raise CaptureError("METADATA_INVALID")
        return VolumeRecord(
            occurred_at=datetime.now(UTC),
            unique_identity=identity,
            filesystem=filesystem.value,
            label=label.value or None,
            mount_aliases=mounts,
            total_bytes=total.value,
            free_bytes=free.value,
        )


class NativeInventory:
    def __init__(self, *, api: _Api | None = None) -> None:
        self._api = api

    def scan(self, scope: Scope) -> Iterator[Observation]:
        if not isinstance(scope, Scope):
            raise CaptureError("INVALID_SCOPE")
        api = self._api if self._api is not None else _Api()
        for root in scope.roots:
            try:
                yield from self._root(api, root)
            except CaptureError as error:
                yield Observation(error_code=error.code)
            except OSError as error:
                yield Observation(error_code=_failure(error).code)
            except (ValueError, UnicodeError, ValidationError):
                yield Observation(error_code="METADATA_INVALID")

    def _root(self, api: _Api, root: str) -> Iterator[Observation]:
        with ExitStack() as stack:
            # Resolve the local volume before opening any metadata handle. A
            # subsequent drive-letter remap cannot turn CreateFile into SMB access.
            path = api.volume_root(root[:3])
            parent = None
            parent_id: str | None = None
            serial = None
            handle: int | None = None
            for part in [None, *PureWindowsPath(root).parts[1:]]:
                if part is None:
                    context = api.opened(path)
                else:
                    assert handle is not None
                    path = path.rstrip("\\") + "\\" + part
                    context = api.relative(handle, part, directory=True)
                handle = stack.enter_context(context)
                metadata = api.metadata(handle)
                if not metadata.directory:
                    raise CaptureError("NOT_DIRECTORY")
                final = api.final_path(handle)
                _volume_path(final)
                if serial is not None and (
                    metadata.serial != serial or final.casefold() != path.casefold()
                ):
                    raise CaptureError("SCOPE_CHANGED")
                serial = metadata.serial
                path = final
                if part is not None:
                    parent_id = parent.file_id if parent else None
                else:
                    parent_id = None
                parent = metadata
            assert handle is not None
            yield Observation(record=api.volume(handle, path, root))
            yield Observation(record=self._record(path, metadata, parent_id))
            yield from self._children(api, handle, path, metadata, 0)

    @staticmethod
    def _record(path: str, metadata: _Metadata, parent: str | None) -> FileObjectRecord:
        identity, _, relative = _volume_path(path)
        return FileObjectRecord(
            occurred_at=datetime.now(UTC),
            volume_identity=identity,
            file_id=metadata.file_id,
            parent_file_id=parent,
            object_type="DIRECTORY" if metadata.directory else "FILE",
            name=PureWindowsPath(path).name or "volume-root",
            relative_path=relative or "\\",
            size_bytes=None if metadata.directory else metadata.size,
        )

    def _children(
        self, api: _Api, parent_handle: int, path: str, parent: _Metadata, depth: int
    ) -> Iterator[Observation]:
        if depth >= 64:
            yield Observation(error_code="DEPTH_LIMIT")
            return
        for name, directory in api.entries(parent_handle):
            try:
                with api.relative(parent_handle, name, directory=directory) as handle:
                    metadata = api.metadata(handle)
                    final = api.final_path(handle)
                    if metadata.serial != parent.serial or PureWindowsPath(
                        final
                    ).parent != PureWindowsPath(path):
                        raise CaptureError("SCOPE_CHANGED")
                    yield Observation(record=self._record(final, metadata, parent.file_id))
                    if metadata.directory:
                        yield from self._children(api, handle, final, metadata, depth + 1)
            except CaptureError as error:
                yield Observation(error_code=error.code)
            except OSError as error:
                yield Observation(error_code=_failure(error).code)
            except (ValueError, UnicodeError, ValidationError):
                yield Observation(error_code="METADATA_INVALID")
