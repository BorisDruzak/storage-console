"""Explicit operator-only superset transitions; normal activation remains strict."""

import base64
import json
import re
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import UUID

from collectors.common.outbox import Checkpoint, Outbox

from .inventory import Scope
from .producer import _state
from .usn_state import UsnState, _Cursor, _Node


def additional_roots(current: Scope, proposed: Scope) -> tuple[str, ...]:
    old = {root.casefold() for root in current.roots}
    new = {root.casefold() for root in proposed.roots}
    if not old < new:
        raise ValueError("SCOPE_EXTENSION_INVALID")
    return tuple(root for root in proposed.roots if root.casefold() not in old)


@dataclass(frozen=True)
class ScopeNode:
    volume: str
    file_id: str
    parent_id: str | None
    name: str
    root: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.volume, str)
            or not self.volume.isascii()
            or not 1 <= len(self.volume) <= 255
            or not isinstance(self.file_id, str)
            or re.fullmatch(r"[0-9a-f]{32}", self.file_id) is None
            or self.parent_id is not None
            and (
                not isinstance(self.parent_id, str)
                or re.fullmatch(r"[0-9a-f]{32}", self.parent_id) is None
            )
            or not isinstance(self.name, str)
            or len(self.name.encode("utf-16-le")) > 510
            or self.root is not None
            and (not isinstance(self.root, str) or len(self.root) > 32700)
        ):
            raise ValueError("SCOPE_NODE_INVALID")


def commit_scope(
    box: Outbox,
    current: Scope,
    proposed: Scope,
    nodes: Iterable[ScopeNode],
    fences: Mapping[str, tuple[int, int]],
    transition_id: str,
) -> None:
    additions = additional_roots(current, proposed)
    identity = UUID(transition_id).hex
    if not 1 <= len(fences) <= 32:
        raise ValueError("SCOPE_EXTENSION_INVALID")
    readonly = Outbox(box.path, box.collector_id, box.limits, read_only=True)
    marker = "windows:scope-transition"
    previous = readonly.checkpoint(marker)
    if previous.value is not None and not isinstance(previous.value, dict):
        raise ValueError("SCOPE_RECEIPT_INVALID")
    if isinstance(previous.value, dict) and previous.value.get("id") == identity:
        if previous.value.get("new_scope") != proposed.fingerprint:
            raise ValueError("SCOPE_EXTENSION_CONFLICT")
        return
    inventory = _state(readonly, "windows:inventory", current)
    with readonly._transaction() as connection:
        existing = connection.execute(
            "SELECT value FROM checkpoints WHERE substr(stream,1,12)='windows:usn:' "
            "AND length(stream)=44 LIMIT 33"
        ).fetchall()
    if len(existing) > 32 or any(json.loads(row[0])["volume"] not in fences for row in existing):
        raise ValueError("SCOPE_EXTENSION_INCOMPLETE")
    states = {}
    for volume, (journal, fence) in fences.items():
        if type(journal) is not int or type(fence) is not int or journal < 1 or fence < 0:
            raise ValueError("SCOPE_EXTENSION_INVALID")
        state = UsnState(readonly, volume, current.fingerprint)
        checkpoint, saved = state._load()
        if saved is None:
            raise ValueError("SCOPE_EXTENSION_INCOMPLETE")
        if saved.journal != journal or saved.cursor > fence:
            raise ValueError("SCOPE_JOURNAL_CHANGED")
        states[volume] = (state, checkpoint, saved)
    counts = dict.fromkeys(fences, 0)
    roots = 0

    def updates(read_checkpoint: Callable[[str], Checkpoint]) -> Iterator[tuple[str, int, object]]:
        nonlocal roots
        for node in nodes:
            if node.volume not in states:
                raise ValueError("SCOPE_VOLUME_MISMATCH")
            state = states[node.volume][0]
            key = state._key(node.file_id)
            prior = read_checkpoint(key)
            if prior.value is not None:
                raise ValueError("SCOPE_IDENTITY_CONFLICT")
            value = _Node(
                parent=node.parent_id,
                name=node.name,
                created=True,
                observed_since_usn=fences[node.volume][1],
            )
            if node.root is not None:
                roots += 1
                chunks = [node.root[i : i + 2048] for i in range(0, max(1, len(node.root)), 2048)]
                value.root_parts = len(chunks)
                for number, chunk in enumerate(chunks):
                    root_key = key + ":root:" + str(number)
                    yield root_key, read_checkpoint(root_key).revision, chunk
            counts[node.volume] += 1
            if counts[node.volume] > 100000:
                raise ValueError("SCOPE_CAPACITY")
            yield key, prior.revision, value.model_dump()
        if roots != len(additions):
            raise ValueError("SCOPE_EXTENSION_INCOMPLETE")
        for volume, (state, checkpoint, saved) in states.items():
            assert saved is not None
            cursor_value = _Cursor.model_validate(
                {
                    **saved.model_dump(),
                    "scope": proposed.fingerprint,
                    "nodes": saved.nodes + counts[volume],
                }
            )
            yield state.stream, checkpoint.revision, cursor_value.model_dump()
        if isinstance(inventory.value, dict):
            yield "windows:inventory", inventory.revision, {
                **inventory.value, "scope": proposed.fingerprint, "completed": False,
            }

    box.advance_stream(
        marker,
        previous.revision,
        {
            "id": identity,
            "phase": "COMMITTED",
            "old_scope": current.fingerprint,
            "new_scope": proposed.fingerprint,
            "fences": dict(fences),
        },
        updates,
    )


