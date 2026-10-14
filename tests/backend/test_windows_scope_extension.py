"""Scope transition state stays atomic without materializing large checkpoint groups."""

import json
import tracemalloc
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from collectors.common.outbox import Limits, Outbox, OutboxError
from packages.contracts.common import BatchEnvelope
from packages.contracts.heartbeat import HeartbeatRecord


def test_streamed_52000_node_transition_retains_queued_body_and_bounded_python_memory(tmp_path):
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", uuid4())
    now = datetime.now(UTC)
    batch = BatchEnvelope[HeartbeatRecord](
        collector_id=box.collector_id,
        batch_id=uuid4().hex,
        schema_version=1,
        sent_at=now,
        first_event_at=now,
        last_event_at=now,
        record_count=1,
        records=[HeartbeatRecord(occurred_at=now, version="synthetic")],
    )
    box.enqueue("heartbeat", batch, "windows:heartbeat", 0, {"sequence": 1})
    body = box.claim(now).body

    def changes():
        for number in range(52000):
            yield f"windows:usn:synthetic:node:{number:032x}", 0, {"name": "Отчёт", "parent": None}

    tracemalloc.start()
    try:
        box.advance_stream("windows:scope-transition", 0, {"phase": "COMMITTED"}, changes())
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 4 * 1024**2
    assert box.checkpoint("windows:usn:synthetic:node:0000000000000000000000000000cb1f").value == {
        "name": "Отчёт",
        "parent": None,
    }
    assert box.checkpoint("windows:scope-transition").value == {"phase": "COMMITTED"}
    assert box.claim(now + timedelta(seconds=61)).body == body


def test_stream_failure_rolls_back_earlier_nodes_and_transition_marker(tmp_path):
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", uuid4())

    def interrupted():
        yield "windows:usn:synthetic:node:first", 0, {"name": "first"}
        raise OSError("synthetic-interruption")

    with pytest.raises((OSError, OutboxError)):
        box.advance_stream("windows:scope-transition", 0, {"phase": "COMMITTED"}, interrupted())
    assert box.checkpoint("windows:scope-transition").revision == 0
    assert box.checkpoint("windows:usn:synthetic:node:first").revision == 0


def test_duplicate_checkpoint_key_cannot_override_staged_transition(tmp_path):
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", uuid4())
    changes = iter(
        (
            ("windows:usn:synthetic:node:first", 0, {"name": "first"}),
            ("windows:usn:synthetic:node:first", 1, {"name": "replacement"}),
        )
    )
    with pytest.raises(OutboxError, match="INVALID_CHECKPOINT"):
        box.advance_stream("windows:scope-transition", 0, {}, changes)
    assert box.checkpoint("windows:usn:synthetic:node:first").revision == 0


def test_streamed_capacity_failure_preserves_existing_cursor_and_history(tmp_path):
    box = Outbox(
        tmp_path / "state" / "outbox.sqlite3",
        uuid4(),
        Limits(max_cache_entries=2, max_cache_bytes=1024),
    )
    box.advance("windows:usn:synthetic", 0, {"cursor": 100, "scope": "old"})
    changes = iter(
        (
            ("windows:usn:synthetic:node:first", 0, {"name": "first"}),
            ("windows:usn:synthetic:node:second", 0, {"name": "second"}),
        )
    )
    with pytest.raises(OutboxError, match="CAPACITY"):
        box.advance_stream("windows:scope-transition", 0, {}, changes)
    assert box.checkpoint("windows:usn:synthetic").value == {"cursor": 100, "scope": "old"}
    assert box.checkpoint("windows:usn:synthetic:node:first").revision == 0


def test_streamed_update_count_limit_rolls_back_before_accepting_partial_scope(tmp_path):
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", uuid4())
    changes = ((f"windows:usn:synthetic:node:{n}", 0, {}) for n in range(3))
    with pytest.raises(OutboxError, match="CAPACITY"):
        box.advance_stream("windows:scope-transition", 0, {}, changes, max_updates=2)
    assert box.checkpoint("windows:scope-transition").revision == 0


