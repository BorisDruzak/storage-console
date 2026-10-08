from datetime import UTC, datetime
from uuid import uuid4

import pytest

from collectors.common.outbox import Outbox, OutboxError
from packages.contracts.common import BatchEnvelope
from packages.contracts.heartbeat import HeartbeatRecord


def batch(box):
    now = datetime.now(UTC)
    return BatchEnvelope[HeartbeatRecord](
        collector_id=box.collector_id, batch_id=str(uuid4()), schema_version=1,
        sent_at=now, first_event_at=now, last_event_at=now, record_count=1,
        records=[HeartbeatRecord(occurred_at=now, version="synthetic")],
    )


def test_batch_cursor_and_cache_are_atomic_and_restart_replays_exact_bytes(tmp_path):
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", uuid4())
    payload = batch(box)
    updates = {"usn:path:synthetic": (0, {"name": "Отчёт", "parent": "root"})}
    box.enqueue("heartbeat", payload, "usn:cursor", 0, {"cursor": 128},
                checkpoint_updates=updates)
    restored = Outbox(box.path, box.collector_id)
    assert restored.checkpoint("usn:cursor").value == {"cursor": 128}
    assert restored.checkpoint("usn:path:synthetic").value == updates["usn:path:synthetic"][1]
    claim = restored.claim(datetime.now(UTC))
    assert claim.body == payload.model_dump_json().encode()
    box.enqueue("heartbeat", payload, "usn:cursor", 0, {"cursor": 128},
                checkpoint_updates=updates)
    assert box.status().pending_count == 1
    with pytest.raises(OutboxError, match="^BATCH_CONFLICT$"):
        box.enqueue("heartbeat", payload, "usn:cursor", 0, {"cursor": 128},
                    checkpoint_updates={"usn:path:synthetic": (0, {"name": "changed"})})


def test_late_cache_conflict_rolls_back_batch_cursor_and_earlier_cache(tmp_path):
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", uuid4())
    box.advance("usn:path:last", 0, {"original": True})
    with pytest.raises(OutboxError, match="^CHECKPOINT_CONFLICT$"):
        box.enqueue("heartbeat", batch(box), "usn:cursor", 0, {"cursor": 128},
                    checkpoint_updates={"usn:path:first": (0, {"name": "first"}),
                                        "usn:path:last": (0, {"name": "last"})})
    assert box.status().pending_count == 0
    assert box.checkpoint("usn:cursor").revision == 0
    assert box.checkpoint("usn:path:first").revision == 0
    assert box.checkpoint("usn:path:last").value == {"original": True}


def test_empty_read_transition_advances_cursor_and_cache_without_empty_batch(tmp_path):
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", uuid4())
    box.advance("usn:cursor", 0, {"cursor": 64},
                checkpoint_updates={"usn:path:a": (0, {"parent": "root"})})
    assert box.status().pending_count == 0
    assert box.checkpoint("usn:cursor").value == {"cursor": 64}
    assert box.checkpoint("usn:path:a").revision == 1
    with pytest.raises(OutboxError, match="^CHECKPOINT_CONFLICT$"):
        box.advance("usn:cursor", 0, {"cursor": 128})


def test_invalid_group_is_rejected_without_partial_writes(tmp_path):
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", uuid4())
    for updates in [{"usn:cursor": (0, {})}, {"usn:path:a": (True, {})},
                    {"usn:path:a": (0, {"too_large": "a" * 17000})}]:
        with pytest.raises(OutboxError):
            box.advance("usn:cursor", 0, {"cursor": 128}, checkpoint_updates=updates)
        assert box.checkpoint("usn:cursor").revision == 0
        assert box.checkpoint("usn:path:a").revision == 0


def test_checkpoint_group_rejects_mixed_or_invalid_keys_with_fixed_code(tmp_path):
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", uuid4())
    for updates in [{1: (0, {})}, {"valid": (0, {}), 1: (0, {})},
                    {"invalid\0stream": (0, {})}]:
        with pytest.raises(OutboxError, match="^INVALID_CHECKPOINT$"):
            box.advance("usn:cursor", 0, {}, checkpoint_updates=updates)
        assert box.checkpoint("usn:cursor").revision == 0


def test_global_cache_bound_rolls_back_transition_and_preserves_heartbeat_reserve(tmp_path):
    from collectors.common.outbox import Limits

    box = Outbox(tmp_path / "private" / "queue", uuid4(),
                 Limits(max_cache_entries=2, max_cache_bytes=1024))
    box.advance("windows:usn:a", 0, {"cursor": 1},
                checkpoint_updates={"windows:usn:a:node:one": (0, {"name": "one"})})
    with pytest.raises(OutboxError, match="^CAPACITY$"):
        box.enqueue("heartbeat", batch(box), "windows:usn:a", 1, {"cursor": 2},
                    checkpoint_updates={"windows:usn:a:node:two": (0, {"name": "two"})})
    assert box.checkpoint("windows:usn:a").value == {"cursor": 1}
    assert box.checkpoint("windows:usn:a:node:two").revision == 0
    assert box.status().pending_count == 0
    box.enqueue("heartbeat", batch(box), "windows:heartbeat", 0, {"sequence": 1})
    assert box.status().pending_count == 1


def test_explicit_rebaseline_preserves_queued_bytes_credentials_and_other_streams(tmp_path):
    box = Outbox(tmp_path / "private" / "queue", uuid4())
    binding = uuid4()
    box.activate_credentials(binding)
    payload = batch(box)
    box.enqueue("heartbeat", payload, "windows:heartbeat", 0, {"sequence": 1})
    box.advance("windows:usn:synthetic", 0, {"status": "CONTINUITY_GAP"},
                checkpoint_updates={"windows:usn:synthetic:node:one": (0, {"name": "one"})})
    claim = box.claim(datetime.now(UTC))
    assert box.credential_binding() == binding
    box.reset_usn_checkpoints()
    assert box.checkpoint("windows:usn:synthetic").revision == 0
    assert box.checkpoint("windows:usn:synthetic:node:one").revision == 0
    assert box.checkpoint("windows:heartbeat").value == {"sequence": 1}
    assert box.credential_binding() == binding
    assert box.status().pending_count == 1
    assert claim.body == payload.model_dump_json().encode()
    assert box.retry(claim, "NETWORK", datetime.now(UTC))
    reopened = Outbox(box.path, box.collector_id)
    replay = reopened.claim(datetime.now(UTC))
    assert replay.body == claim.body and replay.batch_id == claim.batch_id
    assert reopened.credential_binding() == binding
