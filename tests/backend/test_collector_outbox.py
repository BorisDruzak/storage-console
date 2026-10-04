import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

import pytest

from collectors.common.outbox import Limits, Outbox, OutboxError
from packages.contracts.common import BatchEnvelope
from packages.contracts.heartbeat import HeartbeatRecord


def heartbeat(collector_id: UUID, batch_id: str | None = None):
    stamp = datetime.now(UTC)
    return BatchEnvelope[HeartbeatRecord](
        collector_id=collector_id,
        batch_id=batch_id or str(uuid4()),
        schema_version=1,
        sent_at=stamp,
        first_event_at=stamp,
        last_event_at=stamp,
        record_count=1,
        records=[HeartbeatRecord(occurred_at=stamp, version="synthetic")],
    )


def test_enqueue_and_checkpoint_survive_reopen_as_one_commit(tmp_path):
    collector = uuid4()
    path = tmp_path / "private" / "outbox.sqlite3"
    outbox = Outbox(path, collector)
    assert outbox.checkpoint("heartbeat").revision == 0
    batch = heartbeat(collector)
    outbox.enqueue("heartbeat", batch, "heartbeat", 0, {"cursor": "1"})
    restored = Outbox(path, collector)
    checkpoint = restored.checkpoint("heartbeat")
    assert (checkpoint.revision, checkpoint.value) == (1, {"cursor": "1"})
    claim = restored.claim(datetime.now(UTC))
    assert claim is not None and claim.batch_id == batch.batch_id
    assert claim.body == batch.model_dump_json().encode()


def test_stale_checkpoint_never_adds_a_batch_or_advances_state(tmp_path):
    collector = uuid4()
    outbox = Outbox(tmp_path / "private" / "outbox.sqlite3", collector)
    first = heartbeat(collector)
    outbox.enqueue("heartbeat", first, "heartbeat", 0, {"cursor": "1"})
    with pytest.raises(OutboxError) as failure:
        outbox.enqueue("heartbeat", heartbeat(collector), "heartbeat", 0, {"cursor": "2"})
    assert failure.value.code == "CHECKPOINT_CONFLICT"
    assert outbox.checkpoint("heartbeat").value == {"cursor": "1"}
    assert outbox.status().pending_count == 1


def test_exact_transition_replay_is_idempotent_but_changed_payload_is_conflict(tmp_path):
    collector = uuid4()
    outbox = Outbox(tmp_path / "private" / "outbox.sqlite3", collector)
    batch = heartbeat(collector)
    outbox.enqueue("heartbeat", batch, "heartbeat", 0, {"cursor": "1"})
    outbox.enqueue("heartbeat", batch, "heartbeat", 0, {"cursor": "1"})
    assert outbox.status().pending_count == 1
    changed = batch.model_copy(
        update={"records": [HeartbeatRecord(occurred_at=batch.first_event_at, version="different")]}
    )
    with pytest.raises(OutboxError) as failure:
        outbox.enqueue("heartbeat", changed, "heartbeat", 0, {"cursor": "1"})
    assert failure.value.code == "BATCH_CONFLICT"


def test_different_collector_cannot_reuse_durable_state(tmp_path):
    path = tmp_path / "private" / "outbox.sqlite3"
    Outbox(path, uuid4())
    with pytest.raises(OutboxError) as failure:
        Outbox(path, uuid4())
    assert failure.value.code == "IDENTITY_CONFLICT"


@pytest.mark.parametrize("domain", ["unknown", "../heartbeat", "inventory"])
def test_domain_validation_leaves_capture_state_unchanged(tmp_path, domain):
    collector = uuid4()
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", collector)
    with pytest.raises(OutboxError) as failure:
        box.enqueue(domain, heartbeat(collector), "stream", 0, {})
    assert failure.value.code == "INVALID_BATCH"
    assert box.checkpoint("stream").revision == box.status().pending_count == 0


def test_mutated_envelope_and_wrong_identity_are_revalidated(tmp_path):
    collector = uuid4()
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", collector)
    for batch in [heartbeat(uuid4()), heartbeat(collector).model_copy(update={"record_count": 2})]:
        with pytest.raises(OutboxError) as failure:
            box.enqueue("heartbeat", batch, "stream", 0, {})
        assert failure.value.code == "INVALID_BATCH"
    assert box.status().pending_count == 0