def test_scope_extension_only_accepts_strict_disjoint_superset():
    from collectors.windows.inventory import Scope
    from collectors.windows.scope_extension import additional_roots

    old = Scope((r"D:\Synthetic\Original",))
    new = Scope((r"D:\Synthetic\Original", r"D:\Synthetic\Additional"))
    assert additional_roots(old, new) == (r"D:\Synthetic\Additional",)
    for candidate in (old, Scope((r"D:\Synthetic\Additional",))):
        with pytest.raises(ValueError, match="SCOPE_EXTENSION_INVALID"):
            additional_roots(old, candidate)


def test_scope_commit_keeps_old_cursor_and_excludes_new_root_history_before_fence(tmp_path):
    from collectors.windows.inventory import Scope
    from collectors.windows.scope_extension import ScopeNode, commit_scope
    from collectors.windows.usn import UsnRecord
    from collectors.windows.usn_state import UsnState

    old = Scope((r"D:\Synthetic\Original",))
    new = Scope((r"D:\Synthetic\Original", r"D:\Synthetic\Additional"))
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", uuid4())
    state = UsnState(box, "ntfs:synthetic", old.fingerprint)
    state.initialize(
        7,
        100,
        {
            f"{1:032x}": {"root": "\\Original", "name": "Original"},
            f"{2:032x}": {"parent": f"{1:032x}", "name": "old.txt"},
        },
    )
    nodes = iter(
        (
            ScopeNode("ntfs:synthetic", f"{3:032x}", None, "Additional", "\\Additional"),
            ScopeNode("ntfs:synthetic", f"{4:032x}", f"{3:032x}", "new.txt"),
        )
    )
    commit_scope(box, old, new, nodes, {"ntfs:synthetic": (7, 200)}, uuid4().hex)
    current = UsnState(box, "ntfs:synthetic", new.fingerprint)
    assert current.cursor == 100
    assert box.checkpoint(state._key(f"{2:032x}")).value["name"] == "old.txt"
    records = (
        UsnRecord(f"{4:032x}", f"{3:032x}", 150, datetime.now(UTC), 0x80000100, 0, "new.txt"),
        UsnRecord(f"{2:032x}", f"{1:032x}", 170, datetime.now(UTC), 0x80000200, 0, "old.txt"),
    )
    events = current.consume(7, 201, records)
    assert [(item.event_type, item.old_relative_path) for item in events] == [
        ("DELETE", "\\Original\\old.txt")
    ]
    assert current.cursor == 201


def test_scope_commit_cannot_overwrite_old_ancestry_on_file_id_collision(tmp_path):
    from collectors.windows.inventory import Scope
    from collectors.windows.scope_extension import ScopeNode, commit_scope
    from collectors.windows.usn_state import UsnState

    old = Scope((r"D:\Synthetic\Original",))
    new = Scope((r"D:\Synthetic\Original", r"D:\Synthetic\Additional"))
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", uuid4())
    state = UsnState(box, "ntfs:synthetic", old.fingerprint)
    state.initialize(7, 100, {f"{1:032x}": {"root": "\\Original", "name": "Original"}})
    original = box.checkpoint(state.stream)
    with pytest.raises(ValueError, match="SCOPE_IDENTITY_CONFLICT"):
        commit_scope(
            box,
            old,
            new,
            iter((ScopeNode("ntfs:synthetic", f"{1:032x}", None, "Additional", "\\Additional"),)),
            {"ntfs:synthetic": (7, 200)},
            uuid4().hex,
        )
    assert box.checkpoint(state.stream) == original


def test_scope_commit_preserves_preexisting_continuity_gap(tmp_path):
    from collectors.windows.inventory import Scope
    from collectors.windows.scope_extension import ScopeNode, commit_scope
    from collectors.windows.usn_state import UsnState

    old = Scope((r"D:\Synthetic\Original",))
    new = Scope((r"D:\Synthetic\Original", r"D:\Synthetic\Additional"))
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", uuid4())
    state = UsnState(box, "ntfs:synthetic", old.fingerprint)
    state.initialize(7, 100, {f"{1:032x}": {"root": "\\Original", "name": "Original"}})
    state.fail("CONTINUITY_GAP")
    commit_scope(
        box,
        old,
        new,
        iter((ScopeNode("ntfs:synthetic", f"{3:032x}", None, "Additional", "\\Additional"),)),
        {"ntfs:synthetic": (7, 200)},
        uuid4().hex,
    )
    current = UsnState(box, "ntfs:synthetic", new.fingerprint)
    assert current.cursor == 100
    assert current.status == "CONTINUITY_GAP"