RECEIPT_NAME = "scope-extension.json"


def _backup_names(identity: str) -> tuple[str, str]:
    identity = UUID(identity).hex
    return (
        "scope-before-config-" + identity + ".bin",
        "scope-before-activation-" + identity + ".bin",
    )


def prepare_receipt(
    state: Any,
    original: Any,
    proposed: Any,
    transition_id: str,
    *,
    stage_info: dict[str, Any] | None = None,
) -> None:
    from .configuration import PrivateConfig

    additional_roots(original.scope, proposed.scope)
    identity = UUID(transition_id).hex
    proposed = PrivateConfig.model_validate_json(proposed.model_dump_json())
    if original.model_dump(exclude={"roots"}) != proposed.model_dump(exclude={"roots"}):
        raise ValueError("SCOPE_CREDENTIAL_CHANGED")
    before = state.read("config.json", 131072)
    activation = state.read("usn-activation.json", 4096)
    if PrivateConfig.model_validate_json(before) != original:
        raise ValueError("SCOPE_CONFIG_CHANGED")
    old_activation = json.loads(activation)
    if old_activation != {"version": 1, "scope": original.scope.fingerprint, "enabled": True}:
        raise ValueError("SCOPE_USN_REQUIRED")
    if (state.root / RECEIPT_NAME).exists():
        previous_bytes = state.read(RECEIPT_NAME, 1048576)
        previous = json.loads(previous_bytes)
        if previous.get("phase") != "DONE":
            raise ValueError("SCOPE_EXTENSION_PENDING")
        prior_identity = UUID(previous["id"]).hex
        state.write("scope-extension-receipt-" + prior_identity + ".json", previous_bytes)
    new_config = proposed.model_dump_json().encode()
    new_activation = json.dumps(
        {
            "version": 1,
            "scope": proposed.scope.fingerprint,
            "enabled": True,
        },
        separators=(",", ":"),
    ).encode()
    before_name, activation_name = _backup_names(identity)
    if (state.root / before_name).exists() or (state.root / activation_name).exists():
        raise ValueError("SCOPE_EXTENSION_CONFLICT")
    state.write(before_name, before)
    state.write(activation_name, activation)
    state.write(
        RECEIPT_NAME,
        json.dumps(
            {
                "version": 1,
                "id": identity,
                "phase": "PREPARED",
                "original_config_sha256": sha256(before).hexdigest(),
                "proposed_config_sha256": sha256(new_config).hexdigest(),
                "original_scope": original.scope.fingerprint,
                "new_scope": proposed.scope.fingerprint,
                "new_config": base64.b64encode(new_config).decode(),
                "new_activation": base64.b64encode(new_activation).decode(),
                "stage": stage_info,
            },
            separators=(",", ":"),
        ).encode(),
    )


