"""Bounded local session/handle caches; only scoped evidence can leave the host."""

import ctypes
import json
import os
from collections import OrderedDict
from collections.abc import Callable
from datetime import timedelta
from hashlib import sha256
from pathlib import PureWindowsPath
from typing import Any

from .events import AuditEvent


def path_parts(path: str) -> tuple[str, ...] | None:
    value = PureWindowsPath(path)
    if (
        not value.is_absolute()
        or len(value.drive) != 2
        or value.drive[1] != ":"
        or any(char in path for char in '\x00\r\n/*?"<>|')
        or any(
            p in {".", ".."} or p.endswith((".", " ")) or ":" in p
            for p in path.replace("/", "\\").split("\\")[1:]
        )
    ):
        return None
    return tuple(value.parts)


def ordinal_equal(left: str, right: str) -> bool:
    if os.name == "nt":
        function = vars(ctypes)["WinDLL"]("kernel32").CompareStringOrdinal
        function.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_int,
            ctypes.c_wchar_p,
            ctypes.c_int,
            ctypes.c_int,
        ]
        function.restype = ctypes.c_int
        return bool(function(left, -1, right, -1, True) == 2)

    # Conservative portable test fallback: never expand a character (ß -> SS).
    def key(value: str) -> str:
        return "".join(c.upper() if len(c.upper()) == 1 else c for c in value)

    return key(left) == key(right)


class AuditScope:
    def __init__(
        self, roots: dict[str, str], *, guard: Callable[[str], bool] | None = None
    ) -> None:
        if not 1 <= len(roots) <= 16 or any(
            not path_parts(root) or not volume for root, volume in roots.items()
        ):
            raise ValueError("AUDIT_SCOPE_INVALID")
        self.roots = {path_parts(root): volume for root, volume in roots.items()}
        self.guard = guard

    def select(self, event: AuditEvent) -> AuditEvent | None:
        if event.event_id != 4663 or event.object_type != "File" or not event.path:
            return None
        parts = path_parts(event.path)
        if parts is None:
            return None
        matches = {
            volume
            for root, volume in self.roots.items()
            if root is not None
            and len(parts) >= len(root)
            and all(ordinal_equal(a, b) for a, b in zip(parts, root, strict=False))
        }
        if len(matches) != 1:
            return None
        if self.guard is not None and not self.guard(event.path):
            return None
        # A configured lexical alias is not event-time ancestry or FileId proof.
        # Correlation must verify historical USN paths; never resolve the current file.
        return event.model_copy(update={"volume_id": matches.pop()})


class Selector:
    def __init__(
        self,
        scope: AuditScope,
        *,
        capacity: int = 64,
        state: dict[str, Any] | None = None,
    ) -> None:
        if not 1 <= capacity <= 256:
            raise ValueError("AUDIT_CACHE_INVALID")
        self.scope, self.capacity = scope, capacity
        self.sessions: OrderedDict[str, AuditEvent] = OrderedDict()
        self.accesses: OrderedDict[str, AuditEvent] = OrderedDict()
        self.pending: OrderedDict[str, AuditEvent] = OrderedDict()
        self.barriers: OrderedDict[str, int] = OrderedDict()
        if state:
            for name in ("sessions", "accesses", "pending"):
                values = state.get(name, [])
                if len(values) > capacity:
                    raise ValueError("AUDIT_CACHE_INVALID")
                for value in values:
                    event = AuditEvent.model_validate(value)
                    self._add(getattr(self, name), event)
            self.barriers.update(state.get("barriers", {}))
            if len(self.barriers) > capacity:
                raise ValueError("AUDIT_CACHE_INVALID")

    def _add(self, cache: OrderedDict[str, AuditEvent], event: AuditEvent) -> None:
        cache[str(event.generation) + ":" + str(event.record_id)] = event
        while len(cache) > self.capacity:
            cache.popitem(last=False)
        # JSON escaping of long/Cyrillic fields counts toward the byte budget.
        while cache and sum(len(e.model_dump_json().encode()) for e in cache.values()) > 256 * 1024:
            cache.popitem(last=False)

    @staticmethod
    def _handle_key(event: AuditEvent) -> str:
        return sha256(
            json.dumps(
                [
                    str(event.host_id),
                    event.boot_id,
                    str(event.generation),
                    event.logon_id,
                    event.sid,
                    event.process_id,
                    event.handle_id,
                ],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    @staticmethod
    def _context(a: AuditEvent, b: AuditEvent) -> bool:
        return (
            (a.host_id, a.boot_id, a.generation, a.logon_id, a.sid)
            == (b.host_id, b.boot_id, b.generation, b.logon_id, b.sid)
            and a.sid is not None
            and a.logon_id is not None
        )

    def _delete(self, event: AuditEvent) -> AuditEvent | None:
        if not event.handle_id or not event.process_id:
            return None
        candidates = [
            access
            for access in self.accesses.values()
            if self._context(access, event)
            and (access.handle_id, access.process_id) == (event.handle_id, event.process_id)
            and access.record_id < event.record_id
            and access.record_id > self.barriers.get(self._handle_key(event), 0)
            and timedelta(0) <= event.occurred_at - access.occurred_at <= timedelta(seconds=30)
            and access.access_mask is not None
            and access.access_mask & 0x10000
        ]
        if not candidates or any(
            a.volume_id != candidates[0].volume_id
            or not ordinal_equal(a.path or "", candidates[0].path or "")
            for a in candidates
        ):
            return None
        access = max(candidates, key=lambda a: a.record_id)
        return event.model_copy(
            update={"volume_id": access.volume_id, "linked_record_ids": [access.record_id]}
        )

    def process(self, event: AuditEvent) -> list[AuditEvent]:
        # Event-time expiry, not arrival-time expiry (outbox replay can be late).
        for cache, age in ((self.sessions, 86400), (self.accesses, 30), (self.pending, 30)):
            for key, old in list(cache.items()):
                if event.occurred_at - old.occurred_at > timedelta(seconds=age):
                    del cache[key]
        if event.event_id == 4624:
            self._add(self.sessions, event)
            return []
        if event.event_id == 4660:
            matched = self._delete(event)
            if matched:
                return [matched]
            self._add(self.pending, event)
            return []
        selected = self.scope.select(event)
        if selected is None:
            if event.event_id == 4663:
                key = self._handle_key(event)
                for old_key, access in list(self.accesses.items()):
                    if self._handle_key(access) == key:
                        del self.accesses[old_key]
                self.barriers[key] = max(event.record_id, self.barriers.get(key, 0))
                while len(self.barriers) > self.capacity:
                    self.barriers.popitem(last=False)
                    # Loss of the bounded reuse barrier is a loss of matching proof.
                    self.accesses.clear()
            return []
        self._add(self.accesses, selected)
        result = [selected]
        sessions = [
            session
            for session in self.sessions.values()
            if self._context(session, selected)
            and session.record_id < selected.record_id
            and timedelta(0) <= selected.occurred_at - session.occurred_at <= timedelta(days=1)
        ]
        # A reused numeric ID or ambiguous session never releases client data.
        if len(sessions) == 1:
            # Link eligibility is local policy; the original session evidence is immutable.
            result.insert(0, sessions[0])
        for key, pending in list(self.pending.items()):
            matched = self._delete(pending)
            if matched:
                result.append(matched)
                del self.pending[key]
        return result

    def snapshot(self) -> dict[str, Any]:
        return {
            "barriers": dict(self.barriers),
            **{
                name: [event.model_dump(mode="json") for event in getattr(self, name).values()]
                for name in ("sessions", "accesses", "pending")
            },
        }