def test_scope_commit_interruption_cannot_leave_mixed_old_and_new_state(tmp_path):
    from collectors.windows.inventory import Scope
    from collectors.windows.scope_extension import ScopeNode, commit_scope
    from collectors.windows.usn_state import UsnState

    old = Scope((r"D:\Synthetic\Original",))
    new = Scope((r"D:\Synthetic\Original", r"D:\Synthetic\Additional"))
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", uuid4())
    state = UsnState(box, "ntfs:synthetic", old.fingerprint)
    state.initialize(7, 100, {f"{1:032x}": {"root": "\\Original", "name": "Original"}})
    original = box.checkpoint(state.stream)

    def interrupted():
        yield ScopeNode("ntfs:synthetic", f"{3:032x}", None, "Additional", "\\Additional")
        raise OSError("synthetic-interruption")

    with pytest.raises((ValueError, OutboxError, OSError)):
        commit_scope(box, old, new, interrupted(), {"ntfs:synthetic": (7, 200)}, uuid4().hex)
    assert box.checkpoint(state.stream) == original
    assert box.checkpoint(state._key(f"{3:032x}")).revision == 0
    assert box.checkpoint("windows:scope-transition").revision == 0


def test_committed_scope_recovers_config_activation_without_changing_credentials(tmp_path):
    from collectors.windows.configuration import PrivateConfig
    from collectors.windows.scope_extension import prepare_receipt, recover_scope

    original = PrivateConfig(
        collector_id=uuid4(),
        credential_version=uuid4(),
        origin="https://synthetic.example.test",
        roots=(r"D:\Synthetic\Original",),
        encrypted_token="synthetic-encrypted-token",
    )
    proposed = original.model_copy(
        update={
            "roots": (r"D:\Synthetic\Original", r"D:\Synthetic\Additional"),
        }
    )
    state = SimpleNamespace(
        root=tmp_path,
        read=lambda name, _bound: (tmp_path / name).read_bytes(),
        write=lambda name, data: (tmp_path / name).write_bytes(data),
    )
    state.write("config.json", original.model_dump_json().encode())
    state.write(
        "usn-activation.json",
        json.dumps(
            {
                "version": 1,
                "scope": original.scope.fingerprint,
                "enabled": True,
            }
        ).encode(),
    )
    box = Outbox(tmp_path / "outbox.sqlite3", original.collector_id)
    box.activate_credentials(original.credential_version)
    identifier = uuid4().hex
    prepare_receipt(state, original, proposed, identifier)
    box.advance(
        "windows:scope-transition",
        0,
        {
            "id": identifier,
            "phase": "COMMITTED",
            "old_scope": original.scope.fingerprint,
            "new_scope": proposed.scope.fingerprint,
        },
    )
    assert recover_scope(state)
    current = PrivateConfig.model_validate_json(state.read("config.json", 131072))
    assert current.roots == proposed.roots
    assert current.collector_id == original.collector_id
    assert current.credential_version == original.credential_version
    assert current.encrypted_token == original.encrypted_token
    assert (
        json.loads(state.read("usn-activation.json", 4096))["scope"] == proposed.scope.fingerprint
    )
    assert not recover_scope(state)


def test_uncommitted_scope_receipt_refuses_runtime_instead_of_false_old_continuity(tmp_path):
    from collectors.windows.configuration import PrivateConfig
    from collectors.windows.scope_extension import prepare_receipt, recover_scope

    original = PrivateConfig(
        collector_id=uuid4(),
        credential_version=uuid4(),
        origin="https://synthetic.example.test",
        roots=(r"D:\Synthetic\Original",),
        encrypted_token="synthetic-encrypted-token",
    )
    proposed = original.model_copy(
        update={
            "roots": (r"D:\Synthetic\Original", r"D:\Synthetic\Additional"),
        }
    )
    state = SimpleNamespace(
        root=tmp_path,
        read=lambda name, _bound: (tmp_path / name).read_bytes(),
        write=lambda name, data: (tmp_path / name).write_bytes(data),
    )
    state.write("config.json", original.model_dump_json().encode())
    state.write(
        "usn-activation.json",
        json.dumps(
            {
                "version": 1,
                "scope": original.scope.fingerprint,
                "enabled": True,
            }
        ).encode(),
    )
    box = Outbox(tmp_path / "outbox.sqlite3", original.collector_id)
    box.activate_credentials(original.credential_version)
    prepare_receipt(state, original, proposed, uuid4().hex)
    with pytest.raises(ValueError, match="SCOPE_EXTENSION_PENDING"):
        recover_scope(state)
    assert (
        PrivateConfig.model_validate_json(state.read("config.json", 131072)).roots == original.roots
    )


