"""Independent retained bytes and permanent delivery failures; no USN queue."""

import json
from uuid import UUID, uuid4

from test_windows_audit_store import Cipher

from collectors.common.transport import DeliveryOutcome
from collectors.windows_audit.store import AuditStore


class Sender:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.claims = []

    def send(self, claim):
        self.claims.append(claim)
        return next(self.outcomes)


def setup(tmp_path, outcomes):
    from collectors.windows_audit.delivery import Delivery

    store = AuditStore(tmp_path / "audit.sqlite3", UUID(int=4), Cipher())
    body = json.dumps(
        {
            "collector_id": str(store.collector_id),
            "batch_id": uuid4().hex,
            "records": [{"event_id": 4663}],
        }
    ).encode()
    store.commit("bookmark", {}, body)
    sender = Sender(outcomes)
    return Delivery(store, sender), store, sender, body


def test_lost_ack_replays_identical_bytes_then_acknowledges(tmp_path):
    delivery, store, sender, body = setup(
        tmp_path, [DeliveryOutcome("retry", "NETWORK"), DeliveryOutcome("accepted", duplicate=True)]
    )
    delivery.step(now=1000)
    assert store.peek() is not None
    delivery.step(now=2000)
    assert store.peek() is None and sender.claims[0].body == sender.claims[1].body == body


def test_quarantine_is_durable_and_never_discards_evidence(tmp_path):
    delivery, store, sender, _ = setup(tmp_path, [DeliveryOutcome("quarantined", "HTTP_REJECTED")])
    delivery.step(now=1000)
    delivery.step(now=2000)
    from collectors.windows_audit.delivery import Delivery

    Delivery(store, sender).step(now=3000)
    assert len(sender.claims) == 1 and store.peek() is not None
    assert store.delivery_state()["quarantine"] is True


def test_auth_suspension_is_separate_from_security_capture(tmp_path):
    delivery, store, sender, body = setup(tmp_path, [DeliveryOutcome("suspended", "AUTH_REQUIRED")])
    delivery.step(now=1000)
    store.commit(
        "next",
        {},
        body.replace(b"4663", b"4660").replace(
            json.loads(body)["batch_id"].encode(), uuid4().hex.encode()
        ),
    )
    delivery.step(now=2000)
    assert len(sender.claims) == 1 and store.status()["backlog"] == 2


def test_heartbeat_uses_published_state_without_opening_mutable_capture_file(tmp_path, monkeypatch):
    import threading
    from types import SimpleNamespace

    from pydantic import SecretStr

    from collectors.windows_audit import configuration, delivery

    stop = threading.Event()
    claims = []

    class HeartbeatSender:
        def send(self, claim):
            claims.append(claim)
            stop.set()
            return DeliveryOutcome("accepted")

    def forbidden_read(*_):
        raise AssertionError("MUTABLE_STATUS_FILE_MUST_NOT_BE_SHARED")

    monkeypatch.setattr(configuration, "MachineCipher", Cipher)
    monkeypatch.setattr(delivery, "Transport", lambda *_a, **_kw: HeartbeatSender())
    config = SimpleNamespace(
        collector_id=UUID(int=4),
        host_id=UUID(int=5),
        generation=UUID(int=6),
        token=SecretStr("a" * 43),
        ca_file="unused",
        origin="https://example.test",
        configured=True,
    )
    delivery.run_delivery(
        SimpleNamespace(root=tmp_path, read=forbidden_read),
        config,
        stop,
        status_reader=lambda: {"health": "OBSERVE", "policy_verified": True, "sacl_verified": True},
    )
    heartbeat = json.loads(claims[0].body)["records"][0]["audit"]
    assert heartbeat["configured"] is True and heartbeat["state"] == "OBSERVE"


def test_heartbeat_reports_large_scope_proof_without_claiming_full_coverage(tmp_path, monkeypatch):
    import threading
    from types import SimpleNamespace

    from pydantic import SecretStr

    from collectors.windows_audit import configuration, delivery

    stop = threading.Event()
    claims = []

    class Sender:
        def send(self, claim):
            claims.append(claim)
            stop.set()
            return DeliveryOutcome("accepted", duplicate=False)

    monkeypatch.setattr(configuration, "MachineCipher", Cipher)
    monkeypatch.setattr(delivery, "Transport", lambda *_a, **_kw: Sender())
    config = SimpleNamespace(
        collector_id=UUID(int=4), host_id=UUID(int=5), generation=UUID(int=6),
        token=SecretStr("a" * 43), ca_file="unused", origin="https://example.test", configured=True,
    )
    delivery.run_delivery(
        SimpleNamespace(root=tmp_path), config, stop,
        status_reader=lambda: {
            "health": "OBSERVE", "policy_verified": False, "sacl_verified": False,
            "readiness_objects": 52000, "readiness_complete": True, "readiness_stale": True,
            "readiness_checked_at": "2026-01-01T00:00:00+00:00", "readiness_age_seconds": 61.0,
            "readiness_duration_seconds": 25.0, "readiness_error": None,
        },
    )
    heartbeat = json.loads(claims[0].body)["records"][0]["audit"]
    assert heartbeat["configured"] is False
    assert heartbeat["state"] == "OBSERVE"
    assert heartbeat["readiness_objects"] == 52000
    assert heartbeat["readiness_stale"] is True
    assert heartbeat["readiness_duration_seconds"] == 25.0


