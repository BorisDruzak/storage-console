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