def test_configuration_load_recovers_scope_before_loading_usn_activation(monkeypatch, tmp_path):
    from collectors.windows import configuration, scope_extension

    recovered = []
    monkeypatch.setattr(
        scope_extension, "recover_scope", lambda state: recovered.append(state) or False
    )

    def read_after_recovery(state):
        assert recovered == [state]
        raise RuntimeError("synthetic-stop-after-recovery")

    monkeypatch.setattr(configuration, "_read", read_after_recovery)
    state = SimpleNamespace(root=tmp_path)
    with pytest.raises(RuntimeError, match="synthetic-stop-after-recovery"):
        configuration.load(state)


def test_operator_extension_preserves_old_credentials_queue_and_ancestry(monkeypatch, tmp_path):
    from collectors.windows import scope_extension
    from collectors.windows.configuration import PrivateConfig
    from collectors.windows.usn_state import UsnState

    original = PrivateConfig(
        collector_id=uuid4(),
        credential_version=uuid4(),
        origin="https://synthetic.example.test",
        roots=(r"D:\Synthetic\Original",),
        encrypted_token="synthetic-encrypted-token",
    )
    state = SimpleNamespace(
        root=tmp_path,
        read=lambda name, _bound: (tmp_path / name).read_bytes(),
        write=lambda name, data: (tmp_path / name).write_bytes(data),
        validate_file=lambda _: None,
        create_file=lambda name: (tmp_path / name).touch(),
    )
    state.write("config.json", original.model_dump_json().encode())
    state.write(
        "usn-activation.json",
        json.dumps(
            {
                "version": 1,
                "scope": original.scope.fingerprint,
                "enabled": True,
            }
        ).encode(),
    )
    box = Outbox(tmp_path / "outbox.sqlite3", original.collector_id)
    box.activate_credentials(original.credential_version)
    old_state = UsnState(box, "ntfs:synthetic", original.scope.fingerprint)
    old_state.initialize(7, 100, {f"{1:032x}": {"root": "\\Original", "name": "Original"}})

    def prepared(stage, roots, proposed, **_kwargs):
        assert roots == (r"D:\Synthetic\Additional",)
        stage.write_nodes(
            iter(
                (
                    scope_extension.ScopeNode(
                        "ntfs:synthetic",
                        f"{3:032x}",
                        None,
                        "Additional",
                        "\\Additional",
                    ),
                )
            )
        )
        return {"ntfs:synthetic": (7, 200)}

    monkeypatch.setattr(scope_extension, "prepare_native_stage", prepared)
    monkeypatch.setattr(scope_extension, "validate_fences", lambda *args: None)
    new_roots = (r"D:\Synthetic\Original", r"D:\Synthetic\Additional")
    scope_extension.extend_scope(state, new_roots)
    current = PrivateConfig.model_validate_json(state.read("config.json", 131072))
    assert current.roots == new_roots
    assert current.encrypted_token == original.encrypted_token
    assert current.credential_version == original.credential_version
    assert UsnState(box, "ntfs:synthetic", current.scope.fingerprint).cursor == 100
    assert box.checkpoint(old_state._key(f"{1:032x}")).value["name"] == "Original"


def test_operator_cli_has_explicit_scope_extension_without_reusing_activate():
    from collectors.windows.cli import _parser

    args = _parser().parse_args(
        [
            "scope-extend",
            "--state",
            r"C:\SyntheticState",
            "--root",
            r"D:\Synthetic\Additional",
        ]
    )
    assert args.command == "scope-extend"
    assert args.root == r"D:\Synthetic\Additional"


