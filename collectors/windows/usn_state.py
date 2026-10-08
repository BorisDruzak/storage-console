"""Scoped ancestry and logical USN events committed together with the read cursor."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from collectors.common.outbox import Checkpoint, Outbox
from packages.contracts.changes import ChangeRecord, EventType
from packages.contracts.common import BatchEnvelope

from .usn import USN_CODES, UsnError, UsnRecord

Identifier = Annotated[str, Field(pattern="^[0-9a-f]{32}$")]
Unsigned = Annotated[int, Field(ge=0, le=2**64 - 1)]


class _Cursor(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    version: Literal[1] = 1
    volume: str
    scope: str
    journal: Unsigned
    cursor: Annotated[int, Field(ge=0, le=2**63 - 1)]
    status: str | None = None
    nodes: Annotated[int, Field(ge=0, le=100000)] = 0
    pending_renames: Annotated[int, Field(ge=0, le=100000)] = 0


class _Node(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    parent: Identifier | None = None
    name: str = ""
    root_parts: Annotated[int, Field(ge=1, le=32)] | None = None
    created: bool = False
    outside: bool = False
    write_emitted: bool = False
    rename_emitted: bool = False
    rename_usn: Unsigned | None = None
    rename_reason: Annotated[int, Field(ge=0, le=2**32 - 1)] = 0
    rename_parts: Annotated[int, Field(ge=1, le=32)] | None = None
    write_usn: Unsigned | None = None
    write_time: str | None = None
    write_path_digest: Annotated[str, Field(pattern="^[0-9a-f]{64}$")] | None = None
    write_parent: Identifier | None = None
    write_reason: Annotated[int, Field(ge=0, le=2**32 - 1)] = 0
    write_count: Annotated[int, Field(ge=0, le=32)] = 0


class UsnState:
    def __init__(self, box: Outbox, volume: str, scope_fingerprint: str) -> None:
        self.box, self.volume, self.scope = box, volume, scope_fingerprint
        self.stream = "windows:usn:" + sha256(volume.encode()).hexdigest()[:32]
        self._load()

    def _load(self) -> tuple[Checkpoint, _Cursor | None]:
        checkpoint = self.box.checkpoint(self.stream)
        if checkpoint.value is None:
            if checkpoint.revision:
                raise UsnError("USN_STATE_INVALID")
            return checkpoint, None
        try:
            state = _Cursor.model_validate(checkpoint.value)
            if state.volume != self.volume or state.scope != self.scope:
                raise UsnError("USN_STATE_INVALID")
            if state.status is not None and state.status not in USN_CODES:
                raise UsnError("USN_STATE_INVALID")
            return checkpoint, state
        except (ValidationError, TypeError, ValueError):
            raise UsnError("USN_STATE_INVALID") from None

    @property
    def cursor(self) -> int:
        _, state = self._load()
        return state.cursor if state else 0

    @property
    def status(self) -> str | None:
        _, state = self._load()
        if state is None:
            return "USN_BOOTSTRAP"
        return state.status or ("USN_PATH_UNKNOWN" if state.pending_renames else None)

    def fail(self, code: str) -> None:
        checkpoint, state = self._load()
        if state is None:
            raise UsnError(code)
        # Gap is latched: a later successful query does not erase missing history.
        if state.status == "CONTINUITY_GAP" or state.status == code:
            return
        self.box.advance(self.stream, checkpoint.revision,
                         state.model_copy(update={"status": code}).model_dump())

    def check_continuity(self, journal: int, first: int, next_usn: int) -> None:
        _, state = self._load()
        if state is not None and (
            journal != state.journal or not first <= state.cursor <= next_usn
        ):
            self.fail("CONTINUITY_GAP")

    def _key(self, identifier: str) -> str:
        if len(identifier) != 32 or any(c not in "0123456789abcdef" for c in identifier):
            raise UsnError("USN_STATE_INVALID")
        return self.stream + ":node:" + identifier

    def initialize(
        self, journal: int, cursor: int, nodes: Mapping[str, Mapping[str, object]],
    ) -> None:
        checkpoint, existing = self._load()
        if existing is not None or len(nodes) > 100000:
            raise UsnError("USN_STATE_INVALID")
        updates: dict[str, tuple[int, object]] = {}
        for identifier, raw in nodes.items():
            value = dict(raw)
            root = value.pop("root", None)
            if root is not None:
                if not isinstance(root, str):
                    raise UsnError("USN_STATE_INVALID")
                chunks = [root[i:i + 2048] for i in range(0, max(1, len(root)), 2048)]
                value["root_parts"] = len(chunks)
                for number, chunk in enumerate(chunks):
                    key = self._key(identifier) + ":root:" + str(number)
                    updates[key] = (self.box.checkpoint(key).revision, chunk)
            value["created"] = True
            node = _Node.model_validate(value)
            key = self._key(identifier)
            updates[key] = (self.box.checkpoint(key).revision, node.model_dump())
        state = _Cursor(volume=self.volume, scope=self.scope, journal=journal, cursor=cursor,
                        nodes=len(nodes))
        # Bootstrap is allowed only for a new stream. Larger inventories are
        # chunked with an explicit incomplete status, never treated as live coverage.
        entries = list(updates.items())
        for start in range(0, len(entries), 512):
            self.box.advance(self.stream, checkpoint.revision,
                             state.model_copy(update={"status": "USN_BOOTSTRAP"}).model_dump(),
                             checkpoint_updates=dict(entries[start:start + 512]))
            checkpoint = self.box.checkpoint(self.stream)
        self.box.advance(self.stream, checkpoint.revision, state.model_dump())

    def consume(
        self, journal: int, cursor: int, records: Sequence[UsnRecord],
    ) -> tuple[ChangeRecord, ...]:
        checkpoint, state = self._load()
        if state is None:
            raise UsnError("USN_BOOTSTRAP")
        if state.status is not None:
            return ()
        if journal != state.journal or cursor < state.cursor:
            self.fail("CONTINUITY_GAP")
            return ()
        if cursor == state.cursor:
            return ()
        if len(records) > 256 or any(not state.cursor <= r.usn < cursor for r in records):
            raise UsnError("USN_MALFORMED")
        loaded: dict[str, tuple[int, _Node | None]] = {}
        updates: dict[str, tuple[int, object]] = {}
        events: list[ChangeRecord] = []
        node_count = state.nodes
        pending_renames = state.pending_renames

        def get(identifier: str) -> _Node | None:
            if identifier not in loaded:
                saved = self.box.checkpoint(self._key(identifier))
                try:
                    node = _Node.model_validate(saved.value) if saved.value is not None else None
                except ValidationError:
                    raise UsnError("USN_STATE_INVALID") from None
                loaded[identifier] = (saved.revision, node)
            return loaded[identifier][1]

        def put(identifier: str, node: _Node | None) -> None:
            get(identifier)
            revision = loaded[identifier][0]
            loaded[identifier] = (revision, node)
            updates[self._key(identifier)] = (revision, node.model_dump() if node else None)

        def text(identifier: str, kind: str, count: int) -> str | None:
            parts = []
            for number in range(count):
                key = self._key(identifier) + ":" + kind + ":" + str(number)
                value = updates[key][1] if key in updates else self.box.checkpoint(key).value
                if not isinstance(value, str):
                    raise UsnError("USN_STATE_INVALID")
                parts.append(value)
            return "".join(parts) or "\\"

        def path(identifier: str) -> str | None:
            parts: list[str] = []
            visited: set[str] = set()
            for _ in range(66):
                if identifier in visited:
                    raise UsnError("USN_STATE_INVALID")
                visited.add(identifier)
                node = get(identifier)
                if node is None:
                    return None
                if node.outside:
                    return None
                if node.root_parts is not None:
                    prefix = text(identifier, "root", node.root_parts)
                    assert prefix is not None
                    return "\\".join([prefix.rstrip("\\"), *reversed(parts)]) or "\\"
                parts.append(node.name)
                if node.parent is None:
                    return None
                identifier = node.parent
            return None

        def outside(identifier: str) -> bool:
            visited: set[str] = set()
            for _ in range(66):
                if identifier in visited:
                    raise UsnError("USN_STATE_INVALID")
                visited.add(identifier)
                node = get(identifier)
                if node is None or node.root_parts is not None:
                    return False
                if node.outside:
                    return True
                if node.parent is None:
                    return False
                identifier = node.parent
            return False

        def emit(
            record: UsnRecord, kind: EventType, old: str | None, new: str | None, *,
            event_usn: int | None = None, reason: int | None = None,
            occurred_at: datetime | None = None, parent_id: str | None = None,
        ) -> None:
            identity = sha256((self.volume + ":" + str(journal) + ":" +
                               str(record.usn if event_usn is None else event_usn) + ":" +
                               record.file_id + ":" + kind).encode()).hexdigest()
            events.append(ChangeRecord(
                occurred_at=occurred_at or record.occurred_at, volume_identity=self.volume,
                file_id=record.file_id,
                parent_file_id=parent_id if kind == "WRITE" else record.parent_id,
                event_type=kind,
                old_relative_path=old, new_relative_path=new,
                reason_mask=f"0x{record.reason if reason is None else reason:08X}",
                source_event_id="ntfs-usn:" + identity,
                path_quality=("COMPLETE" if (
                    old is not None and new is not None if kind == "RENAME" else
                    old is not None if kind == "DELETE" else new is not None
                ) else "UNAVAILABLE"),
            ))

        def flush_write(node: _Node, record: UsnRecord, known_path: str | None) -> None:
            if node.write_usn is None:
                return
            # The event keeps the first data record's time. Later ancestry changes
            # cannot rewrite that historical path using the current cache.
            if (known_path is None or node.write_path_digest is None
                    or sha256(known_path.encode()).hexdigest() != node.write_path_digest):
                known_path = None
            emit(record, "WRITE", None, known_path, event_usn=node.write_usn,
                 reason=node.write_reason | (record.reason & 0x80000000),
                 occurred_at=datetime.fromisoformat(node.write_time) if node.write_time else None,
                 parent_id=node.write_parent)
            node.write_usn, node.write_time = None, None
            node.write_path_digest = None
            node.write_parent = None
            node.write_reason, node.write_count = 0, 0
            node.write_emitted = not bool(record.reason & 0x80000000)

        for record in records:
            node = get(record.file_id)
            parent_path = path(record.parent_id)
            previous_path = path(record.file_id) if node else None
            # NTFS accumulates NEW with later reasons until CLOSE. Proof belongs
            # to this destination in the still-open cycle, not merely its cache.
            rename_summary = bool(
                record.reason & 0x2000
                and node and node.rename_emitted and node.rename_usn is None
                and node.parent == record.parent_id and node.name == record.name
            )
            if parent_path is None and (outside(record.parent_id) or outside(record.file_id)):
                # An ancestor's proven move-out invalidates descendant membership;
                # subsequent outside noise cannot block unrelated monitored files.
                if node is not None:
                    flush_write(node, record, None)
                    if record.reason & 0x2000 and node.rename_usn is not None:
                        old = (text(record.file_id, "rename", node.rename_parts)
                               if node.rename_parts else None)
                        emit(record, "RENAME", old, None, event_usn=node.rename_usn,
                             reason=node.rename_reason | record.reason)
                        pending_renames -= 1
                        for number in range(node.rename_parts or 0):
                            key = self._key(record.file_id) + ":rename:" + str(number)
                            revision = (updates[key][0] if key in updates
                                        else self.box.checkpoint(key).revision)
                            updates[key] = (revision, None)
                        node.rename_usn, node.rename_parts, node.rename_reason = None, None, 0
                    put(record.file_id, _Node(
                        outside=True, created=node.created, rename_usn=node.rename_usn,
                        rename_reason=node.rename_reason, rename_parts=node.rename_parts,
                    ))
                continue
            if (node is not None and outside(record.file_id) and parent_path is not None
                    and node.rename_usn is None):
                node = None
            paired_rename = bool(record.reason & 0x2000 and node and node.rename_usn is not None)
            if node is not None and node.root_parts is not None:
                if record.reason & 0x3200:
                    self.fail("CONTINUITY_GAP")
                    return ()
                continue
            if parent_path is None and node is None:
                # Crucially do not persist even the unknown record's name.
                continue
            if record.reason & 0x1000:
                if node is not None and previous_path is not None:
                    if record.reason & 7 and not node.write_emitted:
                        if node.write_usn is None:
                            node.write_usn = record.usn
                            node.write_time = record.occurred_at.isoformat()
                            node.write_path_digest = sha256(previous_path.encode()).hexdigest()
                            node.write_parent = record.parent_id
                        node.write_reason |= record.reason
                        node.write_count = min(32, node.write_count + 1)
                    if node.rename_usn is None:
                        pending_renames += 1
                    chunks = [previous_path[i:i + 2048] for i in range(0, len(previous_path), 2048)]
                    for number, chunk in enumerate(chunks):
                        key = self._key(record.file_id) + ":rename:" + str(number)
                        revision = self.box.checkpoint(key).revision
                        updates[key] = (revision, chunk)
                    node = node.model_copy(update={"rename_usn": record.usn,
                                                  "rename_reason": record.reason,
                                                  "rename_parts": len(chunks)})
                    put(record.file_id, node)
                continue
            if record.reason & 0x2000 and node is not None and node.rename_usn is not None:
                pending_renames -= 1
                old = (text(record.file_id, "rename", node.rename_parts)
                       if node.rename_parts else None)
                new = (parent_path.rstrip("\\") + "\\" + record.name
                       if parent_path is not None else None)
                flush_write(node, record, old)
                emit(record, "RENAME", old, new, event_usn=node.rename_usn,
                     reason=node.rename_reason | record.reason)
                for number in range(node.rename_parts or 0):
                    key = self._key(record.file_id) + ":rename:" + str(number)
                    revision = (
                        updates[key][0] if key in updates else self.box.checkpoint(key).revision
                    )
                    updates[key] = (revision, None)
                if parent_path is None:
                    put(record.file_id, _Node(outside=True))
                    continue
                node = node.model_copy(update={"parent": record.parent_id, "name": record.name,
                                              "rename_usn": None, "rename_reason": 0,
                                              "rename_parts": None, "outside": False,
                                              "rename_emitted": True})
            elif parent_path is None:
                # No trustworthy ancestry/transition: do not invent an event kind
                # or commit this raw record's outside name/cursor.
                self.fail("USN_PATH_UNKNOWN")
                return ()
            elif node is None:
                node_count += 1
                if node_count > 100000:
                    raise UsnError("USN_CAPACITY")
                node = _Node(parent=record.parent_id, name=record.name)
            else:
                node = node.model_copy(update={
                    "parent": record.parent_id, "name": record.name,
                    "rename_emitted": bool(node.rename_emitted and
                                           node.parent == record.parent_id and
                                           node.name == record.name),
                })
            put(record.file_id, node)
            current_path = path(record.file_id)
            if record.reason & 0x2000 and not paired_rename and not rename_summary:
                emit(record, "RENAME", None, current_path)
                node.created = True
                node.rename_emitted = True
            if record.reason & 0x100 and not node.created:
                emit(record, "CREATE", None, current_path)
                node.created = True
            if record.reason & 7 and not node.write_emitted:
                if node.write_usn is None:
                    node.write_usn, node.write_time = record.usn, record.occurred_at.isoformat()
                    node.write_path_digest = (sha256(current_path.encode()).hexdigest()
                                              if current_path is not None else None)
                    node.write_parent = record.parent_id
                node.write_reason |= record.reason
                node.write_count += 1
            if node.write_usn is not None and (
                record.reason & 0x80000200 or node.write_count >= 32
            ):
                flush_write(node, record, current_path)
            if record.reason & 0x80000000:
                node.write_emitted = False
                node.rename_emitted = False
                classes: tuple[tuple[int, EventType], ...] = (
                    (0x8000, "METADATA_CHANGE"), (0x800, "SECURITY_CHANGE"),
                )
                for mask, kind in classes:
                    if record.reason & mask:
                        emit(record, kind, None, current_path)
            if record.reason & 0x200:
                emit(record, "DELETE", previous_path or current_path, None)
                put(record.file_id, None)
            else:
                put(record.file_id, node)
        value = state.model_copy(update={"cursor": cursor, "nodes": node_count,
                                         "pending_renames": pending_renames}).model_dump()
        if events:
            first, last = min(e.occurred_at for e in events), max(e.occurred_at for e in events)
            payload = BatchEnvelope[ChangeRecord](
                collector_id=self.box.collector_id, batch_id="usn:" + sha256(
                    (self.stream + ":" + str(journal) + ":" + str(state.cursor) + ":" + str(cursor))
                    .encode()).hexdigest(), schema_version=1, sent_at=last,
                first_event_at=first, last_event_at=last, record_count=len(events), records=events,
            )
            self.box.enqueue("changes", payload, self.stream, checkpoint.revision, value,
                             checkpoint_updates=updates)
        else:
            self.box.advance(self.stream, checkpoint.revision, value, checkpoint_updates=updates)
        return tuple(events)