@pytest.mark.parametrize("checkpoint", [{"cursor": float("nan")}, {"cursor": "x" * 16384}])
def test_invalid_checkpoint_never_advances_capture(tmp_path, checkpoint):
    collector = uuid4()
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", collector)
    with pytest.raises(OutboxError) as failure:
        box.enqueue("heartbeat", heartbeat(collector), "stream", 0, checkpoint)
    assert failure.value.code == "INVALID_CHECKPOINT"
    assert box.checkpoint("stream").revision == box.status().pending_count == 0


def test_utf8_evidence_and_checkpoint_are_preserved_without_normalizing_identities(tmp_path):
    collector = uuid4()
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", collector)
    batch = heartbeat(collector)
    batch.records[0].version = "синтетический"
    box.enqueue("heartbeat", batch, "Поток", 0, {"cursor": "Пример"})
    claim = box.claim(datetime.now(UTC))
    assert claim is not None and claim.body == batch.model_dump_json().encode("utf-8")
    assert "синтетический".encode() in claim.body
    assert box.checkpoint("Поток").value == {"cursor": "Пример"}


@pytest.mark.parametrize("location", ["body", "checkpoint"])
def test_invalid_unicode_does_not_add_work_or_advance_capture(tmp_path, location):
    collector = uuid4()
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", collector)
    batch = heartbeat(collector)
    checkpoint = {"cursor": "safe"}
    if location == "body":
        batch.records[0].version = "\ud800"
    else:
        checkpoint["cursor"] = "\ud800"
    with pytest.raises(OutboxError) as failure:
        box.enqueue("heartbeat", batch, "stream", 0, checkpoint)
    assert failure.value.code == ("INVALID_BATCH" if location == "body" else "INVALID_CHECKPOINT")
    assert box.checkpoint("stream").revision == box.status().pending_count == 0


def test_capacity_retains_quarantine_and_rejects_without_checkpoint_change(tmp_path):
    collector = uuid4()
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", collector, Limits(max_retained_batches=1))
    box.enqueue("heartbeat", heartbeat(collector), "stream", 0, {})
    claim = box.claim(datetime.now(UTC))
    assert claim is not None
    assert box.quarantine(claim, "HTTP_REJECTED")
    with pytest.raises(OutboxError) as failure:
        box.enqueue("heartbeat", heartbeat(collector), "other", 0, {})
    assert failure.value.code == "CAPACITY"
    assert box.checkpoint("other").revision == 0
    assert box.status().quarantined_count == 1
    assert box.status().retained_bytes == len(claim.body)


def test_claim_expiry_replays_exact_bytes_and_stale_ack_cannot_delete_new_lease(tmp_path):
    collector = uuid4()
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", collector)
    box.enqueue("heartbeat", heartbeat(collector), "stream", 0, {})
    now = datetime.now(UTC)
    first = box.claim(now)
    assert first is not None and box.claim(now + timedelta(seconds=59)) is None
    second = box.claim(now + timedelta(seconds=60))
    assert second is not None and second.lease_id != first.lease_id
    assert second.body == first.body
    assert not box.acknowledge(first)
    assert not box.retry(first, "NETWORK", now + timedelta(seconds=120))
    assert not box.quarantine(first, "HTTP_REJECTED")
    assert box.acknowledge(second)
    assert box.status().pending_count == 0


def test_stream_fifo_blocks_backoff_and_quarantine_but_other_streams_progress(tmp_path):
    collector = uuid4()
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", collector)
    first, second, other = [heartbeat(collector) for _ in range(3)]
    box.enqueue("heartbeat", first, "a", 0, {"cursor": 1})
    box.enqueue("heartbeat", second, "a", 1, {"cursor": 2})
    box.enqueue("heartbeat", other, "b", 0, {})
    now = datetime.now(UTC)
    claim = box.claim(now)
    assert claim is not None and claim.batch_id == first.batch_id
    assert box.retry(claim, "NETWORK", now + timedelta(seconds=10))
    independent = box.claim(now)
    assert independent is not None and independent.batch_id == other.batch_id
    assert box.acknowledge(independent)
    assert box.claim(now) is None
    head = box.claim(now + timedelta(seconds=10))
    assert head is not None and head.batch_id == first.batch_id
    assert box.quarantine(head, "HTTP_REJECTED")
    assert box.claim(now + timedelta(days=1)) is None
    assert box.status().pending_count == 1 and box.status().quarantined_count == 1