def test_disk_staging_is_paged_bounded_and_rejects_ambiguous_file_ids(tmp_path):
    from collectors.windows.scope_extension import ScopeNode
    from collectors.windows.scope_stage import ScopeStage

    stage = ScopeStage(tmp_path / "stage.sqlite3", "synthetic-transition")
    stage.write_nodes(
        ScopeNode("ntfs:synthetic", f"{number:032x}", None, "Отчёт") for number in range(52000)
    )
    assert stage.count() == 52000
    assert stage.contains("ntfs:synthetic", f"{51999:032x}")
    assert sum(1 for _ in stage.nodes()) == 52000
    with pytest.raises(ValueError, match="SCOPE_IDENTITY_CONFLICT"):
        stage.write_nodes(iter((ScopeNode("ntfs:synthetic", f"{1:032x}", None, "duplicate"),)))
    assert stage.count() == 52000


def test_staging_bound_or_cancel_never_publishes_partial_native_baseline(tmp_path):
    from collectors.windows.scope_extension import ScopeNode
    from collectors.windows.scope_stage import ScopeStage

    stage = ScopeStage(tmp_path / "stage.sqlite3", "synthetic-transition", max_nodes=2)
    rows = (ScopeNode("ntfs:synthetic", f"{number:032x}", None, "file") for number in range(3))
    with pytest.raises(ValueError, match="SCOPE_CAPACITY"):
        stage.write_nodes(rows)
    assert stage.count() == 0
    with pytest.raises(ValueError, match="SCOPE_STOPPED"):
        stage.write_nodes(
            iter((ScopeNode("ntfs:synthetic", f"{1:032x}", None, "file"),)),
            stopped=lambda: True,
        )
    assert stage.count() == 0


@pytest.mark.parametrize("changed", [False, True, "future"])
def test_native_stage_uses_read_only_fence_and_rejects_in_scope_changes(
    tmp_path, monkeypatch, changed
):
    from collectors.windows import native, usn_native
    from collectors.windows.inventory import Scope
    from collectors.windows.scope_extension import prepare_native_stage
    from collectors.windows.scope_stage import ScopeStage
    from collectors.windows.usn import UsnRecord
    from collectors.windows.usn_native import JournalInfo
    from packages.contracts.inventory import FileObjectRecord

    queries = 0
    closed = 0

    class Stream:
        def query(self):
            nonlocal queries
            queries += 1
            return JournalInfo(7, 0, 201 if changed and queries > 1 else 200, 0, 1048576, 65536)

        def read(self, journal, cursor):
            assert (journal, cursor) == (7, 200)
            return (202 if changed == "future" else 201), (
                UsnRecord(
                    f"{4:032x}",
                    f"{3:032x}",
                    201 if changed == "future" else 200,
                    datetime.now(UTC),
                    1,
                    0,
                    "file.txt",
                ),
            )

        def close(self):
            nonlocal closed
            closed += 1

    class Journal:
        volumes = ("ntfs:synthetic",)
        _api = None

        def __init__(self, _scope):
            pass

        def open(self, volume):
            assert volume == "ntfs:synthetic"
            return Stream()

    class Inventory:
        def _root(self, _api, root):
            assert root == r"D:\Synthetic\Additional"
            for identifier, parent, name, kind in (
                (3, None, "Additional", "DIRECTORY"),
                (4, 3, "file.txt", "FILE"),
            ):
                record = FileObjectRecord(
                    occurred_at=datetime.now(UTC),
                    volume_identity="ntfs:synthetic",
                    file_id=f"{identifier:032x}",
                    parent_file_id=f"{parent:032x}" if parent else None,
                    object_type=kind,
                    name=name,
                    relative_path="\\Additional",
                    link_count=1 if kind == "FILE" else None,
                )
                yield SimpleNamespace(record=record, error_code=None)

    monkeypatch.setattr(usn_native, "NativeJournal", Journal)
    monkeypatch.setattr(native, "NativeInventory", Inventory)
    stage = ScopeStage(tmp_path / "stage.sqlite3", "synthetic-transition")
    proposed = Scope((r"D:\Synthetic\Original", r"D:\Synthetic\Additional"))
    if changed is True:
        with pytest.raises(ValueError, match="SCOPE_CHANGED"):
            prepare_native_stage(stage, (r"D:\Synthetic\Additional",), proposed)
    else:
        assert prepare_native_stage(stage, (r"D:\Synthetic\Additional",), proposed) == {
            "ntfs:synthetic": (7, 201 if changed == "future" else 200)
        }
    assert closed == 2


