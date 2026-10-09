import json
import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from collectors.common.outbox import Limits, Outbox, OutboxError
from collectors.windows.inventory import CaptureError, Observation, Scope
from collectors.windows.producer import capture_heartbeat, capture_inventory
from packages.contracts.inventory import FileObjectRecord, VolumeRecord

NOW = datetime(2026, 1, 1, tzinfo=UTC)
SCOPE = Scope(("C:\\synthetic",))


def observations(count=5):
    yield Observation(
        record=VolumeRecord(occurred_at=NOW, unique_identity="synthetic-volume", filesystem="NTFS")
    )
    for index in range(count):
        yield Observation(
            record=FileObjectRecord(
                occurred_at=NOW,
                volume_identity="synthetic-volume",
                file_id=str(index),
                object_type="FILE",
                name=f"file{index}",
                relative_path=f"synthetic\\file{index}",
                size_bytes=index,
            )
        )


def box(tmp_path, **limits):
    return Outbox(tmp_path / "private" / "state.db", uuid4(), Limits(**limits))


def drain(box):
    batches = []
    while claim := box.claim(NOW):
        batches.append(json.loads(claim.body))
        assert box.acknowledge(claim)
    return batches


def test_chunks_contract_checkpoint_and_unchanged_retained_restart(tmp_path):
    outbox = box(tmp_path)
    result = capture_inventory(outbox, SCOPE, observations(), max_records=2, clock=lambda: NOW)
    assert (result.records, result.batches, result.completed, result.errors) == (6, 3, True, ())
    checkpoint = outbox.checkpoint("windows:inventory")
    assert checkpoint.revision == 3 and checkpoint.value["completed"] is True
    assert checkpoint.value["scope"] == SCOPE.fingerprint
    first = outbox.claim(NOW)
    reopened = Outbox(outbox.path, outbox.collector_id)
    later = NOW + timedelta(seconds=61)
    replay = reopened.claim(later)
    assert replay.body == first.body and replay.batch_id == first.batch_id
    assert reopened.acknowledge(replay)
    remaining = drain(reopened)
    assert len(remaining) == 2
    for batch in [json.loads(first.body), *remaining]:
        assert batch["schema_version"] == 1 and batch["record_count"] == len(batch["records"]) == 2
        assert batch["collector_id"] == str(outbox.collector_id)


def test_restart_new_scan_id_preserves_old_fifo_and_scope(tmp_path):
    outbox = box(tmp_path)
    capture_inventory(outbox, SCOPE, observations(1), clock=lambda: NOW)
    old = outbox.checkpoint("windows:inventory").value["scan_id"]
    reopened = Outbox(outbox.path, outbox.collector_id)
    capture_inventory(reopened, SCOPE, observations(1), clock=lambda: NOW)
    new = reopened.checkpoint("windows:inventory").value["scan_id"]
    assert old != new
    batches = drain(reopened)
    assert len(batches) == 2 and batches[0]["batch_id"] != batches[1]["batch_id"]
    assert batches[0]["records"] == batches[1]["records"]


def test_scope_mismatch_before_provider_iteration(tmp_path):
    outbox = box(tmp_path)
    capture_inventory(outbox, SCOPE, observations(), clock=lambda: NOW)
    called = []

    def forbidden():
        called.append(True)
        yield from observations()

    with pytest.raises(CaptureError, match="^STATE_MISMATCH$"):
        capture_inventory(outbox, Scope(("D:\\other",)), forbidden(), clock=lambda: NOW)
    assert called == []


def test_pressure_keeps_committed_checkpoint_and_closes_provider(tmp_path):
    outbox = box(tmp_path, max_retained_batches=1)
    closed = []

    def provider():
        try:
            yield from observations(10)
        finally:
            closed.append(True)

    result = capture_inventory(outbox, SCOPE, provider(), max_records=2, clock=lambda: NOW)
    assert (result.records, result.batches, result.completed) == (2, 1, False)
    assert result.errors == ("CAPACITY",) and closed == [True]
    assert outbox.status().pending_count == 1
    assert outbox.checkpoint("windows:inventory").revision == 1
    assert outbox.checkpoint("windows:inventory").value["completed"] is False


@pytest.mark.parametrize("code", [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED])
def test_inventory_retries_only_temporary_lock_without_advancing_batch(tmp_path, monkeypatch, code):
    outbox = box(tmp_path)
    enqueue = outbox.enqueue
    attempts = []

    def blocked(*args):
        attempts.append(args)
        if len(attempts) == 1:
            raise OutboxError("STATE_UNAVAILABLE", sqlite_errorcode=code)
        return enqueue(*args)

    monkeypatch.setattr(outbox, "enqueue", blocked)
    result = capture_inventory(outbox, SCOPE, observations(1), clock=lambda: NOW,
                               capacity_wait_seconds=1)
    assert result.completed and result.records == 2 and result.batches == 1
    assert attempts[0] == attempts[1]
    assert outbox.checkpoint("windows:inventory").revision == 1
    assert len(drain(outbox)) == 1


@pytest.mark.parametrize("code", [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_CORRUPT])
def test_inventory_lock_retry_is_bounded_and_does_not_retry_corruption(tmp_path, monkeypatch, code):
    outbox = box(tmp_path)
    tick = [0.0]
    attempts = []

    def blocked(*args):
        attempts.append(tick[0])
        raise OutboxError("STATE_UNAVAILABLE", sqlite_errorcode=code)

    def wait(seconds):
        tick[0] += seconds

    monkeypatch.setattr(outbox, "enqueue", blocked)
    result = capture_inventory(outbox, SCOPE, observations(1), clock=lambda: NOW,
                               capacity_wait_seconds=0.25, monotonic=lambda: tick[0], wait=wait)
    assert not result.completed and result.records == 0
    assert result.errors == ("NATIVE_FAILED",)
    assert outbox.checkpoint("windows:inventory").revision == 0
    assert attempts == ([0.0, 0.1, 0.2] if code == sqlite3.SQLITE_BUSY else [0.0])


