"""Regression evidence using real SQLite contention and the service host."""

import json
import sqlite3
import threading
import time
from dataclasses import replace

import pytest
from test_windows_runtime import prepared

from collectors.common.outbox import OutboxError
from collectors.windows.runtime import Runtime
from collectors.windows.service import RuntimeHost


def test_sqlite_busy_retains_numeric_cause_without_private_text(tmp_path):
    loaded = prepared(tmp_path)
    loaded.outbox.limits = replace(loaded.outbox.limits, busy_timeout_seconds=1)
    lock = sqlite3.connect(loaded.outbox.path, autocommit=True)
    try:
        lock.execute("BEGIN IMMEDIATE")
        with pytest.raises(OutboxError) as caught:
            loaded.outbox.status()
        assert getattr(caught.value, "sqlite_errorcode", None) == sqlite3.SQLITE_BUSY
        assert getattr(caught.value, "retryable", False)
        assert str(caught.value) == "STATE_UNAVAILABLE"
    finally:
        lock.close()


@pytest.mark.parametrize("resume_delay", [0, 6])
def test_runtime_survives_writer_lock_and_resumes_delivery(tmp_path, monkeypatch, resume_delay):
    loaded = prepared(tmp_path)
    loaded.outbox.limits = replace(loaded.outbox.limits, busy_timeout_seconds=1)
    busy_seen, resume = threading.Event(), threading.Event()
    sent, acknowledged = [], []
    send = loaded.transport.send
    acknowledge = loaded.outbox.acknowledge

    def observed_send(claim):
        outcome = send(claim)
        if claim.domain == "heartbeat":
            sent.append(claim.batch_id)
        return outcome

    def observed_ack(claim):
        changed = acknowledge(claim)
        if changed:
            acknowledged.append(claim.batch_id)
        return changed

    monkeypatch.setattr(loaded.outbox, "acknowledge", observed_ack)
    monkeypatch.setattr(loaded.transport, "send", observed_send)

    def diagnostic(value):
        if json.loads(value).get("sqlite_errorcode") == sqlite3.SQLITE_BUSY:
            busy_seen.set()
            assert resume.wait(15), "test did not release the retry gate"

    runtime = Runtime(loaded, capture_factory=lambda: BlockedCapture(), diagnostic=diagnostic)
    failures, results = [], []
    host = RuntimeHost(lambda stop: runtime.run, lambda *args: None, failures.append)
    worker = threading.Thread(target=lambda: results.append(host.run()))
    worker.start()
    lock = sqlite3.connect(loaded.outbox.path, autocommit=True)
    release_retry = threading.Timer(resume_delay, resume.set)
    try:
        deadline = time.monotonic() + 35
        while not acknowledged and worker.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert loaded.transport.records and acknowledged, (failures, results, runtime.events)
        lock.execute("BEGIN IMMEDIATE")
        assert busy_seen.wait(10), "real SQLite BUSY was not exercised"
        assert worker.is_alive(), failures
        lock.execute("ROLLBACK")
        before = len(loaded.transport.records)
        sent_before = set(sent)
        released_at = time.monotonic()
        release_retry.start()
        # This is a test guard, not a four-second recovery SLA. The runtime's
        # own 30-second retry deadline and fatal-error policy remain unchanged.
        deadline = released_at + 35
        while (worker.is_alive() and not failures and time.monotonic() < deadline
               and (len(loaded.transport.records) == before
                    or not (set(sent) - sent_before).intersection(acknowledged))):
            time.sleep(0.02)
        evidence = {
            "worker_alive": worker.is_alive(),
            "failures": failures[-2:],
            "host_results": results,
            "sqlite_busy_observed": busy_seen.is_set(),
            "sent_before": before,
            "sent_after": len(loaded.transport.records),
            "new_sent": len(set(sent) - sent_before),
            "new_acked": len((set(sent) - sent_before).intersection(acknowledged)),
            "elapsed_seconds": time.monotonic() - released_at,
            "events": [(event.kind, event.code) for event in runtime.events],
        }
        assert worker.is_alive() and not failures, evidence
        assert len(loaded.transport.records) > before, evidence
        assert (set(sent) - sent_before).intersection(acknowledged), evidence
        assert time.monotonic() < deadline, evidence
    finally:
        resume.set()
        release_retry.cancel()
        if release_retry.ident is not None:
            release_retry.join(1)
        lock.close()
        host.control(1)
        worker.join(3)
    assert not worker.is_alive()
    assert not failures and results == [0]


