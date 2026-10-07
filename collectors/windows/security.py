"""Native protected local state and machine-bound, noninteractive DPAPI."""

from __future__ import annotations

import ctypes
import os
import re
from pathlib import Path, PureWindowsPath
from typing import Any
from uuid import uuid4

from .errors import SecurityError as SecurityError


class _Blob(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint32), ("data", ctypes.c_void_p)]


class _Attributes(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint32),
        ("descriptor", ctypes.c_void_p),
        ("inherit", ctypes.c_int32),
    ]


class _Acl(ctypes.Structure):
    _fields_ = [
        ("revision", ctypes.c_ubyte),
        ("reserved", ctypes.c_ubyte),
        ("size", ctypes.c_uint16),
        ("count", ctypes.c_uint16),
        ("reserved2", ctypes.c_uint16),
    ]


class _Ace(ctypes.Structure):
    _fields_ = [
        ("kind", ctypes.c_ubyte),
        ("flags", ctypes.c_ubyte),
        ("size", ctypes.c_uint16),
        ("mask", ctypes.c_uint32),
        ("sid", ctypes.c_uint32),
    ]


class _Standard(ctypes.Structure):
    _fields_ = [
        ("allocation", ctypes.c_int64),
        ("size", ctypes.c_int64),
        ("links", ctypes.c_uint32),
        ("delete_pending", ctypes.c_ubyte),
        ("directory", ctypes.c_ubyte),
    ]


class _Tag(ctypes.Structure):
    _fields_ = [("attributes", ctypes.c_uint32), ("tag", ctypes.c_uint32)]


def _api() -> Any:
    if os.name != "nt":
        raise SecurityError("PLATFORM_UNSUPPORTED")
    from ctypes import wintypes

    class API:
        def __init__(self) -> None:
            loader = vars(ctypes)["WinDLL"]
            self.kernel = loader("kernel32", use_last_error=True)
            self.advapi = loader("advapi32", use_last_error=True)
            self.crypt = loader("crypt32", use_last_error=True)
            pointer = ctypes.c_void_p
            pp = ctypes.POINTER(pointer)
            self.bind(self.kernel, "LocalFree", [pointer], pointer)
            self.bind(self.kernel, "CloseHandle", [pointer], wintypes.BOOL)
            self.bind(
                self.kernel,
                "CreateFileW",
                [
                    wintypes.LPCWSTR,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    ctypes.POINTER(_Attributes),
                    wintypes.DWORD,
                    wintypes.DWORD,
                    pointer,
                ],
                pointer,
            )
            self.bind(
                self.kernel,
                "CreateDirectoryW",
                [wintypes.LPCWSTR, ctypes.POINTER(_Attributes)],
                wintypes.BOOL,
            )
            self.bind(
                self.kernel,
                "GetFileInformationByHandleEx",
                [pointer, ctypes.c_int, pointer, wintypes.DWORD],
                wintypes.BOOL,
            )
            self.bind(
                self.kernel,
                "WriteFile",
                [pointer, pointer, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), pointer],
                wintypes.BOOL,
            )
            self.bind(
                self.kernel,
                "ReadFile",
                [pointer, pointer, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), pointer],
                wintypes.BOOL,
            )
            self.bind(self.kernel, "FlushFileBuffers", [pointer], wintypes.BOOL)
            self.bind(
                self.advapi,
                "ConvertStringSecurityDescriptorToSecurityDescriptorW",
                [wintypes.LPCWSTR, wintypes.DWORD, pp, pointer],
                wintypes.BOOL,
            )
            self.bind(
                self.advapi,
                "GetNamedSecurityInfoW",
                [wintypes.LPCWSTR, ctypes.c_int, wintypes.DWORD, pp, pp, pp, pp, pp],
                wintypes.DWORD,
            )
            self.bind(
                self.advapi,
                "GetSecurityDescriptorControl",
                [pointer, ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(wintypes.DWORD)],
                wintypes.BOOL,
            )
            self.bind(self.advapi, "ConvertSidToStringSidW", [pointer, pp], wintypes.BOOL)
            self.bind(self.advapi, "GetAce", [pointer, wintypes.DWORD, pp], wintypes.BOOL)
            blob = ctypes.POINTER(_Blob)
            self.bind(
                self.crypt,
                "CryptProtectData",
                [blob, wintypes.LPCWSTR, blob, pointer, pointer, wintypes.DWORD, blob],
                wintypes.BOOL,
            )
            self.bind(
                self.crypt,
                "CryptUnprotectData",
                [blob, pp, blob, pointer, pointer, wintypes.DWORD, blob],
                wintypes.BOOL,
            )

        def bind(self, dll: Any, name: str, args: list[Any], result: Any) -> None:
            function = getattr(dll, name)
            function.argtypes = args
            function.restype = result

    return API()