def test_lost_enqueue_ack_can_replay_after_delivery_ack_but_forgotten_receipt_conflicts(tmp_path):
    collector = uuid4()
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", collector, Limits(max_receipts=1))
    first = heartbeat(collector)
    box.enqueue("heartbeat", first, "stream", 0, {"cursor": 1})
    claim = box.claim(datetime.now(UTC))
    assert claim is not None and box.acknowledge(claim)
    box.enqueue("heartbeat", first, "stream", 0, {"cursor": 1})
    assert box.status().pending_count == 0
    box.enqueue("heartbeat", heartbeat(collector), "stream", 1, {"cursor": 2})
    with pytest.raises(OutboxError) as failure:
        box.enqueue("heartbeat", first, "stream", 0, {"cursor": 1})
    assert failure.value.code == "CHECKPOINT_CONFLICT"


def test_sql_failure_rolls_back_batch_and_checkpoint(tmp_path):
    collector = uuid4()
    path = tmp_path / "private" / "outbox.sqlite3"
    box = Outbox(path, collector)
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TRIGGER fail_checkpoint BEFORE INSERT ON checkpoints "
            "BEGIN SELECT RAISE(ABORT, 'synthetic private failure'); END"
        )
    with pytest.raises(OutboxError) as failure:
        box.enqueue("heartbeat", heartbeat(collector), "stream", 0, {})
    assert failure.value.code == "STATE_UNAVAILABLE"
    assert "private" not in str(failure.value)
    assert box.checkpoint("stream").revision == box.status().pending_count == 0


@pytest.mark.parametrize("rollback_fails", [False, True])
def test_commit_failure_keeps_both_capture_states_unchanged_and_errors_generic(
    tmp_path, monkeypatch, rollback_fails
):
    collector = uuid4()
    path = tmp_path / "private" / "outbox.sqlite3"
    box = Outbox(path, collector)

    class FailedCommit(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql == "COMMIT" or (rollback_fails and sql == "ROLLBACK"):
                raise sqlite3.OperationalError("synthetic private disk failure")
            return super().execute(sql, parameters)

    original = Outbox._connect

    def connect(self):
        db = sqlite3.connect(self.path, autocommit=True, factory=FailedCommit)
        db.row_factory = sqlite3.Row
        return db

    monkeypatch.setattr(Outbox, "_connect", connect)
    with pytest.raises(OutboxError) as failure:
        box.enqueue("heartbeat", heartbeat(collector), "stream", 0, {})
    assert str(failure.value) == "STATE_UNAVAILABLE"
    monkeypatch.setattr(Outbox, "_connect", original)
    assert box.checkpoint("stream").revision == box.status().pending_count == 0


def test_concurrent_capture_has_one_cas_winner_and_claimers_have_one_lease(tmp_path):
    collector = uuid4()
    path = tmp_path / "private" / "outbox.sqlite3"
    box = Outbox(path, collector)

    def produce(_):
        try:
            Outbox(path, collector).enqueue("heartbeat", heartbeat(collector), "stream", 0, {})
            return "accepted"
        except OutboxError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(produce, range(4)))
        claims = list(pool.map(lambda _: box.claim(datetime.now(UTC)), range(4)))
    assert results.count("accepted") == 1 and results.count("CHECKPOINT_CONFLICT") == 3
    assert sum(claim is not None for claim in claims) == 1
    assert box.checkpoint("stream").revision == box.status().pending_count == 1


