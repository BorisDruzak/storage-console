from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from collectors.common.delivery import Delivery
from collectors.common.outbox import Limits, Outbox, OutboxError
from collectors.common.transport import DeliveryOutcome, TransportError
from packages.contracts.common import BatchEnvelope
from packages.contracts.heartbeat import HeartbeatRecord
from packages.contracts.inventory import FileObjectRecord, InventoryRecord

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def batch(collector, domain):
    record = (
        HeartbeatRecord(occurred_at=NOW, version="synthetic")
        if domain == "heartbeat"
        else FileObjectRecord(
            occurred_at=NOW,
            volume_identity="synthetic",
            file_id="1",
            object_type="FILE",
            name="file",
            relative_path="file",
        )
    )
    model = (
        BatchEnvelope[HeartbeatRecord] if domain == "heartbeat" else BatchEnvelope[InventoryRecord]
    )
    return model(
        collector_id=collector,
        batch_id=str(uuid4()),
        schema_version=1,
        sent_at=NOW,
        first_event_at=NOW,
        last_event_at=NOW,
        record_count=1,
        records=[record],
    )


def enqueue(box, domain, stream):
    value = batch(box.collector_id, domain)
    box.enqueue(domain, value, stream, box.checkpoint(stream).revision, {"cursor": value.batch_id})
    return value


@pytest.mark.parametrize(
    "field,value",
    [
        ("heartbeat_reserve_batches", -1),
        ("heartbeat_reserve_batches", True),
        ("heartbeat_reserve_batches", 1024),
        ("heartbeat_reserve_bytes", -1),
        ("heartbeat_reserve_bytes", True),
        ("heartbeat_reserve_bytes", 512 * 1024**2),
    ],
)
def test_invalid_reserves_fail_closed(field, value):
    with pytest.raises(OutboxError, match="^INVALID_LIMITS$"):
        Limits(**{field: value})


def test_count_reserve_rollback_replay_and_global_limit(tmp_path):
    box = Outbox(
        tmp_path / "private" / "queue",
        uuid4(),
        Limits(
            max_retained_batches=3,
            heartbeat_reserve_batches=1,
        ),
    )
    first = enqueue(box, "inventory", "data")
    enqueue(box, "inventory", "data")
    rejected = batch(box.collector_id, "inventory")
    with pytest.raises(OutboxError, match="^CAPACITY$"):
        box.enqueue("inventory", rejected, "data", 2, {"cursor": "rejected"})
    assert box.checkpoint("data").revision == 2
    assert box.status().pending_count == 2
    # Replay does not need extra capacity or change the checkpoint.
    box.enqueue("inventory", first, "data", 0, {"cursor": first.batch_id})
    enqueue(box, "heartbeat", "heartbeat")
    with pytest.raises(OutboxError, match="^CAPACITY$"):
        enqueue(box, "heartbeat", "heartbeat")
    assert box.checkpoint("heartbeat").revision == 1
    # Failure leaves no receipt: same immutable batch can be queued once space returns.
    claim = box.claim(NOW)
    assert claim is not None and box.acknowledge(claim)
    box.enqueue("inventory", rejected, "data", 2, {"cursor": "rejected"})
    assert box.checkpoint("data").revision == 3


def test_byte_reserve_includes_quarantined_bodies(tmp_path):
    collector = uuid4()
    data = batch(collector, "inventory")
    heartbeat = batch(collector, "heartbeat")
    data_size = len(data.model_dump_json().encode())
    heartbeat_size = len(heartbeat.model_dump_json().encode())
    box = Outbox(
        tmp_path / "private" / "queue",
        collector,
        Limits(
            max_retained_bytes=data_size + heartbeat_size,
            max_body_bytes=data_size + heartbeat_size,
            heartbeat_reserve_bytes=heartbeat_size,
        ),
    )
    box.enqueue("inventory", data, "data", 0, {})
    claim = box.claim(NOW)
    assert claim is not None and box.quarantine(claim, "HTTP_REJECTED")
    with pytest.raises(OutboxError, match="^CAPACITY$"):
        enqueue(box, "inventory", "other")
    assert box.checkpoint("other").revision == 0
    box.enqueue("heartbeat", heartbeat, "heartbeat", 0, {})
    assert box.status().retained_bytes == data_size + heartbeat_size


def test_independent_writers_cannot_consume_reserved_slot(tmp_path):
    collector = uuid4()
    path = tmp_path / "private" / "queue"
    limits = Limits(max_retained_batches=5, heartbeat_reserve_batches=2)
    boxes = [Outbox(path, collector, limits) for _ in range(8)]

    def write(index):
        try:
            enqueue(boxes[index], "inventory", f"data-{index}")
            return True
        except OutboxError as error:
            assert error.code == "CAPACITY"
            assert boxes[index].checkpoint(f"data-{index}").revision == 0
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(write, range(8))) == 3
    enqueue(boxes[0], "heartbeat", "heartbeat")
    enqueue(boxes[0], "heartbeat", "heartbeat")
    assert boxes[0].status().pending_count == 5


