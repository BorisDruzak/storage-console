"""Read-only Win32 policy/SACL proof; privileges affect only this Audit process."""

import ctypes
import math
import os
import stat
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Protocol
from uuid import UUID

from .native import no_reparse_ancestry


class _Guid(ctypes.Structure):
    _fields_ = [
        ("a", ctypes.c_uint32),
        ("b", ctypes.c_uint16),
        ("c", ctypes.c_uint16),
        ("d", ctypes.c_ubyte * 8),
    ]


class _Policy(ctypes.Structure):
    _fields_ = [("subcategory", _Guid), ("information", ctypes.c_uint32), ("category", _Guid)]


class _Luid(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_int32)]


class _Privileges(ctypes.Structure):
    _fields_ = [("count", ctypes.c_uint32), ("luid", _Luid), ("attributes", ctypes.c_uint32)]


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
    ]


def covered(
    aces: list[tuple[int, int, int, str]], sids: list[str], *, directory: bool = True
) -> bool:
    masks = dict.fromkeys(sids, 0)
    for kind, flags, mask, sid in aces:
        # Success + file/container inheritance. Conditional/object ACEs are
        # unsupported proof, never guessed from a partially decoded structure.
        required = 0x43 if directory else 0x40
        if kind == 2 and flags & required == required and not flags & 0x0C and sid in masks:
            masks[sid] |= mask
    return bool(masks) and all(mask & 0x10006 == 0x10006 for mask in masks.values())


class _Scan(Protocol):
    def __next__(self) -> os.DirEntry[str]: ...
    def close(self) -> None: ...