def test_partial_native_failure_is_fixed_and_last_checkpoint_incomplete(tmp_path):
    outbox = box(tmp_path)

    def provider():
        yield from observations(1)
        yield Observation(error_code="ACCESS_DENIED")
        raise OSError("private-secret-sensitive-path")

    result = capture_inventory(outbox, SCOPE, provider(), clock=lambda: NOW)
    assert result.errors == ("ACCESS_DENIED", "NATIVE_FAILED")
    assert not result.completed and result.records == 2
    assert outbox.checkpoint("windows:inventory").value["completed"] is False
    assert "private" not in repr(result)


def test_cancelled_capture_discards_only_volatile_records_and_closes(tmp_path):
    outbox = box(tmp_path)
    yielded = []
    closed = []

    def provider():
        try:
            for item in observations(10):
                yielded.append(True)
                yield item
        finally:
            closed.append(True)

    result = capture_inventory(
        outbox,
        SCOPE,
        provider(),
        max_records=2,
        clock=lambda: NOW,
        stopped=lambda: len(yielded) >= 4,
    )
    assert result.records == 2 and result.batches == 1 and result.errors == ("STOPPED",)
    assert not result.completed and closed == [True]
    assert outbox.checkpoint("windows:inventory").revision == 1


def test_heartbeat_independent_and_has_no_fake_usn_cursor(tmp_path):
    outbox = box(tmp_path)
    capture_inventory(outbox, SCOPE, observations(1), clock=lambda: NOW)
    first = outbox.claim(NOW)
    assert outbox.quarantine(first, "HTTP_REJECTED")
    identity = capture_heartbeat(outbox, error_code="ACCESS_DENIED", clock=lambda: NOW)
    heartbeat = outbox.claim(NOW)
    assert heartbeat.domain == "heartbeat" and heartbeat.batch_id == identity
    payload = json.loads(heartbeat.body)
    assert payload["records"][0] == {
        "occurred_at": "2026-01-01T00:00:00Z",
        "version": "0.1.0",
        "cursor": None,
        "lag_seconds": None,
        "error_code": "ACCESS_DENIED",
    }
    assert outbox.checkpoint("windows:heartbeat").value["sequence"] == 1
    assert outbox.acknowledge(heartbeat)
    capture_heartbeat(outbox, clock=lambda: NOW)
    assert outbox.checkpoint("windows:heartbeat").value["sequence"] == 2


@pytest.mark.parametrize("limit", [0, 513, True, 1.5])
def test_invalid_chunk_size_rejected(tmp_path, limit):
    with pytest.raises(CaptureError, match="^METADATA_INVALID$"):
        capture_inventory(
            box(tmp_path), SCOPE, observations(), max_records=limit, clock=lambda: NOW
        )


def test_serialized_byte_limit_splits_large_unicode_records(tmp_path):
    outbox = box(tmp_path)

    def provider():
        for index in range(150):
            yield Observation(
                record=FileObjectRecord(
                    occurred_at=NOW,
                    volume_identity="synthetic-volume",
                    file_id=str(index),
                    object_type="FILE",
                    name="Ж" * 30000,
                    relative_path="Ж" * 30000,
                )
            )

    result = capture_inventory(outbox, SCOPE, provider(), clock=lambda: NOW)
    assert result.completed and result.records == 150 and result.batches > 1
    total = 0
    while claim := outbox.claim(NOW):
        assert len(claim.body) <= 8 * 1024**2
        total += json.loads(claim.body)["record_count"]
        assert outbox.acknowledge(claim)
    assert total == 150


def test_cleanup_failure_cannot_commit_completed_checkpoint(tmp_path):
    outbox = box(tmp_path)

    class Provider:
        def __init__(self):
            self.source = observations(1)
            self.closed = 0

        def __iter__(self):
            return self

        def __next__(self):
            return next(self.source)

        def close(self):
            self.closed += 1
            raise OSError("private-sensitive-close-error")

    provider = Provider()
    result = capture_inventory(outbox, SCOPE, provider, clock=lambda: NOW)
    assert result.errors == ("NATIVE_FAILED",) and not result.completed
    assert provider.closed == 1
    assert outbox.checkpoint("windows:inventory").value["completed"] is False


def test_stopped_callback_failure_is_value_free_and_closes_provider(tmp_path):
    outbox = box(tmp_path)

    class Provider:
        def __init__(self):
            self.closed = False

        def __iter__(self):
            return self

        def __next__(self):
            raise AssertionError("must-not-enumerate")

        def close(self):
            self.closed = True

    provider = Provider()

    def failed():
        raise RuntimeError("private-secret-path")

    result = capture_inventory(outbox, SCOPE, provider, clock=lambda: NOW, stopped=failed)
    assert result.errors == ("NATIVE_FAILED",) and provider.closed
    assert outbox.checkpoint("windows:inventory").revision == 0


def test_tampered_capture_record_never_advances_checkpoint(tmp_path):
    outbox = box(tmp_path)
    record = next(observations()).record.model_copy(update={"filesystem": "x" * 33})
    result = capture_inventory(outbox, SCOPE, iter([Observation(record=record)]), clock=lambda: NOW)
    assert result.errors == ("METADATA_INVALID",) and not result.completed
    assert outbox.checkpoint("windows:inventory").revision == 0
    assert outbox.status().pending_count == 0