def test_future_schema_and_unrelated_database_are_not_modified(tmp_path):
    collector = uuid4()
    path = tmp_path / "private" / "outbox.sqlite3"
    Outbox(path, collector)
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=3")
    before = path.read_bytes()
    with pytest.raises(OutboxError) as failure:
        Outbox(path, collector)
    assert failure.value.code == "SCHEMA_UNSUPPORTED"
    assert path.read_bytes() == before
    other = path.parent / "other.sqlite3"
    with sqlite3.connect(other) as db:
        db.execute("CREATE TABLE unrelated(value TEXT)")
    if os.name == "posix":
        other.chmod(0o600)
    with pytest.raises(OutboxError) as failure:
        Outbox(other, collector)
    assert failure.value.code == "SCHEMA_UNSUPPORTED"


@pytest.mark.skipif(os.name != "posix", reason="Windows ACL protection is a runtime gate")
def test_private_container_and_database_permissions_are_enforced(tmp_path):
    collector = uuid4()
    path = tmp_path / "private" / "outbox.sqlite3"
    Outbox(path, collector)
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    path.chmod(0o644)
    with pytest.raises(OutboxError) as failure:
        Outbox(path, collector)
    assert failure.value.code == "UNSAFE_STATE"


@pytest.mark.skipif(os.name != "posix", reason="Unprivileged Windows symlinks are not assumed")
def test_symlink_parent_and_hardlinked_database_are_rejected(tmp_path):
    collector = uuid4()
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(OutboxError) as failure:
        Outbox(link / "outbox.sqlite3", collector)
    assert failure.value.code == "UNSAFE_STATE"
    path = target / "outbox.sqlite3"
    Outbox(path, collector)
    os.link(path, target / "alias.sqlite3")
    with pytest.raises(OutboxError) as failure:
        Outbox(path, collector)
    assert failure.value.code == "UNSAFE_STATE"


@pytest.mark.parametrize(
    "settings",
    [
        {"max_retained_batches": 0},
        {"max_retained_batches": True},
        {"lease_seconds": 15},
        {"max_receipts": 0},
        {"max_body_bytes": 16777217},
        {"max_retained_bytes": 1},
        {"max_checkpoint_bytes": 16385},
    ],
)
def test_invalid_limits_fail_before_state_is_opened(settings):
    with pytest.raises(OutboxError) as failure:
        Limits(**settings)
    assert failure.value.code == "INVALID_LIMITS"


def test_byte_and_body_capacity_fail_without_losing_retained_data(tmp_path):
    collector = uuid4()
    batch = heartbeat(collector)
    size = len(batch.model_dump_json().encode())
    small = Outbox(
        tmp_path / "small" / "outbox.sqlite3", collector, Limits(max_body_bytes=size - 1)
    )
    with pytest.raises(OutboxError) as failure:
        small.enqueue("heartbeat", batch, "stream", 0, {})
    assert failure.value.code == "INVALID_BATCH" and small.status().pending_count == 0
    box = Outbox(
        tmp_path / "private" / "outbox.sqlite3",
        collector,
        Limits(max_body_bytes=size, max_retained_bytes=size),
    )
    box.enqueue("heartbeat", batch, "stream", 0, {})
    with pytest.raises(OutboxError) as failure:
        box.enqueue("heartbeat", heartbeat(collector), "other", 0, {})
    assert failure.value.code == "CAPACITY"
    assert box.status().retained_bytes == size and box.checkpoint("other").revision == 0


def test_same_batch_with_changed_checkpoint_transition_is_conflict(tmp_path):
    collector = uuid4()
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", collector)
    batch = heartbeat(collector)
    box.enqueue("heartbeat", batch, "stream", 0, {"cursor": "Пример"})
    for stream, revision, checkpoint in [
        ("other", 0, {"cursor": "Пример"}),
        ("stream", 1, {"cursor": "Пример"}),
        ("stream", 0, {"cursor": "changed"}),
    ]:
        with pytest.raises(OutboxError) as failure:
            box.enqueue("heartbeat", batch, stream, revision, checkpoint)
        assert failure.value.code == "BATCH_CONFLICT"
    assert box.checkpoint("stream").value == {"cursor": "Пример"}