def scope_covered(
    root: str,
    sids: list[str],
    check: Callable[[str, list[str], bool], bool],
    *,
    limit: int = 256,
    max_depth: int = 128,
    max_seconds: float = 30,
    stopped: Callable[[], bool] = lambda: False,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    """Lazy DFS: resident directory iterators scale with bounded depth, never width."""
    if (
        type(limit) is not int
        or not 1 <= limit <= 100000
        or type(max_depth) is not int
        or not 1 <= max_depth <= 128
        or isinstance(max_seconds, bool)
        or not math.isfinite(max_seconds)
        or not 0 < max_seconds <= 30
    ):
        return False
    started = clock()
    frames: list[_Scan] = []

    def expired() -> bool:
        return stopped() or clock() - started > max_seconds

    def children(path: str) -> _Scan:
        if os.name == "nt" and not path.startswith("\\\\?\\"):
            path = "\\\\?\\" + os.path.abspath(path)
        return os.scandir(path)

    try:
        if expired() or not check(root, sids, True):
            return False
        seen = 1
        frames.append(children(root))
        while frames:
            if expired():
                return False
            try:
                child = next(frames[-1])
            except StopIteration:
                frames.pop().close()
                continue
            seen += 1
            if seen > limit:
                return False
            attributes = child.stat(follow_symlinks=False)
            if child.is_symlink() or getattr(attributes, "st_file_attributes", 0) & 0x400:
                return False
            directory = stat.S_ISDIR(attributes.st_mode)
            if not check(child.path, sids, directory) or expired():
                return False
            if directory:
                if len(frames) >= max_depth:
                    return False
                frames.append(children(child.path))
        return not expired()
    except OSError:
        return False
    finally:
        for iterator in reversed(frames):
            iterator.close()


class Native:
    def __init__(self) -> None:
        self.api = vars(ctypes)["WinDLL"]("advapi32", use_last_error=True)
        self.kernel = vars(ctypes)["WinDLL"]("kernel32", use_last_error=True)
        void, dword = ctypes.c_void_p, ctypes.c_uint32
        pointer = ctypes.POINTER(void)
        prototypes = {
            "AuditQuerySystemPolicy": ([ctypes.POINTER(_Guid), dword, pointer], ctypes.c_ubyte),
            "AuditFree": ([void], None),
            "OpenProcessToken": ([void, dword, pointer], ctypes.c_int32),
            "LookupPrivilegeValueW": (
                [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.POINTER(_Luid)],
                ctypes.c_int32,
            ),
            "AdjustTokenPrivileges": (
                [
                    void,
                    ctypes.c_int32,
                    ctypes.POINTER(_Privileges),
                    dword,
                    ctypes.POINTER(_Privileges),
                    ctypes.POINTER(dword),
                ],
                ctypes.c_int32,
            ),
            "GetNamedSecurityInfoW": (
                [ctypes.c_wchar_p, dword, dword, pointer, pointer, pointer, pointer, pointer],
                dword,
            ),
            "GetAce": ([void, dword, pointer], ctypes.c_int32),
            "IsValidSid": ([void], ctypes.c_int32),
            "GetLengthSid": ([void], dword),
            "ConvertSidToStringSidW": ([void, ctypes.POINTER(ctypes.c_wchar_p)], ctypes.c_int32),
        }
        for name, (args, result) in prototypes.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result
        self.kernel.GetCurrentProcess.argtypes = []
        self.kernel.GetCurrentProcess.restype = void
        self.kernel.CloseHandle.argtypes = [void]
        self.kernel.CloseHandle.restype = ctypes.c_int32
        self.kernel.LocalFree.argtypes = [void]
        self.kernel.LocalFree.restype = void

    @contextmanager
    def privilege(self) -> Iterator[None]:
        token, old, length = ctypes.c_void_p(), _Privileges(), ctypes.c_uint32()
        if not self.api.OpenProcessToken(
            self.kernel.GetCurrentProcess(), 0x28, ctypes.byref(token)
        ):
            raise ValueError("AUDIT_READINESS_UNKNOWN")
        changed = False
        try:
            new = _Privileges(count=1, attributes=2)
            if not self.api.LookupPrivilegeValueW(
                None, "SeSecurityPrivilege", ctypes.byref(new.luid)
            ):
                raise ValueError("AUDIT_READINESS_UNKNOWN")
            vars(ctypes)["set_last_error"](0)
            if not self.api.AdjustTokenPrivileges(
                token,
                False,
                ctypes.byref(new),
                ctypes.sizeof(old),
                ctypes.byref(old),
                ctypes.byref(length),
            ):
                raise ValueError("AUDIT_READINESS_UNKNOWN")
            if vars(ctypes)["get_last_error"]() != 0:
                raise ValueError("AUDIT_READINESS_UNKNOWN")
            changed = True
            yield
        finally:
            try:
                if changed:
                    vars(ctypes)["set_last_error"](0)
                    restored = self.api.AdjustTokenPrivileges(
                        token, False, ctypes.byref(old), 0, None, None
                    )
                    if not restored or vars(ctypes)["get_last_error"]() != 0:
                        raise ValueError("AUDIT_READINESS_UNKNOWN")
            finally:
                self.kernel.CloseHandle(token)

    def policy(self) -> bool:
        guid = _Guid.from_buffer_copy(UUID("0cce921d-69ae-11d9-bed3-505054503030").bytes_le)
        value = ctypes.c_void_p()
        if not self.api.AuditQuerySystemPolicy(ctypes.byref(guid), 1, ctypes.byref(value)):
            raise ValueError("AUDIT_READINESS_UNKNOWN")
        try:
            return bool(ctypes.cast(value, ctypes.POINTER(_Policy)).contents.information & 1)
        finally:
            self.api.AuditFree(value)

    def sacl(self, root: str, sids: list[str]) -> bool:
        return scope_covered(root, sids, self.sacl_entry)

    def sacl_entry(self, root: str, sids: list[str], directory: bool) -> bool:
        if not no_reparse_ancestry(root):
            return False
        acl, descriptor = ctypes.c_void_p(), ctypes.c_void_p()
        result = self.api.GetNamedSecurityInfoW(
            root, 1, 8, None, None, None, ctypes.byref(acl), ctypes.byref(descriptor)
        )
        if result:
            raise ValueError("AUDIT_READINESS_UNKNOWN")
        try:
            if not acl.value:
                return False
            header = ctypes.cast(acl, ctypes.POINTER(_Acl)).contents
            if header.count > 256 or header.size > 65535:
                return False
            entries = []
            for index in range(header.count):
                value = ctypes.c_void_p()
                if not self.api.GetAce(acl, index, ctypes.byref(value)) or not value.value:
                    return False
                ace = ctypes.cast(value, ctypes.POINTER(_Ace)).contents
                if ace.kind != 2 or ace.size < 16:
                    continue
                sid = ctypes.c_void_p(value.value + 8)
                if not self.api.IsValidSid(sid) or self.api.GetLengthSid(sid) > ace.size - 8:
                    return False
                text = ctypes.c_wchar_p()
                if not self.api.ConvertSidToStringSidW(sid, ctypes.byref(text)):
                    return False
                try:
                    entries.append((ace.kind, ace.flags, ace.mask, text.value or ""))
                finally:
                    self.kernel.LocalFree(ctypes.cast(text, ctypes.c_void_p))
            return covered(entries, sids, directory=directory)
        finally:
            self.kernel.LocalFree(descriptor)


def readiness(
    roots: list[str],
    sids: list[str],
    *,
    policy: Callable[[], bool] | None = None,
    sacl: Callable[[str, list[str]], bool] | None = None,
) -> tuple[bool, bool]:
    if not sids:
        return False, False
    try:
        if policy is not None and sacl is not None:
            return policy(), all(sacl(root, sids) for root in roots)
        native = Native()
        with native.privilege():
            return native.policy(), all(native.sacl(root, sids) for root in roots)
    except Exception:
        return False, False