def recover_scope(state: Any) -> bool:
    from .configuration import PrivateConfig

    if not (state.root / RECEIPT_NAME).exists():
        return False
    receipt = json.loads(state.read(RECEIPT_NAME, 1048576))
    if (
        not isinstance(receipt, dict)
        or receipt.get("version") != 1
        or receipt.get("phase") not in {"PREPARED", "DONE"}
    ):
        raise ValueError("SCOPE_RECEIPT_INVALID")
    before_name, activation_name = _backup_names(receipt["id"])
    if receipt["phase"] == "DONE":
        # Historical receipt: normal subsequent rotation/disable remains valid.
        return False
    before = state.read(before_name, 131072)
    activation = state.read(activation_name, 4096)
    proposed_bytes = base64.b64decode(receipt["new_config"], validate=True)
    new_activation = base64.b64decode(receipt["new_activation"], validate=True)
    if (
        sha256(before).hexdigest() != receipt["original_config_sha256"]
        or sha256(proposed_bytes).hexdigest() != receipt["proposed_config_sha256"]
    ):
        raise ValueError("SCOPE_RECEIPT_INVALID")
    original = PrivateConfig.model_validate_json(before)
    proposed = PrivateConfig.model_validate_json(proposed_bytes)
    if (
        receipt.get("original_scope") != original.scope.fingerprint
        or receipt.get("new_scope") != proposed.scope.fingerprint
        or json.loads(activation)
        != {"version": 1, "scope": original.scope.fingerprint, "enabled": True}
        or json.loads(new_activation)
        != {"version": 1, "scope": proposed.scope.fingerprint, "enabled": True}
    ):
        raise ValueError("SCOPE_RECEIPT_INVALID")
    additional_roots(original.scope, proposed.scope)
    if original.model_dump(exclude={"roots"}) != proposed.model_dump(exclude={"roots"}):
        raise ValueError("SCOPE_CREDENTIAL_CHANGED")
    current = state.read("config.json", 131072)
    current_activation = state.read("usn-activation.json", 4096)
    if current not in (before, proposed_bytes) or current_activation not in (
        activation,
        new_activation,
    ):
        raise ValueError("SCOPE_CONFIG_CHANGED")
    readonly = Outbox(
        state.root / "outbox.sqlite3",
        original.collector_id,
        original.settings.limits(),
        read_only=True,
    )
    if readonly.credential_binding() != original.credential_version:
        raise ValueError("SCOPE_CREDENTIAL_CHANGED")
    marker = readonly.checkpoint("windows:scope-transition").value
    if not isinstance(marker, dict) or any(
        marker.get(key) != value
        for key, value in {
            "id": receipt["id"],
            "phase": "COMMITTED",
            "old_scope": original.scope.fingerprint,
            "new_scope": proposed.scope.fingerprint,
        }.items()
    ):
        raise ValueError("SCOPE_EXTENSION_PENDING")
    state.write("config.json", proposed_bytes)
    state.write("usn-activation.json", new_activation)
    receipt["phase"] = "DONE"
    state.write(RECEIPT_NAME, json.dumps(receipt, separators=(",", ":")).encode())
    return True


def validate_fences(
    box: Outbox, current: Scope, proposed: Scope, fences: Mapping[str, tuple[int, int]]
) -> None:
    """Recheck retention immediately before commit, including a resumed stage."""
    from .usn_native import NativeJournal

    journal = NativeJournal(proposed)
    if set(journal.volumes) != set(fences):
        raise ValueError("SCOPE_VOLUME_MISMATCH")
    for volume in journal.volumes:
        saved = UsnState(box, volume, current.fingerprint)._load()[1]
        if saved is None:
            raise ValueError("SCOPE_EXTENSION_INCOMPLETE")
        with closing(journal.open(volume)) as stream:
            info = stream.query()
            info.require_cursor(*fences[volume])
            info.require_cursor(saved.journal, saved.cursor)


