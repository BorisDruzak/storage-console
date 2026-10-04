import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from test_collector_outbox import heartbeat, legacy_state

from collectors.common.outbox import Outbox, OutboxError


@pytest.mark.parametrize("version", [1, 2])
def test_migration_preserves_every_retained_transition_and_binding_starts_unset(tmp_path, version):
    path, collector, batch = legacy_state(tmp_path)
    with sqlite3.connect(path) as db:
        if version == 2:
            db.execute("ALTER TABLE meta ADD COLUMN auth_suspended INTEGER NOT NULL DEFAULT 1")
            db.execute(
                "ALTER TABLE meta ADD COLUMN credential_generation INTEGER NOT NULL DEFAULT 7"
            )
            db.execute("PRAGMA user_version=2")
        before = {
            name: db.execute(f"SELECT * FROM {name}").fetchall()
            for name in ("batches", "checkpoints", "receipts")
        }
    box = Outbox(path, collector)
    assert box.credential_binding() is None
    assert box.credential_generation() == (7 if version == 2 else 0)
    assert box.auth_suspended() == (version == 2)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3
        assert {name: db.execute(f"SELECT * FROM {name}").fetchall() for name in before} == before
    box.enqueue("heartbeat", batch, "stream", 0, {"cursor": 1})
    assert box.status().pending_count == 1


def test_activation_is_atomic_revokes_all_old_leases_and_retains_bodies(tmp_path):
    collector = uuid4()
    box = Outbox(tmp_path / "private" / "queue", collector)
    now = datetime.now(UTC)
    for stream in ("first", "second"):
        box.enqueue("heartbeat", heartbeat(collector), stream, 0, {})
    first, second = box.claim(now), box.claim(now)
    assert first is not None and second is not None
    assert box.suspend_auth(first)
    binding = uuid4()
    assert box.activate_credentials(binding) == 1
    assert box.credential_binding() == binding and not box.auth_suspended()
    assert not box.acknowledge(second)
    assert not box.suspend_auth(second)
    new = box.claim(now)
    assert new is not None and new.credential_generation == 1
    assert new.body == first.body and new.lease_id != first.lease_id
    assert box.status().pending_count == 2


def test_same_activation_is_idempotent_and_never_resumes_persisted_suspension(tmp_path):
    box = Outbox(tmp_path / "private" / "queue", uuid4())
    binding = uuid4()
    assert box.activate_credentials(binding) == 1
    box.enqueue("heartbeat", heartbeat(box.collector_id), "stream", 0, {})
    claim = box.claim(datetime.now(UTC))
    assert claim is not None and box.suspend_auth(claim)
    restored = Outbox(box.path, box.collector_id)
    assert restored.credential_binding() == binding
    assert restored.activate_credentials(binding) == 1
    assert restored.auth_suspended()
    with pytest.raises(OutboxError, match="^CREDENTIAL_BOUND$"):
        restored.resume_auth()
    assert restored.auth_suspended()
    assert restored.activate_credentials(uuid4()) == 2
    assert not restored.auth_suspended()


def test_activation_rollback_preserves_suspension_binding_generation_and_leases(tmp_path):
    box = Outbox(tmp_path / "private" / "queue", uuid4())
    binding = uuid4()
    box.activate_credentials(binding)
    box.enqueue("heartbeat", heartbeat(box.collector_id), "stream", 0, {})
    claim = box.claim(datetime.now(UTC))
    assert claim is not None
    with sqlite3.connect(box.path) as db:
        db.execute(
            "CREATE TRIGGER reject_activation BEFORE UPDATE ON batches "
            "BEGIN SELECT RAISE(ABORT,'synthetic'); END"
        )
    with pytest.raises(OutboxError, match="^STATE_UNAVAILABLE$"):
        box.activate_credentials(uuid4())
    assert box.credential_binding() == binding
    assert box.credential_generation() == 1
    assert box.acknowledge(claim)


@pytest.mark.parametrize("value", [None, "not-a-uuid", 1, True])
def test_binding_requires_uuid_and_invalid_input_never_changes_state(tmp_path, value):
    box = Outbox(tmp_path / "private" / "queue", uuid4())
    with pytest.raises(OutboxError, match="^INVALID_CREDENTIALS$"):
        box.activate_credentials(value)
    assert box.credential_binding() is None and box.credential_generation() == 0
