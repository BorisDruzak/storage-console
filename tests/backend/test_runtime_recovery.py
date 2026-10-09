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


def test_runtime_survives_writer_lock_and_resumes_delivery(tmp_path):
    loaded = prepared(tmp_path)
    loaded.outbox.limits = replace(loaded.outbox.limits, busy_timeout_seconds=1)
    runtime = Runtime(loaded, capture_factory=lambda: BlockedCapture())
    failures = []
    host = RuntimeHost(lambda stop: runtime.run, lambda *args: None, failures.append)
    worker = threading.Thread(target=host.run)
    worker.start()
    lock = sqlite3.connect(loaded.outbox.path, autocommit=True)
    try:
        deadline = time.monotonic() + 4
        while not loaded.transport.records and time.monotonic() < deadline:
            time.sleep(0.02)
        assert loaded.transport.records
        while loaded.outbox.status().pending_count and time.monotonic() < deadline:
            time.sleep(0.02)
        assert loaded.outbox.status().pending_count == 0
        lock.execute("BEGIN IMMEDIATE")
        time.sleep(2.3)
        assert worker.is_alive(), failures
        lock.execute("ROLLBACK")
        before = len(loaded.transport.records)
        deadline = time.monotonic() + 4
        while len(loaded.transport.records) == before and time.monotonic() < deadline:
            time.sleep(0.02)
        assert len(loaded.transport.records) > before
    finally:
        lock.close()
        host.control(1)
        worker.join(3)
    assert not worker.is_alive()
    assert not failures


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