def test_running_collector_rejects_a_schema_or_identity_change_without_writing(tmp_path):
    collector = uuid4()
    path = tmp_path / "private" / "outbox.sqlite3"
    box = Outbox(path, collector)
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=3")
    with pytest.raises(OutboxError) as failure:
        box.enqueue("heartbeat", heartbeat(collector), "stream", 0, {})
    assert failure.value.code == "SCHEMA_UNSUPPORTED"
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM batches").fetchone()[0] == 0
        db.execute("PRAGMA user_version=2")
        db.execute("UPDATE meta SET collector_id=?", (str(uuid4()),))
    with pytest.raises(OutboxError) as failure:
        box.checkpoint("stream")
    assert failure.value.code == "IDENTITY_CONFLICT"


def test_corrupt_retained_bytes_are_not_claimed_or_removed(tmp_path):
    collector = uuid4()
    path = tmp_path / "private" / "outbox.sqlite3"
    box = Outbox(path, collector)
    batch = heartbeat(collector)
    box.enqueue("heartbeat", batch, "stream", 0, {})
    with sqlite3.connect(path) as db:
        db.execute("UPDATE batches SET body=?", (b"{}",))
    with pytest.raises(OutboxError) as failure:
        box.claim(datetime.now(UTC))
    assert failure.value.code == "STATE_UNAVAILABLE"
    assert box.status().pending_count == 1


def test_corrupt_checkpoint_is_reported_without_exposing_stored_values(tmp_path):
    collector = uuid4()
    path = tmp_path / "private" / "outbox.sqlite3"
    box = Outbox(path, collector)
    box.enqueue("heartbeat", heartbeat(collector), "stream", 0, {})
    with sqlite3.connect(path) as db:
        db.execute("UPDATE checkpoints SET value=?", ("synthetic-invalid-json",))
    with pytest.raises(OutboxError) as failure:
        box.checkpoint("stream")
    assert str(failure.value) == "STATE_UNAVAILABLE"
    assert box.status().pending_count == 1


def test_subprocess_crash_before_checkpoint_rolls_back_and_after_commit_replays(tmp_path):
    collector = uuid4()
    path = tmp_path / "private" / "outbox.sqlite3"
    Outbox(path, collector)
    batch = heartbeat(collector)
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TRIGGER crash_checkpoint BEFORE INSERT ON checkpoints "
            "BEGIN SELECT simulate_crash(); END"
        )
    script = """
import os,sys
from pathlib import Path
from uuid import UUID
from collectors.common.outbox import Outbox
from packages.contracts.common import BatchEnvelope
from packages.contracts.heartbeat import HeartbeatRecord
original=Outbox._connect
def connect(self):
    db=original(self)
    db.create_function('simulate_crash',0,lambda: os._exit(23))
    return db
Outbox._connect=connect
box=Outbox(Path(sys.argv[1]),UUID(sys.argv[2]))
box.enqueue('heartbeat',BatchEnvelope[HeartbeatRecord].model_validate_json(sys.stdin.read()),
            'stream',0,{'cursor':1})
os._exit(24)
"""
    command = [sys.executable, "-c", script, str(path), str(collector)]
    first = subprocess.run(
        command, input=batch.model_dump_json(), text=True, capture_output=True, timeout=20
    )
    assert first.returncode == 23, first.stderr
    restored = Outbox(path, collector)
    assert restored.checkpoint("stream").revision == restored.status().pending_count == 0
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER crash_checkpoint")
    second = subprocess.run(
        command, input=batch.model_dump_json(), text=True, capture_output=True, timeout=20
    )
    assert second.returncode == 24, second.stderr
    restored = Outbox(path, collector)
    restored.enqueue("heartbeat", batch, "stream", 0, {"cursor": 1})
    assert restored.checkpoint("stream").revision == restored.status().pending_count == 1
    claim = restored.claim(datetime.now(UTC))
    assert claim is not None and claim.body == batch.model_dump_json().encode()


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner/mode checks are Linux acceptance")
@pytest.mark.parametrize("unsafe", ["parent", "sidecar"])
def test_existing_instance_rejects_newly_unsafe_parent_and_sidecar(tmp_path, unsafe):
    collector = uuid4()
    path = tmp_path / "private" / "outbox.sqlite3"
    box = Outbox(path, collector)
    if unsafe == "parent":
        path.parent.chmod(0o777)
    else:
        target = tmp_path / "unrelated"
        target.write_bytes(b"")
        target.chmod(0o600)
        os.link(target, path.parent / "outbox.sqlite3-journal")
    with pytest.raises(OutboxError) as failure:
        box.checkpoint("stream")
    assert failure.value.code == "UNSAFE_STATE"