def prepare_native_stage(
    stage: Any,
    roots: tuple[str, ...],
    proposed: Scope,
    *,
    stopped: Callable[[], bool] = lambda: False,
    prior_cursors: Mapping[str, tuple[int, int]] | None = None,
) -> dict[str, tuple[int, int]]:
    """New-root-only metadata, fenced by QUERY/READ of the existing journals."""
    from packages.contracts.inventory import FileObjectRecord, VolumeRecord

    from .native import NativeInventory
    from .usn_native import NativeJournal

    journal = NativeJournal(proposed)
    before = {}
    started = time.monotonic()

    def cancelled() -> bool:
        return stopped() or time.monotonic() - started > 120

    for volume in journal.volumes:
        with closing(journal.open(volume)) as stream:
            before[volume] = stream.query()

    def nodes() -> Iterator[ScopeNode]:
        inventory = NativeInventory()
        for root in roots:
            iterator = inventory._root(journal._api, root)
            first = True
            try:
                for observation in iterator:
                    if cancelled():
                        raise ValueError("SCOPE_STOPPED")
                    if observation.error_code:
                        raise ValueError("SCOPE_METADATA_UNAVAILABLE")
                    record = observation.record
                    if isinstance(record, VolumeRecord):
                        continue
                    if not isinstance(record, FileObjectRecord):
                        raise ValueError("SCOPE_METADATA_UNAVAILABLE")
                    if record.object_type == "FILE" and record.link_count != 1:
                        raise ValueError("SCOPE_IDENTITY_CONFLICT")
                    if first and record.object_type != "DIRECTORY":
                        raise ValueError("SCOPE_ROOT_INVALID")
                    yield ScopeNode(
                        record.volume_identity,
                        record.file_id,
                        record.parent_file_id,
                        record.name,
                        record.relative_path if first else None,
                    )
                    first = False
                if first:
                    raise ValueError("SCOPE_METADATA_UNAVAILABLE")
            finally:
                iterator.close()

    stage.write_nodes(nodes(), stopped=cancelled)
    fences = {}
    for volume in journal.volumes:
        with closing(journal.open(volume)) as stream:
            after = stream.query()
            prior_journal, cursor = (prior_cursors or {}).get(
                volume, (before[volume].journal_id, before[volume].next_usn)
            )
            after.require_cursor(prior_journal, cursor)
            after.require_cursor(before[volume].journal_id, cursor)
            for _ in range(8):
                if cursor >= after.next_usn:
                    break
                if cancelled():
                    raise ValueError("SCOPE_STOPPED")
                next_cursor, records = stream.read(after.journal_id, cursor)
                with stage.read_view() as contains:
                    for record in records:
                        if cancelled():
                            raise ValueError("SCOPE_STOPPED")
                        if record.usn >= after.next_usn:
                            continue  # Later changes will be consumed after the baseline fence.
                        if contains(volume, record.file_id) or contains(volume, record.parent_id):
                            raise ValueError("SCOPE_CHANGED")
                if next_cursor <= cursor:
                    raise ValueError("SCOPE_JOURNAL_CHANGED")
                cursor = next_cursor
            if cursor < after.next_usn:
                raise ValueError("SCOPE_CAPACITY")
            fences[volume] = (after.journal_id, after.next_usn)
    return fences


def extend_scope(
    state: Any, new_roots: tuple[str, ...], *, stopped: Callable[[], bool] = lambda: False
) -> None:
    from uuid import uuid4

    from .configuration import PrivateConfig, _outbox, _read, _usn_enabled
    from .scope_stage import ScopeStage

    pending: dict[str, Any] | None = None
    if (state.root / RECEIPT_NAME).exists():
        try:
            recover_scope(state)
        except ValueError as error:
            if str(error) != "SCOPE_EXTENSION_PENDING":
                raise
            pending = json.loads(state.read(RECEIPT_NAME, 1048576))
    original = _read(state)
    proposed = PrivateConfig.model_validate_json(
        original.model_copy(update={"roots": new_roots}).model_dump_json()
    )
    if proposed.scope.fingerprint == original.scope.fingerprint:
        repair_completed_inventory(state, original)
        return
    additions = additional_roots(original.scope, proposed.scope)
    if not _usn_enabled(state, original):
        raise ValueError("SCOPE_USN_REQUIRED")
    box = _outbox(state, original)
    if box.credential_binding() != original.credential_version:
        raise ValueError("SCOPE_CREDENTIAL_CHANGED")
    if pending is None:
        identity = uuid4().hex
        filename = "scope-stage-" + identity + ".sqlite3"
        prior_cursors = {}
        readonly = Outbox(box.path, box.collector_id, box.limits, read_only=True)
        with readonly._transaction() as connection:
            cursors = connection.execute(
                "SELECT value FROM checkpoints WHERE substr(stream,1,12)='windows:usn:' "
                "AND length(stream)=44 LIMIT 33"
            ).fetchall()
        if not 1 <= len(cursors) <= 32:
            raise ValueError("SCOPE_EXTENSION_INCOMPLETE")
        for (raw,) in cursors:
            saved = _Cursor.model_validate_json(raw)
            if saved.scope != original.scope.fingerprint:
                raise ValueError("SCOPE_EXTENSION_CONFLICT")
            prior_cursors[saved.volume] = (saved.journal, saved.cursor)
        state.create_file(filename)
        try:
            stage = ScopeStage(state.root / filename, identity)
            fences = prepare_native_stage(
                stage, additions, proposed.scope, stopped=stopped, prior_cursors=prior_cursors
            )
        except BaseException:
            # Only this unpublished owned stage; published receipts/stages survive.
            stage_path = state.root / filename
            state.validate_file(filename)
            if stage_path.resolve().parent != state.root.resolve():
                raise ValueError("SCOPE_STAGE_UNSAFE") from None
            stage_path.unlink()
            raise
        digest = sha256()
        with (state.root / filename).open("rb") as source:
            while block := source.read(1024 * 1024):
                digest.update(block)
        prepare_receipt(
            state,
            original,
            proposed,
            identity,
            stage_info={
                "file": filename,
                "sha256": digest.hexdigest(),
                "fences": fences,
            },
        )
    else:
        if pending.get("new_scope") != proposed.scope.fingerprint or not pending.get("stage"):
            raise ValueError("SCOPE_EXTENSION_CONFLICT")
        identity = UUID(pending["id"]).hex
        info = pending["stage"]
        filename = "scope-stage-" + identity + ".sqlite3"
        if info.get("file") != filename:
            raise ValueError("SCOPE_STAGE_UNSAFE")
        state.validate_file(filename)
        digest = sha256()
        with (state.root / filename).open("rb") as source:
            while block := source.read(1024 * 1024):
                digest.update(block)
        if digest.hexdigest() != info.get("sha256"):
            raise ValueError("SCOPE_STAGE_CONFLICT")
        stage = ScopeStage(state.root / filename, identity)
        fences = {volume: tuple(value) for volume, value in info["fences"].items()}
    if stopped():
        raise ValueError("SCOPE_STOPPED")
    validate_fences(box, original.scope, proposed.scope, fences)
    with closing(stage.nodes()) as nodes:
        commit_scope(box, original.scope, proposed.scope, nodes, fences, identity)
    recover_scope(state)


