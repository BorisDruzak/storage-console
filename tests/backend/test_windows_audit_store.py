"""Independent transactional checkpoint, encrypted queue and replay."""

import sqlite3
from uuid import UUID

import pytest
from test_windows_audit_events import module, parse, xml


class Cipher:
    def protect(self, value):
        return b"protected:" + bytes(byte ^ 0xAA for byte in value)

    def unprotect(self, value):
        assert value.startswith(b"protected:")
        return bytes(byte ^ 0xAA for byte in value[10:])


def store(tmp_path, **kwargs):
    return module("store").AuditStore(tmp_path / "audit.sqlite", UUID(int=9), Cipher(), **kwargs)


def test_bookmark_cache_receipt_atomic_restart_and_byte_identical_lost_ack(tmp_path):
    db = store(tmp_path)
    body = b'{"records":["synthetic"]}'
    db.commit("bookmark-10", {"session": "private-local"}, body)
    reopened = store(tmp_path)
    assert reopened.checkpoint() == ("bookmark-10", {"session": "private-local"})
    batch_id, sent = reopened.peek()
    assert sent == body and reopened.peek() == (batch_id, body)
    reopened.acknowledge(batch_id)
    assert reopened.peek() is None and reopened.checkpoint()[0] == "bookmark-10"
    contents = (tmp_path / "audit.sqlite").read_bytes()
    assert b"private-local" not in contents and body not in contents


def test_capacity_failure_cannot_advance_bookmark_or_caches(tmp_path):
    db = store(tmp_path, max_bytes=128)
    db.commit("before", {}, b"x")
    with pytest.raises(module("store").AuditStoreError, match="AUDIT_BACKPRESSURE"):
        db.commit("after", {"bad": True}, b"y" * 256)
    assert db.checkpoint() == ("before", {})


def test_filtered_event_advances_without_queue_and_gap_latches_across_restart(tmp_path):
    db = store(tmp_path)
    db.commit("filtered-100", {}, None)
    assert db.peek() is None
    db.latch_gap("AUDIT_LOG_CLEARED")
    assert store(tmp_path).gap() == "AUDIT_LOG_CLEARED"
    with pytest.raises(module("store").AuditStoreError, match="AUDIT_GAP"):
        db.commit("future-only", {}, b"x")


def test_different_collector_cannot_adopt_existing_queue(tmp_path):
    store(tmp_path)
    with pytest.raises(module("store").AuditStoreError, match="AUDIT_IDENTITY_CONFLICT"):
        module("store").AuditStore(tmp_path / "audit.sqlite", UUID(int=8), Cipher())


def test_selector_cache_roundtrip_is_bounded_and_minimal(tmp_path):
    api = module("scope")
    selector = api.Selector(api.AuditScope({r"C:\Pilot": "volume-a"}), capacity=2)
    for i in range(10):
        selector.process(parse(xml(4624, record=i + 1, TargetLogonId=hex(i + 1))))
    state = selector.snapshot()
    assert len(state["sessions"]) <= 2
    assert "raw_xml" not in str(state)
    restored = api.Selector(api.AuditScope({r"C:\Pilot": "volume-a"}), state=state, capacity=2)
    assert restored.snapshot() == state


def test_transaction_error_rolls_back_checkpoint(tmp_path):
    db = store(tmp_path)
    db.commit("before", {}, None)
    with sqlite3.connect(tmp_path / "audit.sqlite") as sql:
        sql.execute(
            "CREATE TRIGGER fail_queue BEFORE INSERT ON queue BEGIN SELECT RAISE(ABORT,'fail'); END"
        )
    with pytest.raises(module("store").AuditStoreError):
        db.commit("after", {}, b"x")
    assert db.checkpoint()[0] == "before"