def _protected_config_fixture(tmp_path):
    from collectors.windows.configuration import PrivateConfig

    original = PrivateConfig(
        collector_id=uuid4(),
        credential_version=uuid4(),
        origin="https://synthetic.example.test",
        roots=(r"D:\Synthetic\Original",),
        encrypted_token="synthetic-encrypted-token",
    )
    state = SimpleNamespace(
        root=tmp_path,
        read=lambda name, _bound: (tmp_path / name).read_bytes(),
        write=lambda name, data: (tmp_path / name).write_bytes(data),
        validate_file=lambda _: None,
        create_file=lambda name: (tmp_path / name).touch(),
    )
    state.write("config.json", original.model_dump_json().encode())
    state.write(
        "usn-activation.json",
        json.dumps({"version": 1, "scope": original.scope.fingerprint, "enabled": True}).encode(),
    )
    box = Outbox(tmp_path / "outbox.sqlite3", original.collector_id)
    box.activate_credentials(original.credential_version)
    return state, original, box


def test_preparing_next_transition_preserves_completed_receipt_at_every_write(tmp_path):
    from collectors.windows.scope_extension import RECEIPT_NAME, prepare_receipt, recover_scope

    state, original, box = _protected_config_fixture(tmp_path)
    first = original.model_copy(update={"roots": (*original.roots, r"D:\Synthetic\Second")})
    identifier = uuid4().hex
    prepare_receipt(state, original, first, identifier)
    box.advance(
        "windows:scope-transition",
        0,
        {
            "id": identifier,
            "phase": "COMMITTED",
            "old_scope": original.scope.fingerprint,
            "new_scope": first.scope.fingerprint,
        },
    )
    recover_scope(state)
    first_receipt = state.read(RECEIPT_NAME, 1048576)
    second = first.model_copy(update={"roots": (*first.roots, r"D:\Synthetic\Third")})
    write = state.write

    def interrupted(name, data):
        if name == RECEIPT_NAME:
            raise OSError("synthetic-before-receipt-replacement")
        write(name, data)

    state.write = interrupted
    with pytest.raises(OSError):
        prepare_receipt(state, first, second, uuid4().hex)
    state.write = write
    assert not recover_scope(state)
    assert state.read(RECEIPT_NAME, 1048576) == first_receipt
    assert state.read("scope-extension-receipt-" + identifier + ".json", 1048576) == first_receipt


def test_final_fence_check_rejects_rollover_before_scope_commit(tmp_path, monkeypatch):
    from collectors.windows import scope_extension, usn_native
    from collectors.windows.inventory import Scope
    from collectors.windows.usn import UsnError
    from collectors.windows.usn_native import JournalInfo
    from collectors.windows.usn_state import UsnState

    state, original, box = _protected_config_fixture(tmp_path)
    UsnState(box, "ntfs:synthetic", original.scope.fingerprint).initialize(
        7, 100, {f"{1:032x}": {"name": "Original", "root": "\\Original"}}
    )
    closed = []

    class Stream:
        def query(self):
            return JournalInfo(7, 201, 300, 201, 1048576, 65536)

        def close(self):
            closed.append(True)

    class Journal:
        volumes = ("ntfs:synthetic",)

        def __init__(self, scope):
            pass

        def open(self, volume):
            return Stream()

    monkeypatch.setattr(usn_native, "NativeJournal", Journal)
    proposed = Scope((*original.roots, r"D:\Synthetic\Additional"))
    with pytest.raises(UsnError, match="CONTINUITY_GAP"):
        scope_extension.validate_fences(box, original.scope, proposed, {"ntfs:synthetic": (7, 200)})
    assert closed == [True]
    assert box.checkpoint("windows:scope-transition").revision == 0