def legacy_state(tmp_path):
    collector = uuid4()
    batch = heartbeat(collector)
    path = tmp_path / "legacy" / "outbox.sqlite3"
    path.parent.mkdir(mode=0o700)
    body = batch.model_dump_json().encode()
    # Fixture represents the previously published version1 format, not current DDL.
    with sqlite3.connect(path) as db:
        db.executescript("""
CREATE TABLE meta(collector_id TEXT NOT NULL);
CREATE TABLE checkpoints(stream TEXT PRIMARY KEY, revision INTEGER NOT NULL,value TEXT NOT NULL);
CREATE TABLE batches(seq INTEGER PRIMARY KEY AUTOINCREMENT,batch_id TEXT UNIQUE NOT NULL,
 domain TEXT NOT NULL,stream TEXT NOT NULL,body BLOB NOT NULL,digest TEXT NOT NULL,
 revision INTEGER NOT NULL,checkpoint TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',
 lease_id TEXT,lease_until REAL,next_attempt REAL NOT NULL DEFAULT 0,
 attempts INTEGER NOT NULL DEFAULT 0,error_code TEXT);
CREATE INDEX batch_stream_order ON batches(stream,seq);
CREATE TABLE receipts(seq INTEGER PRIMARY KEY AUTOINCREMENT,batch_id TEXT UNIQUE NOT NULL,
 domain TEXT NOT NULL,stream TEXT NOT NULL,digest TEXT NOT NULL,revision INTEGER NOT NULL,
 checkpoint TEXT NOT NULL);
PRAGMA application_id=0x53434F42;
PRAGMA user_version=1;
""")
        db.execute("INSERT INTO meta VALUES (?)", (str(collector),))
        db.execute("INSERT INTO checkpoints VALUES ('stream',1,?)", ('{"cursor":1}',))
        db.execute(
            "INSERT INTO batches(batch_id,domain,stream,body,digest,revision,checkpoint) "
            "VALUES (?,'heartbeat','stream',?,?,0,?)",
            (batch.batch_id, body, sha256(body).hexdigest(), '{"cursor":1}'),
        )
        db.execute(
            "INSERT INTO receipts(batch_id,domain,stream,digest,revision,checkpoint) "
            "VALUES (?,'heartbeat','stream',?,0,?)",
            (batch.batch_id, sha256(body).hexdigest(), '{"cursor":1}'),
        )
    path.chmod(0o600)
    return path, collector, batch


def test_schema1_migration_preserves_pending_bytes_checkpoint_and_enqueue_receipt(tmp_path):
    path, collector, batch = legacy_state(tmp_path)
    box = Outbox(path, collector)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
    assert not box.auth_suspended() and box.credential_generation() == 0
    box.enqueue("heartbeat", batch, "stream", 0, {"cursor": 1})
    assert box.checkpoint("stream").revision == box.status().pending_count == 1
    claim = box.claim(datetime.now(UTC))
    assert claim is not None and claim.body == batch.model_dump_json().encode()


def test_interrupted_migration_leaves_schema1_and_all_evidence_intact(tmp_path, monkeypatch):
    path, collector, batch = legacy_state(tmp_path)
    original = Outbox._connect

    def connect(self):
        db = original(self)
        count = [0]

        def authorize(action, *_args):
            if action == sqlite3.SQLITE_ALTER_TABLE:
                count[0] += 1
                if count[0] == 2:
                    return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        db.set_authorizer(authorize)
        return db

    monkeypatch.setattr(Outbox, "_connect", connect)
    with pytest.raises(OutboxError) as failure:
        Outbox(path, collector)
    assert failure.value.code == "STATE_UNAVAILABLE"
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert [row[1] for row in db.execute("PRAGMA table_info(meta)")] == ["collector_id"]
        assert (
            db.execute("SELECT body FROM batches").fetchone()[0] == batch.model_dump_json().encode()
        )