def test_heartbeat_state_read_preserves_lock_error_for_runtime_retry(tmp_path):
    from collectors.windows.producer import capture_heartbeat
    loaded = prepared(tmp_path)
    loaded.outbox.limits = replace(loaded.outbox.limits, busy_timeout_seconds=1)
    lock = sqlite3.connect(loaded.outbox.path, autocommit=True)
    try:
        lock.execute("BEGIN IMMEDIATE")
        with pytest.raises(OutboxError) as caught:
            capture_heartbeat(loaded.outbox)
        assert caught.value.retryable
    finally:
        lock.close()


def test_inventory_resumes_after_real_exclusive_sqlite_lock(tmp_path, monkeypatch):
    from test_windows_producer import NOW, SCOPE, observations

    from collectors.windows.producer import capture_inventory

    loaded = prepared(tmp_path)
    box = loaded.outbox
    box.limits = replace(box.limits, busy_timeout_seconds=1)
    enqueue = box.enqueue
    writer = sqlite3.connect(box.path, autocommit=True)
    retries = []
    attempts = []

    def enqueue_under_lock(*args):
        if not attempts:
            writer.execute("BEGIN EXCLUSIVE")
        attempts.append(args)
        return enqueue(*args)

    def release_writer(seconds):
        retries.append(seconds)
        writer.execute("ROLLBACK")

    monkeypatch.setattr(box, "enqueue", enqueue_under_lock)
    try:
        report = capture_inventory(box, SCOPE, observations(1), clock=lambda: NOW,
                                   capacity_wait_seconds=3, wait=release_writer)
    finally:
        writer.close()
    assert report.completed and report.records == 2 and report.batches == 1
    assert retries and len(attempts) == 2 and attempts[0] == attempts[1]
    assert box.checkpoint("windows:inventory").revision == 1


class BlockedCapture:
    def poll(self):
        return None

    def stop(self, grace):
        from collectors.windows.producer import CaptureReport
        return CaptureReport(0, 0, False, ("STOPPED",))


def test_host_persists_safe_exception_details():
    failures = []

    def fail(stop):
        raise RuntimeError("synthetic-secret C:\\private\\document.txt")

    host = RuntimeHost(lambda stop: fail, lambda *args: None, failures.append)
    assert host.run() == 1
    assert failures[0] == "RUNTIME_FAILED"
    assert len(failures) == 2
    detail = json.loads(failures[1])
    assert detail["stage"] == "runtime"
    assert detail["exception"] == "RuntimeError"
    assert detail["frames"]
    assert "synthetic-secret" not in failures[1]
    assert "private" not in failures[1]
    assert str(__file__) not in failures[1]


def test_delivery_fatal_error_reaches_service_log(tmp_path, monkeypatch):
    loaded = prepared(tmp_path)
    runtime = Runtime(loaded, capture_factory=lambda: BlockedCapture())

    def fail():
        raise OutboxError("STATE_UNAVAILABLE", sqlite_errorcode=sqlite3.SQLITE_CORRUPT)

    monkeypatch.setattr(runtime._delivery, "run_once", fail)
    failures = []
    host = RuntimeHost(lambda stop: runtime.run, lambda *args: None, failures.append)
    assert host.run() == 1
    detail = json.loads(failures[-1])
    assert detail["stage"] == "delivery"
    assert detail["exception"] == "OutboxError"
    assert detail["sqlite_errorcode"] == sqlite3.SQLITE_CORRUPT


@pytest.mark.parametrize("code,retryable", [(5, True), (6, True), (261, True),
                                            (11, False), (10, False), (13, False), (None, False)])
def test_only_lock_errors_are_retryable(code, retryable):
    assert OutboxError("STATE_UNAVAILABLE", sqlite_errorcode=code).retryable is retryable


def test_state_retry_budget_is_finite(tmp_path):
    ticks = iter([0, 31])
    runtime = Runtime(prepared(tmp_path), monotonic=lambda: next(ticks))

    def fail():
        raise OutboxError("STATE_UNAVAILABLE", sqlite_errorcode=sqlite3.SQLITE_BUSY)

    with pytest.raises(OutboxError):
        runtime._state_call(threading.Event(), fail, "delivery")


