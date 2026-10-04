from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from collectors.common.delivery import Delivery
from collectors.common.outbox import Outbox
from collectors.common.transport import DeliveryOutcome
from packages.contracts.common import BatchEnvelope
from packages.contracts.heartbeat import HeartbeatRecord


def queued(tmp_path):
    collector = uuid4()
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", collector)
    now = datetime.now(UTC)
    batch = BatchEnvelope[HeartbeatRecord](
        collector_id=collector,
        batch_id=str(uuid4()),
        schema_version=1,
        sent_at=now,
        first_event_at=now,
        last_event_at=now,
        record_count=1,
        records=[HeartbeatRecord(occurred_at=now, version="synthetic")],
    )
    box.enqueue("heartbeat", batch, "stream", 0, {"cursor": 1})
    return box, batch, now


class Sender:
    def __init__(self, collector_id, *outcomes):
        self.collector_id = collector_id
        self.outcomes = list(outcomes)
        self.claims = []

    def send(self, claim):
        self.claims.append(claim)
        return self.outcomes.pop(0)


def test_lost_response_retries_identical_batch_and_both_receipts_ack(tmp_path):
    box, batch, now = queued(tmp_path)
    clock = [now]
    sender = Sender(
        box.collector_id,
        DeliveryOutcome("retry", code="NETWORK"),
        DeliveryOutcome("accepted", duplicate=True),
    )
    delivery = Delivery(box, sender, clock=lambda: clock[0], randomness=lambda: 0)
    assert delivery.run_once().state == "retry"
    assert delivery.run_once().state == "idle"
    clock[0] += timedelta(seconds=1)
    assert delivery.run_once().state == "accepted"
    assert sender.claims[0].body == sender.claims[1].body == batch.model_dump_json().encode()
    assert sender.claims[0].batch_id == sender.claims[1].batch_id
    assert box.status().pending_count == 0 and box.checkpoint("stream").revision == 1


def test_revoked_credential_suspension_survives_restart_until_explicit_refresh(tmp_path):
    box, _, now = queued(tmp_path)
    revoked = Sender(box.collector_id, DeliveryOutcome("suspended", code="AUTH_REQUIRED"))
    delivery = Delivery(box, revoked, clock=lambda: now)
    assert delivery.run_once().state == "suspended"
    assert box.auth_suspended() and box.claim(now) is None
    restored = Outbox(box.path, box.collector_id)
    current = Sender(box.collector_id, DeliveryOutcome("accepted", duplicate=False))
    restarted = Delivery(restored, current, clock=lambda: now)
    assert restarted.run_once().state == "suspended" and not current.claims
    restarted.refresh_credentials(current)
    assert restarted.run_once().state == "accepted"
    assert len(revoked.claims) == len(current.claims) == 1
    assert restored.status().pending_count == 0 and not restored.auth_suspended()


def test_permanent_rejection_retains_body_and_checkpoint_without_repeated_sends(tmp_path):
    box, batch, now = queued(tmp_path)
    sender = Sender(box.collector_id, DeliveryOutcome("quarantined", code="HTTP_REJECTED"))
    delivery = Delivery(box, sender, clock=lambda: now)
    assert delivery.run_once().state == "quarantined"
    assert delivery.run_once().state == "idle"
    assert box.status().quarantined_count == 1
    assert box.status().retained_bytes == len(batch.model_dump_json().encode())
    assert box.checkpoint("stream").revision == 1 and len(sender.claims) == 1


def test_malformed_success_does_not_acknowledge_retained_work(tmp_path):
    box, _, now = queued(tmp_path)
    sender = Sender(box.collector_id, DeliveryOutcome("retry", code="INVALID_RECEIPT"))
    assert Delivery(box, sender, clock=lambda: now).run_once().state == "retry"
    assert box.status().pending_count == 1


def test_shutdown_during_send_ignores_late_success_and_leaves_reclaimable_work(tmp_path):
    box, batch, now = queued(tmp_path)

    class ClosingSender(Sender):
        def send(self, claim):
            delivery.close()
            return DeliveryOutcome("accepted", duplicate=False)

    sender = ClosingSender(box.collector_id)
    delivery = Delivery(box, sender, clock=lambda: now)
    assert delivery.run_once().state == "stopped"
    assert delivery.run_once().state == "stopped"
    reclaimed = box.claim(now + timedelta(seconds=60))
    assert reclaimed is not None and reclaimed.batch_id == batch.batch_id