def _dpapi(value: bytes, *, decrypt: bool) -> bytes:
    if not isinstance(value, bytes) or not 1 <= len(value) <= 65536:
        raise SecurityError("CREDENTIAL_INVALID")
    api = _api()
    buffer = ctypes.create_string_buffer(value)
    source = _Blob(len(value), ctypes.cast(buffer, ctypes.c_void_p))
    result = _Blob()
    try:
        function = api.crypt.CryptUnprotectData if decrypt else api.crypt.CryptProtectData
        # Machine binding on protect; noninteractive on both operations.
        flags = 1 if decrypt else 5
        if not function(ctypes.byref(source), None, None, None, None, flags, ctypes.byref(result)):
            raise SecurityError("CREDENTIAL_INVALID")
        if not result.data or not 1 <= result.size <= 65536:
            raise SecurityError("CREDENTIAL_INVALID")
        return ctypes.string_at(result.data, result.size)
    finally:
        ctypes.memset(buffer, 0, len(buffer))
        if result.data:
            ctypes.memset(result.data, 0, result.size)
            api.kernel.LocalFree(result.data)


def seal(value: bytes) -> bytes:
    return _dpapi(value, decrypt=False)


def unseal(value: bytes) -> bytes:
    return _dpapi(value, decrypt=True)


_TRUSTED = frozenset({"S-1-5-18", "S-1-5-32-544"})
_SDDL = "O:BAG:BAD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"


