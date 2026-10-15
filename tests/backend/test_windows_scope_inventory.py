"""An explicit USN scope transition must not strand the inventory producer."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from collectors.common.outbox import Outbox, OutboxError
from collectors.windows.configuration import PrivateConfig
from collectors.windows.inventory import Scope
from collectors.windows.producer import _state
from collectors.windows.scope_extension import (
    ScopeNode,
    commit_scope,
    extend_scope,
    prepare_receipt,
    recover_scope,
)
from collectors.windows.usn_state import UsnState


def fixture(tmp_path):
    config = PrivateConfig(
        collector_id=uuid4(), credential_version=uuid4(),
        origin="https://synthetic.example.test", roots=(r"D:\Synthetic\Original",),
        encrypted_token="synthetic-encrypted-token",
    )
    proposed = config.model_copy(update={"roots": (*config.roots, r"D:\Synthetic\Additional")})
    state = SimpleNamespace(
        root=tmp_path, read=lambda name, bound: (tmp_path / name).read_bytes(),
        write=lambda name, data: (tmp_path / name).write_bytes(data),
        validate_file=lambda name: None,
    )
    state.write("config.json", config.model_dump_json().encode())
    state.write("usn-activation.json", json.dumps({
        "version": 1, "scope": config.scope.fingerprint, "enabled": True,
    }).encode())
    box = Outbox(tmp_path / "outbox.sqlite3", config.collector_id)
    box.activate_credentials(config.credential_version)
    usn = UsnState(box, "ntfs:synthetic", config.scope.fingerprint)
    usn.initialize(7, 100, {f"{1:032x}": {"root": "\\Original", "name": "Original"}})
    old_inventory = {
        "kind": "windows:inventory", "scope": config.scope.fingerprint,
        "scan_id": str(uuid4()), "sequence": 3, "completed": True,
    }
    box.advance("windows:inventory", 0, old_inventory)
    return state, config, proposed, box, usn, old_inventory


def commit(box, config, proposed, identifier):
    commit_scope(box, config.scope, proposed.scope, iter((
        ScopeNode("ntfs:synthetic", f"{3:032x}", None, "Additional", "\\Additional"),
    )), {"ntfs:synthetic": (7, 200)}, identifier)


def test_scope_commit_rebinds_inventory_atomically_without_claiming_completion(tmp_path):
    _, config, proposed, box, _, old_inventory = fixture(tmp_path)
    commit(box, config, proposed, uuid4().hex)
    inventory = _state(box, "windows:inventory", proposed.scope)
    assert inventory.value == {
        **old_inventory, "scope": proposed.scope.fingerprint, "completed": False,
    }
    assert UsnState(box, "ntfs:synthetic", proposed.scope.fingerprint).cursor == 100


def test_interrupted_scope_keeps_inventory_and_usn_on_original_scope(tmp_path):
    _, config, proposed, box, usn, _ = fixture(tmp_path)
    before = box.checkpoint("windows:inventory")

    def interrupted():
        yield ScopeNode("ntfs:synthetic", f"{3:032x}", None, "Additional", "\\Additional")
        raise OSError("synthetic-interruption")

    with pytest.raises((OSError, OutboxError)):
        commit_scope(box, config.scope, proposed.scope, interrupted(),
                     {"ntfs:synthetic": (7, 200)}, uuid4().hex)
    assert box.checkpoint("windows:inventory") == before
    assert usn.cursor == 100


def test_explicit_retry_repairs_legacy_completed_transition_without_changing_usn(tmp_path):
    state, config, proposed, box, _, old_inventory = fixture(tmp_path)
    identifier = uuid4().hex
    prepare_receipt(state, config, proposed, identifier)
    commit(box, config, proposed, identifier)
    recover_scope(state)
    # Simulate the inventory checkpoint left behind by the previous release.
    before = box.checkpoint("windows:inventory")
    box.advance("windows:inventory", before.revision, old_inventory)
    current = UsnState(box, "ntfs:synthetic", proposed.scope.fingerprint)
    usn_before = box.checkpoint(current.stream)
    binding = box.credential_binding()
    extend_scope(state, proposed.roots)
    inventory = _state(box, "windows:inventory", proposed.scope)
    assert inventory.value == {
        **old_inventory, "scope": proposed.scope.fingerprint, "completed": False,
    }
    assert box.checkpoint(current.stream) == usn_before
    assert box.credential_binding() == binding
    extend_scope(state, proposed.roots)
    assert box.checkpoint("windows:inventory") == inventory


def test_legacy_repair_refuses_unproven_inventory_scope(tmp_path):
    state, config, proposed, box, _, old_inventory = fixture(tmp_path)
    identifier = uuid4().hex
    prepare_receipt(state, config, proposed, identifier)
    commit(box, config, proposed, identifier)
    recover_scope(state)
    before = box.checkpoint("windows:inventory")
    foreign = {**old_inventory, "scope": Scope((r"D:\Synthetic\Foreign",)).fingerprint}
    box.advance("windows:inventory", before.revision, foreign)
    with pytest.raises(ValueError, match="SCOPE_INVENTORY_CONFLICT"):
        extend_scope(state, proposed.roots)
    assert box.checkpoint("windows:inventory").value == foreign