def test_old_auth_rejection_cannot_suspend_after_explicit_credential_refresh(tmp_path):
    box, _, now = queued(tmp_path)
    current = Sender(box.collector_id, DeliveryOutcome("accepted", duplicate=False))

    class OldSender(Sender):
        def send(self, claim):
            delivery.refresh_credentials(current)
            return DeliveryOutcome("suspended", code="AUTH_REQUIRED")

    delivery = Delivery(box, OldSender(box.collector_id), clock=lambda: now)
    assert delivery.run_once().state == "stale"
    assert not box.auth_suspended() and box.status().pending_count == 1


def test_retry_backoff_caps_and_does_not_claim_before_due_time(tmp_path):
    box, _, now = queued(tmp_path)
    clock = [now]
    sender = Sender(box.collector_id, *[DeliveryOutcome("retry", code="NETWORK")] * 12)
    delivery = Delivery(box, sender, clock=lambda: clock[0], randomness=lambda: 0)
    for delay in [1, 2, 4, 8, 16, 32, 64, 128, 256, 300, 300, 300]:
        assert delivery.run_once().state == "retry"
        clock[0] += timedelta(seconds=delay - 0.01)
        assert delivery.run_once().state == "idle"
        clock[0] += timedelta(seconds=0.01)
    assert len(sender.claims) == 12 and box.status().pending_count == 1
    assert len({claim.body for claim in sender.claims}) == 1


@pytest.mark.parametrize("jitter,delay", [(0, 1), (1, 2), (100, 2), (-1, 1), (float("nan"), 1)])
def test_retry_jitter_is_bounded(tmp_path, jitter, delay):
    box, _, now = queued(tmp_path)
    clock = [now]
    sender = Sender(box.collector_id, DeliveryOutcome("retry", code="NETWORK"))
    delivery = Delivery(box, sender, clock=lambda: clock[0], randomness=lambda: jitter)
    assert delivery.run_once().state == "retry"
    assert box.claim(now + timedelta(seconds=delay - 0.01)) is None
    assert box.claim(now + timedelta(seconds=delay)) is not None


def test_retry_after_respected_without_advancing_checkpoint(tmp_path):
    box, _, now = queued(tmp_path)
    sender = Sender(
        box.collector_id, DeliveryOutcome("retry", code="RATE_LIMITED", retry_after=200)
    )
    assert (
        Delivery(box, sender, clock=lambda: now, randomness=lambda: 0).run_once().state == "retry"
    )
    assert box.claim(now + timedelta(seconds=199)) is None
    assert box.claim(now + timedelta(seconds=200)) is not None
    assert box.checkpoint("stream").revision == 1


def test_expired_lease_success_cannot_remove_new_claim(tmp_path):
    box, batch, now = queued(tmp_path)
    replacement = []

    class SlowSender(Sender):
        def send(self, claim):
            replacement.append(box.claim(now + timedelta(seconds=60)))
            return DeliveryOutcome("accepted", duplicate=False)

    assert (
        Delivery(box, SlowSender(box.collector_id), clock=lambda: now).run_once().state == "stale"
    )
    assert box.status().pending_count == 1
    assert replacement[0].batch_id == batch.batch_id and box.acknowledge(replacement[0])


def test_network_callback_can_commit_an_independent_stream(tmp_path):
    box, batch, now = queued(tmp_path)
    second = batch.model_copy(update={"batch_id": str(uuid4())})

    class WritingSender(Sender):
        def send(self, claim):
            box.enqueue("heartbeat", second, "independent", 0, {"cursor": 2})
            return DeliveryOutcome("accepted", duplicate=False)

    assert (
        Delivery(box, WritingSender(box.collector_id), clock=lambda: now).run_once().state
        == "accepted"
    )
    assert box.status().pending_count == 1 and box.checkpoint("independent").revision == 1


def test_refresh_in_another_controller_disables_old_sender(tmp_path):
    box, _, now = queued(tmp_path)
    old_sender = Sender(box.collector_id)
    old = Delivery(box, old_sender, clock=lambda: now)
    new_sender = Sender(box.collector_id, DeliveryOutcome("accepted", duplicate=False))
    current = Delivery(Outbox(box.path, box.collector_id), new_sender, clock=lambda: now)
    current.refresh_credentials(new_sender)
    assert old.run_once().state == "suspended" and not old_sender.claims
    assert current.run_once().state == "accepted"


def test_sender_exception_never_echoes_credentials_or_acknowledges(tmp_path):
    box, _, now = queued(tmp_path)

    class BrokenSender(Sender):
        def send(self, claim):
            raise RuntimeError("synthetic-private-credential")

    result = Delivery(box, BrokenSender(box.collector_id), clock=lambda: now).run_once()
    assert result.state == "retry" and result.code == "NETWORK"
    assert "synthetic-private" not in repr(result) and box.status().pending_count == 1