def test_scope_cli_retry_does_not_duplicate_root_after_committed_recovery(tmp_path, monkeypatch):
    import threading

    from collectors.windows import cli, scope_extension
    from collectors.windows.configuration import PrivateConfig

    state, original, box = _protected_config_fixture(tmp_path)
    proposed = original.model_copy(update={"roots": (*original.roots, r"D:\Synthetic\Additional")})
    identifier = uuid4().hex
    scope_extension.prepare_receipt(state, original, proposed, identifier)
    box.advance(
        "windows:scope-transition",
        0,
        {
            "id": identifier,
            "phase": "COMMITTED",
            "old_scope": original.scope.fingerprint,
            "new_scope": proposed.scope.fingerprint,
        },
    )
    # Crash after config replacement but before activation replacement.
    state.write("config.json", proposed.model_dump_json().encode())
    from contextlib import nullcontext

    monkeypatch.setattr(cli, "_windows", lambda: True)
    monkeypatch.setattr(cli, "ProtectedState", lambda *args, **kwargs: nullcontext(state))
    monkeypatch.setattr(cli, "_validate_root", lambda scope: None)
    args = cli._parser().parse_args(
        ["scope-extend", "--state", r"C:\SyntheticState", "--root", r"D:\Synthetic\Additional"]
    )
    assert cli._execute(args, threading.Event()) == 0
    assert (
        PrivateConfig.model_validate_json(state.read("config.json", 131072)).roots == proposed.roots
    )
    assert (
        json.loads(state.read("usn-activation.json", 4096))["scope"] == proposed.scope.fingerprint
    )


def test_actual_52000_scope_commit_does_not_lock_its_own_reader(tmp_path):
    from collectors.windows.inventory import Scope
    from collectors.windows.scope_extension import ScopeNode, commit_scope
    from collectors.windows.usn_state import UsnState

    old = Scope((r"D:\Synthetic\Original",))
    new = Scope((*old.roots, r"D:\Synthetic\Additional"))
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", uuid4())
    UsnState(box, "ntfs:synthetic", old.fingerprint).initialize(
        7, 100, {f"{1:032x}": {"name": "Original", "root": "\\Original"}}
    )

    def nodes():
        yield ScopeNode("ntfs:synthetic", f"{2:032x}", None, "Additional", "\\Additional")
        for number in range(3, 52002):
            yield ScopeNode("ntfs:synthetic", f"{number:032x}", f"{2:032x}", "Отчёт")

    tracemalloc.start()
    try:
        commit_scope(box, old, new, nodes(), {"ntfs:synthetic": (7, 200)}, uuid4().hex)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 4 * 1024**2
    assert UsnState(box, "ntfs:synthetic", new.fingerprint).cursor == 100
    assert box.checkpoint("windows:scope-transition").value["phase"] == "COMMITTED"


def test_completed_receipt_does_not_block_subsequent_credential_rotation_or_disable(tmp_path):
    from collectors.windows.scope_extension import prepare_receipt, recover_scope

    state, original, box = _protected_config_fixture(tmp_path)
    proposed = original.model_copy(update={"roots": (*original.roots, r"D:\Synthetic\Additional")})
    identifier = uuid4().hex
    prepare_receipt(state, original, proposed, identifier)
    box.advance(
        "windows:scope-transition",
        0,
        {
            "id": identifier,
            "phase": "COMMITTED",
            "old_scope": original.scope.fingerprint,
            "new_scope": proposed.scope.fingerprint,
        },
    )
    recover_scope(state)
    rotated = proposed.model_copy(update={"credential_version": uuid4()})
    box.activate_credentials(rotated.credential_version)
    state.write("config.json", rotated.model_dump_json().encode())
    state.write(
        "usn-activation.json",
        json.dumps({"version": 1, "scope": rotated.scope.fingerprint, "enabled": False}).encode(),
    )
    assert not recover_scope(state)
    assert box.credential_binding() == rotated.credential_version


def test_missing_original_baseline_is_refused_without_fabricating_healthy_cursor(tmp_path):
    from collectors.windows.inventory import Scope
    from collectors.windows.scope_extension import ScopeNode, commit_scope

    old = Scope((r"D:\Synthetic\Original",))
    new = Scope((*old.roots, r"D:\Synthetic\Additional"))
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", uuid4())
    with pytest.raises(ValueError, match="SCOPE_EXTENSION_INCOMPLETE"):
        commit_scope(
            box,
            old,
            new,
            iter((ScopeNode("ntfs:synthetic", f"{3:032x}", None, "Additional", "\\Additional"),)),
            {"ntfs:synthetic": (7, 200)},
            uuid4().hex,
        )
    assert box.checkpoint("windows:scope-transition").revision == 0