def test_no_new_attempt_at_retry_deadline(tmp_path):
    ticks = iter([0, 29.99, 30, 31])
    runtime = Runtime(prepared(tmp_path), monotonic=lambda: next(ticks))
    attempts = []

    def fail():
        attempts.append(True)
        raise OutboxError("STATE_UNAVAILABLE", sqlite_errorcode=sqlite3.SQLITE_BUSY)

    with pytest.raises(OutboxError):
        runtime._state_call(threading.Event(), fail, "delivery")
    assert len(attempts) == 1


def test_sqlite_wait_is_limited_by_remaining_retry_budget(tmp_path):
    loaded = prepared(tmp_path)
    loaded.outbox.limits = replace(loaded.outbox.limits, busy_timeout_seconds=1)
    ticks = iter([0, 29.95, 31])
    runtime = Runtime(loaded, monotonic=lambda: next(ticks))
    lock = sqlite3.connect(loaded.outbox.path, autocommit=True)
    try:
        lock.execute("BEGIN IMMEDIATE")
        started = time.monotonic()
        with pytest.raises(OutboxError):
            runtime._state_call(threading.Event(), loaded.outbox.status, "delivery")
        assert time.monotonic() - started < 0.5
    finally:
        lock.close()


def test_fatal_heartbeat_checkpoint_error_is_not_swallowed(tmp_path, monkeypatch):
    loaded = prepared(tmp_path)
    runtime = Runtime(loaded, capture_factory=lambda: BlockedCapture())

    def fail(stream):
        raise OutboxError("STATE_UNAVAILABLE", sqlite_errorcode=sqlite3.SQLITE_CORRUPT)

    monkeypatch.setattr(loaded.outbox, "checkpoint", fail)
    failures, results = [], []
    host = RuntimeHost(lambda stop: runtime.run, lambda *args: None, failures.append)
    worker = threading.Thread(target=lambda: results.append(host.run()))
    worker.start()
    try:
        worker.join(1)
        assert not worker.is_alive()
        assert results == [1]
        assert json.loads(failures[-1])["sqlite_errorcode"] == sqlite3.SQLITE_CORRUPT
    finally:
        host.control(1)
        worker.join(3)


def test_cleanup_error_does_not_replace_primary_delivery_failure(tmp_path, monkeypatch):
    runtime = Runtime(prepared(tmp_path))
    ready = threading.Event()

    class Capture(BlockedCapture):
        def stop(self, grace):
            raise ValueError("synthetic-private-cleanup")

    def start():
        ready.set()
        return Capture()

    runtime._capture_factory = start

    def fail():
        assert ready.wait(3)
        raise OutboxError("STATE_UNAVAILABLE", sqlite_errorcode=sqlite3.SQLITE_CORRUPT)

    monkeypatch.setattr(runtime._delivery, "run_once", fail)
    failures = []
    host = RuntimeHost(lambda stop: runtime.run, lambda *args: None, failures.append)
    assert host.run() == 1
    detail = json.loads(failures[-1])
    assert detail["stage"] == "delivery"
    assert detail["sqlite_errorcode"] == sqlite3.SQLITE_CORRUPT


def test_stop_interrupts_sqlite_retry_without_runtime_failure(tmp_path):
    loaded = prepared(tmp_path)
    loaded.outbox.limits = replace(loaded.outbox.limits, busy_timeout_seconds=1)
    runtime = Runtime(loaded, capture_factory=lambda: BlockedCapture())
    failures = []
    host = RuntimeHost(lambda stop: runtime.run, lambda *args: None, failures.append)
    lock = sqlite3.connect(loaded.outbox.path, autocommit=True)
    lock.execute("BEGIN IMMEDIATE")
    worker = threading.Thread(target=host.run)
    worker.start()
    try:
        time.sleep(1.2)
        host.control(1)
        worker.join(3)
        assert not worker.is_alive()
        assert not failures
    finally:
        lock.close()
        host.control(1)
        worker.join(3)


def test_install_upgrades_only_the_recognized_legacy_recovery():
    from collectors.windows import scm
    from collectors.windows.scm import ServiceStatus
    spec = scm.ServiceSpec(r'C:\Collector\python.exe', r'C:\state')

    class Backend:
        current = ServiceStatus("STOPPED", spec.command, 2, "LocalSystem", 0x10, 0, 1067,
                                True, ((1, 10000), (0, 0)), 86400, False)

        def query(self, requested):
            return self.current

        def configure_recovery(self, requested):
            self.current = replace(self.current, recovery=((1, 10000), (1, 30000), (1, 60000)))

    backend = Backend()
    status = scm.ServiceManager(spec, backend).install()
    assert status.recovery == ((1, 10000), (1, 30000), (1, 60000))
