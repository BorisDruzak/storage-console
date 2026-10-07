"""Read-only checks for code that will execute as LocalSystem."""

from __future__ import annotations

import ctypes
import importlib.util
import os
import sys
import time
from pathlib import Path

from .errors import SecurityError
from .security import _Ace, _Acl, _api

# Windows servicing identity, not a deployment-specific SID.
_OWNERS = {"S-1-5-18", "S-1-5-32-544",
           "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"}
_WRITE = 0x500D0156


def _safe_acl(path: Path, *, ancestor: bool = False) -> None:
    api = _api()
    owner, acl, descriptor = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    def sid(value: int | None) -> str:
        result = ctypes.c_void_p()
        if not value or not api.advapi.ConvertSidToStringSidW(value, ctypes.byref(result)):
            raise SecurityError("UNSAFE_SERVICE_INSTALLATION")
        try:
            return ctypes.wstring_at(result.value) if result.value else ""
        finally:
            api.kernel.LocalFree(result)
    try:
        if api.advapi.GetNamedSecurityInfoW(
            str(path), 1, 5, ctypes.byref(owner), None, ctypes.byref(acl), None,
            ctypes.byref(descriptor),
        ) or not acl.value or sid(owner.value) not in _OWNERS:
            raise SecurityError("UNSAFE_SERVICE_INSTALLATION")
        header = ctypes.cast(acl, ctypes.POINTER(_Acl)).contents
        for index in range(header.count):
            pointer = ctypes.c_void_p()
            if not api.advapi.GetAce(acl, index, ctypes.byref(pointer)) or not pointer.value:
                raise SecurityError("UNSAFE_SERVICE_INSTALLATION")
            ace = ctypes.cast(pointer, ctypes.POINTER(_Ace)).contents
            # Conservative: complex conditional/object ACLs require explicit review.
            if ace.kind not in {0, 1}:
                raise SecurityError("UNSAFE_SERVICE_INSTALLATION")
            mask = _WRITE & ~6 if ancestor else _WRITE
            if ace.kind == 0 and not ace.flags & 8 and ace.mask & mask:
                if sid(pointer.value + _Ace.sid.offset) not in _OWNERS:
                    raise SecurityError("UNSAFE_SERVICE_INSTALLATION")
    finally:
        if descriptor.value:
            api.kernel.LocalFree(descriptor)


def validate_installation() -> None:
    """Require an installed, protected interpreter/package; never repair ACLs."""
    roots = {Path(sys.prefix), Path(sys.base_prefix)}
    module = importlib.util.find_spec("collectors.windows.service")
    if module is None or module.origin is None or not any(
        Path(module.origin).is_relative_to(root) for root in roots
    ):
        raise SecurityError("SERVICE_WHEEL_REQUIRED")
    # .pth files may add code directories outside either interpreter root.
    for item in sys.path:
        if not item:
            continue  # -I removes the implicit current working directory.
        path = Path(item)
        if not path.is_absolute():
            raise SecurityError("UNSAFE_SERVICE_INSTALLATION")
        if not any(path.is_relative_to(root) for root in roots):
            if path.exists():
                roots.add(path)
            elif path.suffix.casefold() == ".zip":
                roots.add(path.parent)
            else:
                raise SecurityError("UNSAFE_SERVICE_INSTALLATION")
    checked: set[Path] = set()
    checked_ancestors: set[Path] = set()
    deadline, count = time.monotonic() + 30, 0
    def check(path: Path, *, ancestor: bool = False) -> None:
        nonlocal count
        count += 1
        if count > 100000 or time.monotonic() >= deadline:
            raise SecurityError("SERVICE_INSTALLATION_CHECK_TIMEOUT")
        if getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
            raise SecurityError("UNSAFE_SERVICE_INSTALLATION")
        _safe_acl(path, ancestor=ancestor)
    for root in sorted(roots, key=lambda path: -len(path.parts)):
        for parent in root.parents:
            if parent not in checked and parent not in checked_ancestors:
                check(parent, ancestor=True)
                checked_ancestors.add(parent)
        pending = [root]
        while pending:
            path = pending.pop()
            if path in checked:
                continue
            check(path)
            checked.add(path)
            if path.is_dir():
                with os.scandir(path) as entries:
                    pending.extend(Path(entry.path) for entry in entries)