class ProtectedState:
    """Pin ancestors against rename; hold an exclusive lock for the whole runtime."""

    def __init__(self, root: Path, *, create: bool = False, _child: bool = False) -> None:
        self._root = Path(root)
        self._create = create
        self._child = _child
        self._api = _api()
        self._handles: list[int] = []
        self._active = False

    def __repr__(self) -> str:
        return "ProtectedState()"

    @property
    def root(self) -> Path:
        if not self._active:
            raise SecurityError("STATE_INVALID")
        return self._root

    def _sid(self, sid: int | None) -> str:
        result = ctypes.c_void_p()
        if not sid or not self._api.advapi.ConvertSidToStringSidW(sid, ctypes.byref(result)):
            raise SecurityError("UNSAFE_STATE")
        try:
            if result.value is None:
                raise SecurityError("UNSAFE_STATE")
            return ctypes.wstring_at(result.value)
        finally:
            self._api.kernel.LocalFree(result)

    def _dacl(self, path: Path, *, protected: bool = False) -> None:
        owner, acl, descriptor = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        try:
            if (
                self._api.advapi.GetNamedSecurityInfoW(
                    str(path),
                    1,
                    5,
                    ctypes.byref(owner),
                    None,
                    ctypes.byref(acl),
                    None,
                    ctypes.byref(descriptor),
                )
                or not acl.value
                or self._sid(owner.value) not in _TRUSTED
            ):
                raise SecurityError("UNSAFE_STATE")
            control, revision = ctypes.c_uint16(), ctypes.c_uint32()
            if not self._api.advapi.GetSecurityDescriptorControl(
                descriptor,
                ctypes.byref(control),
                ctypes.byref(revision),
            ) or (protected and not control.value & 0x1000):
                raise SecurityError("UNSAFE_STATE")
            header = ctypes.cast(acl, ctypes.POINTER(_Acl)).contents
            if header.count != 2:
                raise SecurityError("UNSAFE_STATE")
            principals = set()
            for index in range(header.count):
                pointer = ctypes.c_void_p()
                if (
                    not self._api.advapi.GetAce(acl, index, ctypes.byref(pointer))
                    or not pointer.value
                ):
                    raise SecurityError("UNSAFE_STATE")
                ace = ctypes.cast(pointer, ctypes.POINTER(_Ace)).contents
                if ace.kind != 0 or ace.flags & ~0x13 or ace.mask != 0x1F01FF:
                    raise SecurityError("UNSAFE_STATE")
                principals.add(self._sid(pointer.value + _Ace.sid.offset))
            if principals != _TRUSTED:
                raise SecurityError("UNSAFE_STATE")
        finally:
            if descriptor.value:
                self._api.kernel.LocalFree(descriptor)

    def _attributes(self) -> tuple[_Attributes, ctypes.c_void_p]:
        descriptor = ctypes.c_void_p()
        if not self._api.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            _SDDL,
            1,
            ctypes.byref(descriptor),
            None,
        ):
            raise SecurityError("UNSAFE_STATE")
        return _Attributes(ctypes.sizeof(_Attributes), descriptor, False), descriptor

    def _open(self, path: Path, *, lock: bool = False) -> int:
        # No FILE_SHARE_DELETE: an ordinary parent writer cannot replace a pinned node.
        handle = self._api.kernel.CreateFileW(
            str(path),
            0x120089,
            0 if lock else (3 if path.is_dir() else 1),
            None,
            3,
            0x02200000,
            None,
        )
        if handle in (None, ctypes.c_void_p(-1).value):
            code = (
                "STATE_BUSY"
                if lock and vars(ctypes)["get_last_error"]() in (32, 33)
                else "UNSAFE_STATE"
            )
            raise SecurityError(code)
        tag = _Tag()
        if (
            not self._api.kernel.GetFileInformationByHandleEx(
                handle,
                9,
                ctypes.byref(tag),
                ctypes.sizeof(tag),
            )
            or tag.attributes & 0x400
        ):
            self._api.kernel.CloseHandle(handle)
            raise SecurityError("UNSAFE_STATE")
        return int(handle)

    def __enter__(self) -> ProtectedState:
        if self._active or self._handles:
            raise SecurityError("STATE_INVALID")
        root = PureWindowsPath(self._root)
        if (
            not root.is_absolute()
            or not re.fullmatch(r"[A-Za-z]:", root.drive)
            or ".." in root.parts
            or len(root.parts) < 2
            or any(":" in part or part.endswith((".", " ")) for part in root.parts[1:])
        ):
            raise SecurityError("UNSAFE_STATE")
        try:
            # Ancestor pins precede state creation/validation and remain held until exit.
            for ancestor in reversed(self._root.parents):
                if getattr(ancestor.lstat(), "st_file_attributes", 0) & 0x400:
                    raise SecurityError("UNSAFE_STATE")
                self._handles.append(self._open(ancestor))
            if self._create and not self._root.exists():
                attributes, descriptor = self._attributes()
                try:
                    if not self._api.kernel.CreateDirectoryW(
                        str(self._root), ctypes.byref(attributes)
                    ):
                        raise SecurityError("UNSAFE_STATE")
                finally:
                    self._api.kernel.LocalFree(descriptor)
            if (
                getattr(self._root.lstat(), "st_file_attributes", 0) & 0x400
                or not self._root.is_dir()
            ):
                raise SecurityError("UNSAFE_STATE")
            self._handles.append(self._open(self._root))
            self._dacl(self._root, protected=True)
            self._active = True
            lock = self._root / "runtime.lock"
            if not lock.exists():
                if self._child:
                    raise SecurityError("STATE_INVALID")
                self._write_new(lock, b"")
            self._validate_file(lock)
            if self._child:
                try:
                    handle = self._open(lock, lock=True)
                except SecurityError as error:
                    if error.code != "STATE_BUSY":
                        raise
                    return self
                self._api.kernel.CloseHandle(handle)
                raise SecurityError("STATE_INVALID")
            self._handles.append(self._open(lock, lock=True))
            return self
        except (OSError, SecurityError) as error:
            self.__exit__(None, None, None)
            if isinstance(error, SecurityError):
                raise
            raise SecurityError("UNSAFE_STATE") from None

    def __exit__(self, *_args: object) -> None:
        for handle in reversed(self._handles):
            self._api.kernel.CloseHandle(handle)
        self._handles.clear()
        self._active = False

    def _name(self, name: str) -> Path:
        if (
            not self._active
            or not isinstance(name, str)
            or not re.fullmatch(
                r"[a-zA-Z0-9_-][a-zA-Z0-9_.-]{0,63}",
                name,
            )
            or name.endswith(".")
            or name.split(".")[0].upper()
            in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                *(f"COM{x}" for x in range(10)),
                *(f"LPT{x}" for x in range(10)),
            }
        ):
            raise SecurityError("STATE_INVALID")
        return self._root / name

    def _validate_file(self, path: Path) -> None:
        try:
            info = path.lstat()
            if (
                not path.is_file()
                or info.st_nlink != 1
                or getattr(info, "st_file_attributes", 0) & 0x400
            ):
                raise SecurityError("UNSAFE_STATE")
            self._dacl(path)
        except OSError:
            raise SecurityError("UNSAFE_STATE") from None

    def validate_file(self, name: str) -> None:
        self._validate_file(self._name(name))

    def create_file(self, name: str) -> None:
        path = self._name(name)
        if name.casefold() == "runtime.lock":
            raise SecurityError("STATE_INVALID")
        self._write_new(path, b"")
        self._validate_file(path)

    def read(self, name: str, maximum: int) -> bytes:
        path = self._name(name)
        if type(maximum) is not int or not 1 <= maximum <= 1024 * 1024:
            raise SecurityError("STATE_INVALID")
        self._validate_file(path)
        handle = self._open(path)
        try:
            metadata = _Standard()
            if (
                not self._api.kernel.GetFileInformationByHandleEx(
                    handle,
                    1,
                    ctypes.byref(metadata),
                    ctypes.sizeof(metadata),
                )
                or metadata.links != 1
                or metadata.directory
                or not 0 <= metadata.size <= maximum
            ):
                raise SecurityError("STATE_INVALID")
            buffer, read = ctypes.create_string_buffer(maximum + 1), ctypes.c_uint32()
            if not self._api.kernel.ReadFile(handle, buffer, maximum + 1, ctypes.byref(read), None):
                raise SecurityError("STATE_INVALID")
            if read.value > maximum:
                raise SecurityError("STATE_INVALID")
            return buffer.raw[: read.value]
        finally:
            self._api.kernel.CloseHandle(handle)

    def _write_new(self, path: Path, value: bytes) -> None:
        attributes, descriptor = self._attributes()
        handle = self._api.kernel.CreateFileW(
            str(path),
            0x40000000,
            0,
            ctypes.byref(attributes),
            1,
            0x00200000,
            None,
        )
        self._api.kernel.LocalFree(descriptor)
        if handle in (None, ctypes.c_void_p(-1).value):
            raise SecurityError("UNSAFE_STATE")
        try:
            written = ctypes.c_uint32()
            buffer = ctypes.create_string_buffer(value)
            if not self._api.kernel.WriteFile(
                handle, buffer, len(value), ctypes.byref(written), None
            ):
                raise SecurityError("STATE_INVALID")
            if written.value != len(value) or not self._api.kernel.FlushFileBuffers(handle):
                raise SecurityError("STATE_INVALID")
        finally:
            self._api.kernel.CloseHandle(handle)

    def write(self, name: str, value: bytes) -> None:
        path = self._name(name)
        if name == "runtime.lock":
            raise SecurityError("STATE_INVALID")
        if not isinstance(value, bytes) or len(value) > 1024 * 1024:
            raise SecurityError("STATE_INVALID")
        if path.exists():
            self._validate_file(path)
        temporary = self._root / (str(uuid4()) + ".tmp")
        try:
            self._write_new(temporary, value)
            os.replace(temporary, path)
            self._validate_file(path)
        except OSError:
            raise SecurityError("STATE_INVALID") from None
        finally:
            # Only the uniquely generated file this operation owns, inside the pinned root.
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                raise SecurityError("STATE_INVALID") from None
