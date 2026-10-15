"""A completed request must not be forgotten while its local lease settlement is busy."""

import sqlite3
from dataclasses import replace
from datetime import timedelta

import pytest
from test_collector_delivery import Sender, queued

from collectors.common.delivery import Delivery
from collectors.common.outbox import OutboxError
from collectors.common.transport import DeliveryOutcome


def test_accepted_request_finishes_after_real_local_writer_contention(tmp_path):
    box, batch, now = queued(tmp_path)
    box.limits = replace(box.limits, busy_timeout_seconds=1)
    writer = sqlite3.connect(box.path, autocommit=True)

    class AcceptThenLock(Sender):
        def send(self, claim):
            self.claims.append(claim)
            writer.execute("BEGIN EXCLUSIVE")
            return DeliveryOutcome("accepted", duplicate=False)

    sender = AcceptThenLock(box.collector_id)
    delivery = Delivery(box, sender, clock=lambda: now)
    try:
        with pytest.raises(OutboxError) as failure:
            delivery.run_once()
        assert failure.value.retryable
        writer.execute("ROLLBACK")
        # Time does not advance to lease expiry; retry only the local result.
        assert delivery.run_once().state == "accepted"
        assert len(sender.claims) == 1
        assert sender.claims[0].body == batch.model_dump_json().encode()
        assert box.status().pending_count == 0
        assert box.checkpoint("stream").revision == 1
        assert box.claim(now + timedelta(seconds=60)) is None
    finally:
        writer.close()


@pytest.mark.parametrize(
    "operation,outcome,state",
    [
        ("acknowledge", DeliveryOutcome("accepted", duplicate=False), "accepted"),
        ("suspend_auth", DeliveryOutcome("suspended", code="AUTH_REQUIRED"), "suspended"),
        ("quarantine", DeliveryOutcome("quarantined", code="HTTP_REJECTED"), "quarantined"),
        ("retry", DeliveryOutcome("retry", code="RATE_LIMITED", retry_after=20), "retry"),
    ],
)
def test_settlement_retries_real_writer_contention_without_resending(
    tmp_path, monkeypatch, operation, outcome, state
):
    box, _, now = queued(tmp_path)
    box.limits = replace(box.limits, busy_timeout_seconds=1)
    writer = sqlite3.connect(box.path, autocommit=True)
    sender = Sender(box.collector_id, outcome)
    clock = [now]
    random_calls = []

    def jitter():
        random_calls.append(True)
        return 1

    delivery = Delivery(box, sender, clock=lambda: clock[0], randomness=jitter)
    settle = getattr(box, operation)
    attempts = []

    def contend(*args):
        attempts.append(args)
        writer.execute("BEGIN IMMEDIATE")
        try:
            return settle(*args)
        finally:
            writer.execute("ROLLBACK")

    monkeypatch.setattr(box, operation, contend)
    try:
        for _ in range(2):
            with pytest.raises(OutboxError) as failure:
                delivery.run_once()
            assert failure.value.retryable
            clock[0] += timedelta(seconds=5)
        monkeypatch.setattr(box, operation, settle)
        assert delivery.run_once().state == state
        assert len(sender.claims) == 1
        assert attempts[0] == attempts[1]
        assert box.checkpoint("stream").revision == 1
        if state == "retry":
            assert random_calls == [True]
            assert box.claim(now + timedelta(seconds=19)) is None
            retry = box.claim(now + timedelta(seconds=20))
            assert retry is not None and retry.attempts == 1
        elif state == "accepted":
            assert box.status().pending_count == 0
        elif state == "suspended":
            assert box.auth_suspended() and box.status().pending_count == 1
        else:
            assert box.status().quarantined_count == 1
    finally:
        writer.close()


@pytest.mark.parametrize("disposition", ["close", "refresh", "other_refresh", "reclaim"])
def test_pending_response_respects_close_generation_and_lease_fences(
    tmp_path, monkeypatch, disposition
):
    box, batch, now = queued(tmp_path)
    sender = Sender(box.collector_id, DeliveryOutcome("accepted", duplicate=False))
    delivery = Delivery(box, sender, clock=lambda: now)
    acknowledge = box.acknowledge

    def busy(claim):
        raise OutboxError("STATE_BUSY", sqlite_errorcode=5)

    monkeypatch.setattr(box, "acknowledge", busy)
    with pytest.raises(OutboxError):
        delivery.run_once()
    monkeypatch.setattr(box, "acknowledge", acknowledge)
    replacement = None
    if disposition == "close":
        delivery.close()
        expected = "stopped"
    elif disposition in ("refresh", "other_refresh"):
        current = delivery if disposition == "refresh" else Delivery(box, sender)
        current.refresh_credentials(sender)
        expected = "idle" if disposition == "refresh" else "stale"
    else:
        replacement = box.claim(now + timedelta(seconds=60))
        assert replacement is not None
        expected = "stale"
    assert delivery.run_once().state == expected
    assert len(sender.claims) == 1 and box.status().pending_count == 1
    if replacement is None:
        replacement = box.claim(now + timedelta(seconds=60))
    assert replacement is not None and replacement.body == batch.model_dump_json().encode()
    assert box.acknowledge(replacement)


def test_concurrent_calls_reserve_one_slot_before_network_send(tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    box, batch, now = queued(tmp_path)
    box.enqueue("heartbeat", batch.model_copy(update={"batch_id": "second"}), "other", 0, {})
    started, release = threading.Event(), threading.Event()

    class BlockingSender(Sender):
        def send(self, claim):
            self.claims.append(claim)
            started.set()
            assert release.wait(5)
            return DeliveryOutcome("accepted", duplicate=False)

    sender = BlockingSender(box.collector_id)
    delivery = Delivery(box, sender, clock=lambda: now)
    with ThreadPoolExecutor(max_workers=1) as pool:
        request = pool.submit(delivery.run_once)
        try:
            assert started.wait(5)
            assert delivery.run_once().state == "idle"
            assert len(sender.claims) == 1
        finally:
            release.set()
        assert request.result(timeout=5).state == "accepted"
    assert box.status().pending_count == 1


def test_nonretryable_state_error_propagates_without_network_replay(tmp_path, monkeypatch):
    box, _, now = queued(tmp_path)
    sender = Sender(box.collector_id, DeliveryOutcome("accepted", duplicate=False))
    delivery = Delivery(box, sender, clock=lambda: now)
    acknowledge = box.acknowledge

    def fatal(claim):
        raise OutboxError("INVALID_CODE")

    monkeypatch.setattr(box, "acknowledge", fatal)
    with pytest.raises(OutboxError) as failure:
        delivery.run_once()
    assert not failure.value.retryable
    monkeypatch.setattr(box, "acknowledge", acknowledge)
    assert delivery.run_once().state == "accepted"
    assert len(sender.claims) == 1