def repair_completed_inventory(state: Any, current: Any) -> bool:
    """Explicit operator retry for a prior committed scope; never reset USN state."""
    from .configuration import PrivateConfig, _outbox, _usn_enabled

    if not (state.root / RECEIPT_NAME).exists():
        return False
    receipt = json.loads(state.read(RECEIPT_NAME, 1048576))
    if receipt.get("phase") != "DONE" or receipt.get("new_scope") != current.scope.fingerprint:
        raise ValueError("SCOPE_INVENTORY_CONFLICT")
    identity = UUID(receipt["id"]).hex
    before_name, _ = _backup_names(identity)
    before = state.read(before_name, 131072)
    proposed_bytes = base64.b64decode(receipt["new_config"], validate=True)
    if (sha256(before).hexdigest() != receipt["original_config_sha256"]
            or sha256(proposed_bytes).hexdigest() != receipt["proposed_config_sha256"]):
        raise ValueError("SCOPE_RECEIPT_INVALID")
    original = PrivateConfig.model_validate_json(before)
    proposed = PrivateConfig.model_validate_json(proposed_bytes)
    additional_roots(original.scope, proposed.scope)
    if (original.collector_id != current.collector_id
            or proposed.collector_id != current.collector_id
            or proposed.scope.fingerprint != current.scope.fingerprint
            or receipt.get("original_scope") != original.scope.fingerprint
            or not _usn_enabled(state, current)):
        raise ValueError("SCOPE_INVENTORY_CONFLICT")
    box = _outbox(state, current)
    if box.credential_binding() != current.credential_version:
        raise ValueError("SCOPE_CREDENTIAL_CHANGED")
    transition = box.checkpoint("windows:scope-transition").value
    if not isinstance(transition, dict) or any(transition.get(key) != value for key, value in {
        "id": identity, "phase": "COMMITTED", "old_scope": original.scope.fingerprint,
        "new_scope": current.scope.fingerprint,
    }.items()):
        raise ValueError("SCOPE_INVENTORY_CONFLICT")
    inventory = box.checkpoint("windows:inventory")
    if inventory.value is None:
        return False
    if (isinstance(inventory.value, dict)
            and inventory.value.get("scope") == current.scope.fingerprint):
        _state(box, "windows:inventory", current.scope)
        return False
    if (not isinstance(inventory.value, dict)
            or inventory.value.get("scope") != original.scope.fingerprint):
        raise ValueError("SCOPE_INVENTORY_CONFLICT")
    inventory = _state(box, "windows:inventory", original.scope)
    assert isinstance(inventory.value, dict)
    prior_inventory = inventory.value
    marker = "windows:scope-inventory-repair"
    previous = box.checkpoint(marker)
    box.advance_stream(marker, previous.revision, {
        "id": identity, "old_scope": original.scope.fingerprint,
        "new_scope": current.scope.fingerprint, "prior_inventory": prior_inventory,
    }, lambda _read: iter((("windows:inventory", inventory.revision, {
        **prior_inventory, "scope": current.scope.fingerprint, "completed": False,
    }),)))
    return True