def test_preexisting_audit_heartbeat_retains_canonical_receipt_fields():
    from packages.contracts.audit import AuditHealth

    health = AuditHealth(configured=True, state="HEALTHY", host_id=UUID(int=1))
    serialized = health.model_dump(mode="json")
    # These fields were stored by the previous release when computing receipt digests.
    assert set(serialized) == {
        "configured", "state", "host_id", "generation", "boot_id", "gap",
        "last_collected_at", "last_accepted_at", "bookmark_age_seconds",
        "remaining_record_margin", "read_count", "filtered_count", "backlog_count",
        "backlog_bytes", "quarantine", "error_code", "policy_verified", "sacl_verified",
    }


def test_stored_previous_release_audit_heartbeat_replays_without_receipt_conflict(ingest_setup):
    from copy import deepcopy
    from datetime import UTC, datetime
    from hashlib import sha256
    from uuid import uuid4

    from sqlalchemy import insert, update

    from packages.contracts.audit import AuditHealth
    from packages.contracts.common import BatchEnvelope
    from packages.contracts.heartbeat import HeartbeatRecord
    from packages.shared.models.core import collectors
    from packages.shared.models.jobs import ingest_batches

    client, engine, collector, bearer, _source = ingest_setup
    now = datetime(2026, 1, 1, tzinfo=UTC)
    batch = BatchEnvelope[HeartbeatRecord](
        collector_id=collector, batch_id=uuid4().hex, schema_version=1,
        sent_at=now, first_event_at=now, last_event_at=now, record_count=1,
        records=[HeartbeatRecord(
            occurred_at=now, version="synthetic", audit=AuditHealth(
                configured=True, state="HEALTHY", host_id=UUID(int=1),
                policy_verified=True, sacl_verified=True,
            ),
        )],
    )
    old_payload = deepcopy(batch.model_dump(mode="json"))
    old_health = old_payload["records"][0]["audit"]
    for key in tuple(old_health):
        if key.startswith("readiness_"):
            del old_health[key]
    old_digest = sha256(json.dumps(
        {"kind": "heartbeat", "batch": old_payload}, sort_keys=True,
        ensure_ascii=False, separators=(",", ":"),
    ).encode()).hexdigest()
    with engine.begin() as connection:
        connection.execute(update(collectors).where(collectors.c.id == collector).values(
            collector_type="AUDIT_WINDOWS"
        ))
        connection.execute(insert(ingest_batches).values(
            collector_id=collector, batch_id=batch.batch_id, schema_version=1, kind="heartbeat",
            payload_sha256=old_digest, record_count=1, sent_at=now, first_event_at=now,
            last_event_at=now,
        ))
    response = client.post(
        "/api/v1/ingest/heartbeat", json=old_payload,
        headers={"Authorization": "Bearer " + bearer},
    )
    assert response.status_code == 202
    assert response.json() == {"accepted": True, "duplicate": True}


def test_delivery_failure_retains_redacted_metadata_not_exception_text(tmp_path, monkeypatch):
    import threading
    from types import SimpleNamespace

    from pydantic import SecretStr

    from collectors.windows.diagnostics import valid_detail
    from collectors.windows_audit import configuration, delivery

    class BrokenSender:
        def send(self, _):
            raise RuntimeError("SYNTHETIC_SECRET_MUST_NOT_APPEAR")

    monkeypatch.setattr(configuration, "MachineCipher", Cipher)
    monkeypatch.setattr(delivery, "Transport", lambda *_a, **_kw: BrokenSender())
    config = SimpleNamespace(
        collector_id=UUID(int=4),
        host_id=UUID(int=5),
        generation=UUID(int=6),
        token=SecretStr("a" * 43),
        ca_file="unused",
        origin="https://example.test",
        configured=True,
    )
    stop = threading.Event()
    delivery.run_delivery(SimpleNamespace(root=tmp_path), config, stop, status_reader=lambda: {})
    outcome = AuditStore(tmp_path / "audit.sqlite3", config.collector_id, Cipher()).delivery_state()
    assert stop.is_set() and outcome["error_code"] == "AUDIT_DELIVERY_FAILED"
    assert valid_detail(outcome["diagnostic"]) and "SYNTHETIC_SECRET" not in json.dumps(outcome)