def test_native_fence_checks_old_backlog_for_file_moved_into_new_scope(tmp_path, monkeypatch):
    from collectors.windows import native, usn_native
    from collectors.windows.inventory import Scope
    from collectors.windows.scope_extension import prepare_native_stage
    from collectors.windows.scope_stage import ScopeStage
    from collectors.windows.usn import UsnRecord
    from collectors.windows.usn_native import JournalInfo
    from packages.contracts.inventory import FileObjectRecord

    class Stream:
        def query(self):
            return JournalInfo(7, 0, 200, 0, 1048576, 65536)

        def read(self, journal, cursor):
            assert cursor == 100
            return 200, (
                UsnRecord(
                    f"{4:032x}", f"{1:032x}", 120, datetime.now(UTC), 0x80000100, 0, "moved.txt"
                ),
            )

        def close(self):
            pass

    class Journal:
        volumes = ("ntfs:synthetic",)
        _api = None

        def __init__(self, scope):
            pass

        def open(self, volume):
            return Stream()

    class Inventory:
        def _root(self, api, root):
            for fid, parent, name, kind in (
                (3, None, "Additional", "DIRECTORY"),
                (4, 3, "moved.txt", "FILE"),
            ):
                yield SimpleNamespace(
                    error_code=None,
                    record=FileObjectRecord(
                        occurred_at=datetime.now(UTC),
                        volume_identity="ntfs:synthetic",
                        file_id=f"{fid:032x}",
                        parent_file_id=f"{parent:032x}" if parent else None,
                        object_type=kind,
                        name=name,
                        relative_path="\\Additional",
                        link_count=1 if parent else None,
                    ),
                )

    monkeypatch.setattr(usn_native, "NativeJournal", Journal)
    monkeypatch.setattr(native, "NativeInventory", Inventory)
    proposed = Scope((r"D:\Synthetic\Original", r"D:\Synthetic\Additional"))
    stage = ScopeStage(tmp_path / "stage.sqlite3", "synthetic-transition")
    with pytest.raises(ValueError, match="SCOPE_CHANGED"):
        prepare_native_stage(
            stage,
            (r"D:\Synthetic\Additional",),
            proposed,
            prior_cursors={"ntfs:synthetic": (7, 100)},
        )


def test_streamed_transition_closes_producer_after_capacity_rollback(tmp_path):
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", uuid4())
    closed = []

    def changes():
        try:
            for number in range(3):
                yield f"windows:usn:synthetic:node:{number}", 0, {}
        finally:
            closed.append(True)

    retained_generator = changes()
    with pytest.raises(OutboxError, match="CAPACITY"):
        box.advance_stream("windows:scope-transition", 0, {}, retained_generator, max_updates=1)
    assert closed == [True]
    assert box.checkpoint("windows:scope-transition").revision == 0


def test_failed_enumeration_does_not_accumulate_unpublished_stage_files(tmp_path, monkeypatch):
    from collectors.windows import scope_extension
    from collectors.windows.usn_state import UsnState

    state, original, box = _protected_config_fixture(tmp_path)
    UsnState(box, "ntfs:synthetic", original.scope.fingerprint).initialize(
        7, 100, {f"{1:032x}": {"name": "Original", "root": "\\Original"}}
    )

    def failed(*args, **kwargs):
        raise ValueError("SCOPE_CHANGED")

    monkeypatch.setattr(scope_extension, "prepare_native_stage", failed)
    for _ in range(3):
        with pytest.raises(ValueError, match="SCOPE_CHANGED"):
            scope_extension.extend_scope(state, (*original.roots, r"D:\Synthetic\Additional"))
    assert not list(tmp_path.glob("scope-stage-*"))
    assert not (tmp_path / scope_extension.RECEIPT_NAME).exists()
    assert box.checkpoint("windows:scope-transition").revision == 0