def test_independent_writers_cannot_consume_reserved_bytes(tmp_path):
    collector = uuid4()
    data_size = len(batch(collector, "inventory").model_dump_json().encode())
    heartbeat_size = len(batch(collector, "heartbeat").model_dump_json().encode())
    limits = Limits(
        max_retained_bytes=2 * data_size + heartbeat_size,
        max_body_bytes=data_size,
        heartbeat_reserve_bytes=heartbeat_size,
    )
    boxes = [Outbox(tmp_path / "private" / "queue", collector, limits) for _ in range(6)]

    def write(index):
        try:
            enqueue(boxes[index], "inventory", f"data-{index}")
            return True
        except OutboxError as error:
            assert error.code == "CAPACITY"
            assert boxes[index].checkpoint(f"data-{index}").revision == 0
            return False

    with ThreadPoolExecutor(max_workers=6) as pool:
        assert sum(pool.map(write, range(6))) == 2
    enqueue(boxes[0], "heartbeat", "heartbeat")
    assert boxes[0].status().retained_bytes == limits.max_retained_bytes


def test_default_reserve_and_order_remain_compatible(tmp_path):
    box = Outbox(tmp_path / "private" / "queue", uuid4(), Limits(max_retained_batches=2))
    data = enqueue(box, "inventory", "data")
    enqueue(box, "heartbeat", "heartbeat")
    claim = box.claim(NOW)
    assert claim is not None and claim.batch_id == data.batch_id


@pytest.mark.parametrize("blocked", ["quarantine", "retry", "lease"])
def test_priority_never_bypasses_a_stream_head(tmp_path, blocked):
    box = Outbox(tmp_path / "private" / "queue", uuid4())
    enqueue(box, "heartbeat", "heartbeat")
    enqueue(box, "heartbeat", "heartbeat")
    head = box.claim(NOW)
    assert head is not None
    if blocked == "quarantine":
        assert box.quarantine(head, "HTTP_REJECTED")
    elif blocked == "retry":
        assert box.retry(head, "NETWORK", NOW + timedelta(seconds=10))
    data = enqueue(box, "inventory", "data")
    claim = box.claim(NOW, heartbeat_priority="first")
    assert claim is not None and claim.batch_id == data.batch_id
    assert box.acknowledge(claim)
    assert box.claim(NOW, heartbeat_priority="first") is None


def test_priority_first_last_and_invalid_mode(tmp_path):
    box = Outbox(tmp_path / "private" / "queue", uuid4())
    data = enqueue(box, "inventory", "data")
    heartbeat = enqueue(box, "heartbeat", "heartbeat")
    claim = box.claim(NOW, heartbeat_priority="first")
    assert claim is not None and claim.batch_id == heartbeat.batch_id
    assert box.retry(claim, "NETWORK", NOW)
    claim = box.claim(NOW, heartbeat_priority="last")
    assert claim is not None and claim.batch_id == data.batch_id
    with pytest.raises(OutboxError, match="^INVALID_PRIORITY$"):
        box.claim(NOW, heartbeat_priority="untrusted")


class Sender:
    def __init__(self, collector_id):
        self.collector_id = collector_id
        self.domains = []

    def send(self, claim):
        self.domains.append(claim.domain)
        return DeliveryOutcome("accepted", duplicate=False)


def test_delivery_burst_is_fair_even_when_all_heartbeats_precede_data(tmp_path):
    box = Outbox(tmp_path / "private" / "queue", uuid4())
    for _ in range(8):
        enqueue(box, "heartbeat", "heartbeat")
    for _ in range(2):
        enqueue(box, "inventory", "data")
    sender = Sender(box.collector_id)
    delivery = Delivery(box, sender, prefer_heartbeat=True, heartbeat_burst=2, clock=lambda: NOW)
    for _ in range(10):
        assert delivery.run_once().state == "accepted"
    assert sender.domains == ["heartbeat", "heartbeat", "inventory"] * 2 + ["heartbeat"] * 4
    assert delivery.run_once().state == "idle"


def test_retry_attempts_count_towards_burst_and_refresh_resets_it(tmp_path):
    box = Outbox(tmp_path / "private" / "queue", uuid4())
    enqueue(box, "heartbeat", "heartbeat")
    enqueue(box, "inventory", "data")
    clock = [NOW]

    class RetryingSender(Sender):
        def send(self, claim):
            self.domains.append(claim.domain)
            return DeliveryOutcome("retry", code="NETWORK")

    sender = RetryingSender(box.collector_id)
    delivery = Delivery(
        box,
        sender,
        prefer_heartbeat=True,
        heartbeat_burst=1,
        clock=lambda: clock[0],
        randomness=lambda: 0,
    )
    assert delivery.run_once().state == "retry"
    clock[0] += timedelta(seconds=1)
    assert delivery.run_once().state == "retry"
    assert sender.domains == ["heartbeat", "inventory"]
    clock[0] += timedelta(seconds=2)
    assert delivery.run_once().state == "retry"
    current = Sender(box.collector_id)
    delivery.refresh_credentials(current)
    clock[0] += timedelta(seconds=3)
    assert delivery.run_once().state == "accepted"
    assert current.domains == ["heartbeat"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"prefer_heartbeat": 1},
        {"heartbeat_burst": True},
        {"heartbeat_burst": 0},
        {"heartbeat_burst": 101},
    ],
)
def test_invalid_delivery_priority_settings_are_rejected(tmp_path, kwargs):
    box = Outbox(tmp_path / "private" / "queue", uuid4())
    with pytest.raises(TransportError, match="^INVALID_CONFIG$"):
        Delivery(box, Sender(box.collector_id), **kwargs)
