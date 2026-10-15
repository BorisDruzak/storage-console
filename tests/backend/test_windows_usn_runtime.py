import json
import sqlite3
import threading
import time
from contextlib import closing
from dataclasses import replace
from datetime import datetime

import pytest
from test_windows_runtime import Sender, prepared
from windows_capture_diagnostics import readonly_observer, runtime_snapshot, safe_failure

from collectors.common.outbox import OutboxError
from collectors.windows.diagnostics import valid_detail
from collectors.windows.inventory import CaptureError
from collectors.windows.producer import CaptureReport
from collectors.windows.runtime import Runtime


def test_blocked_usn_keeps_heartbeat_inventory_and_shutdown_independent(tmp_path):
    loaded = replace(prepared(tmp_path), usn_enabled=True)
    children = []
    observer = readonly_observer(loaded)
    usn_polled = threading.Event()
    clock_lock = threading.Lock()
    now = 0

    def clock():
        with clock_lock:
            return now

    class Capture:
        def __init__(self, kind):
            self.kind = kind
            children.append((kind, "start"))

        def poll(self):
            if self.kind == "usn":
                usn_polled.set()
            return CaptureReport(1, 1, True, ()) if self.kind == "inventory" else None

        def stop(self, grace):
            children.append((self.kind, "stop"))
            return CaptureReport(0, 0, False, ("STOPPED",))

    runtime = Runtime(loaded, capture_factory=lambda: Capture("inventory"),
                      usn_factory=lambda: Capture("usn"), monotonic=clock)
    stop = threading.Event()
    failures = []

    def run():
        try:
            runtime.run(stop)
        except Exception as error:
            failures.append(safe_failure(error))

    def wait_for_phase(count):
        # Wall time is only fixture emergency protection. Advance scheduling
        # explicitly after durable ACK, rather than asserting a disk-speed SLA.
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline and not failures:
            try:
                with observer._transaction() as connection:
                    acked = connection.execute(
                        "SELECT count(*) FROM receipts r LEFT JOIN batches b "
                        "ON b.batch_id=r.batch_id WHERE r.domain='heartbeat' "
                        "AND b.batch_id IS NULL"
                    ).fetchone()[0]
            except OutboxError as error:
                if not error.retryable:
                    raise
                acked = 0
            completed = sum(e.kind == "inventory" and e.code is None for e in runtime.events)
            if acked >= count and completed >= count and usn_polled.is_set():
                return
            time.sleep(0.05)
        diagnostic = runtime_snapshot(runtime, loaded.outbox.path, failures)
        print("NATIVE_RUNTIME_DIAGNOSTIC " + json.dumps(diagnostic), flush=True)
        pytest.fail("runtime independence phase did not complete: " + str(diagnostic))

    thread = threading.Thread(target=run)
    thread.start()
    try:
        wait_for_phase(1)
        with clock_lock:
            now = loaded.config.settings.heartbeat_seconds
        wait_for_phase(2)
        assert len(loaded.transport.records) >= 2
        assert children.count(("inventory", "start")) >= 2
        assert children.count(("usn", "start")) == 1
        assert all(row["error_code"] == "USN_BOOTSTRAP" for row in loaded.transport.records)
        assert all(row["cursor"].startswith("ntfs-usn:unknown:")
                   for row in loaded.transport.records)
    finally:
        stop.set()
        thread.join(loaded.config.settings.stop_seconds + 5)
    assert not thread.is_alive() and not failures
    assert children.count(("usn", "stop")) == 1
    assert runtime._run_lock.acquire(blocking=False)
    runtime._run_lock.release()


def test_completed_inventory_does_not_clear_usn_gap(tmp_path):
    loaded = replace(prepared(tmp_path), usn_enabled=True)
    sending = threading.Event()
    release_ack = threading.Event()

    class DelayedAck(Sender):
        def send(self, claim):
            outcome = super().send(claim)
            sending.set()
            assert release_ack.wait(10), "test did not release transport ACK"
            return outcome

    loaded = replace(loaded, transport=DelayedAck(loaded.outbox.collector_id))

    class Capture:
        def __init__(self, report):
            self.report = report

        def poll(self):
            return self.report

        def stop(self, grace):
            return self.report

    runtime = Runtime(loaded,
                      capture_factory=lambda: Capture(CaptureReport(1, 1, True, ())),
                      usn_factory=lambda: Capture(CaptureReport(0, 0, False,
                                                                ("CONTINUITY_GAP",))))
    stop = threading.Event()
    failures = []

    def run():
        try:
            runtime.run(stop)
        except Exception as error:
            failures.append(safe_failure(error))

    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert sending.wait(4), runtime_snapshot(runtime, loaded.outbox.path, failures)
        deadline = time.monotonic() + 4
        rows = []
        inventory_completed = False
        while time.monotonic() < deadline:
            # GAP retention is a durable producer property, independent of ACK
            # latency. Read without claiming, acknowledging or locking writers.
            with closing(sqlite3.connect(loaded.outbox.path.as_uri() + "?mode=ro",
                                         uri=True, timeout=0.1)) as observer:
                observer.execute("PRAGMA query_only=ON")
                bodies = observer.execute(
                    "SELECT body FROM batches WHERE domain='heartbeat' AND state='pending' "
                    "ORDER BY seq DESC LIMIT 1"
                ).fetchall()
            rows = [row for (body,) in bodies for row in json.loads(body)["records"]]
            inventory_completed = any(event.kind == "inventory" and event.code is None
                                      for event in runtime.events)
            if inventory_completed and rows and rows[-1].get("error_code") == "CONTINUITY_GAP":
                break
            time.sleep(0.05)
        assert (inventory_completed and rows
                and rows[-1]["error_code"] == "CONTINUITY_GAP"), runtime_snapshot(
            runtime, loaded.outbox.path, failures,
        )
        assert rows[-1]["cursor"].startswith("ntfs-usn:gap:")
        assert loaded.transport.records[0]["error_code"] == "USN_BOOTSTRAP"
    finally:
        release_ack.set()
        stop.set()
        thread.join(2)
    assert not thread.is_alive() and not failures


def test_inventory_stop_failure_still_closes_usn_and_releases_runtime(tmp_path):
    from collectors.windows.diagnostics import RuntimeFailure
    loaded = replace(prepared(tmp_path), usn_enabled=True)
    calls, failures = [], []
    details = []

    class Capture:
        def __init__(self, kind):
            self.kind = kind
            calls.append("start:" + kind)

        def poll(self):
            return None

        def stop(self, grace):
            calls.append("stop:" + self.kind)
            if self.kind == "inventory":
                raise CaptureError("NATIVE_FAILED")
            return CaptureReport(0, 0, False, ("STOPPED",))

    runtime = Runtime(loaded, capture_factory=lambda: Capture("inventory"),
                      usn_factory=lambda: Capture("usn"))
    stop = threading.Event()

    def run():
        try:
            runtime.run(stop)
        except RuntimeFailure as error:
            failures.append(error.code)
            details.append(error.detail)

    thread = threading.Thread(target=run)
    thread.start()
    try:
        deadline = time.monotonic() + 2
        while "start:usn" not in calls and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        stop.set()
        thread.join(2)
    assert not thread.is_alive()
    assert calls[-2:] == ["stop:inventory", "stop:usn"]
    assert failures == ["NATIVE_FAILED"]
    assert json.loads(details[0])["stage"] == "cleanup"
    assert json.loads(details[0])["exception"] == "CaptureError"
    assert runtime._run_lock.acquire(blocking=False)
    runtime._run_lock.release()


def test_success_then_blocked_usn_never_keeps_fresh_heartbeat_continuous(tmp_path):
    loaded = replace(prepared(tmp_path), usn_enabled=True)
    attempts = []
    started = time.monotonic()

    class Capture:
        def __init__(self, completed):
            self.completed = completed

        def poll(self):
            return CaptureReport(0, 0, True, ()) if self.completed else None

        def stop(self, grace):
            return CaptureReport(0, 0, False, ("STOPPED",))

    def usn():
        attempts.append(True)
        return Capture(len(attempts) == 1)

    runtime = Runtime(loaded, capture_factory=lambda: Capture(True), usn_factory=usn,
                      monotonic=lambda: (time.monotonic()-started)*100)
    stop = threading.Event()
    failures = []

    def run():
        try:
            runtime.run(stop)
        except Exception as error:
            failures.append(safe_failure(error))

    thread = threading.Thread(target=run)
    thread.start()
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            rows = list(loaded.transport.records)
            if len(attempts)>1 and any(row.get("error_code") == "USN_STALE" for row in rows):
                break
            time.sleep(0.01)
        assert any(row.get("error_code") == "USN_STALE" for row in rows), runtime_snapshot(
            runtime, loaded.outbox.path, failures,
        )
        assert rows[-1]["cursor"].startswith("ntfs-usn:unknown:")
    finally:
        stop.set()
        thread.join(2)
    assert not thread.is_alive() and not failures


def test_default_thirty_second_config_publishes_usn_proof_before_it_expires(tmp_path):
    loaded = prepared(tmp_path)
    config = loaded.config.model_copy(update={"settings": loaded.config.settings.model_copy(
        update={"heartbeat_seconds":30})})
    loaded = replace(loaded, config=config, usn_enabled=True)
    class Capture:
        def poll(self):
            return CaptureReport(0, 0, True, ())

        def stop(self, grace):
            return CaptureReport(0, 0, False, ("STOPPED",))

    clock = [0.0]
    failures = []
    diagnostics = []
    runtime = Runtime(loaded, capture_factory=Capture, usn_factory=Capture,
                      monotonic=lambda: clock[0], diagnostic=diagnostics.append)
    stop = threading.Event()

    def snapshot():
        value = {
            "runtime": runtime_snapshot(runtime, loaded.outbox.path, failures),
            "diagnostics": [json.loads(entry) for entry in diagnostics if valid_detail(entry)],
        }
        print("USN_RUNTIME_DIAGNOSTIC " + json.dumps(value), flush=True)
        return value

    def run():
        try:
            runtime.run(stop)
        except Exception as error:
            failures.append(safe_failure(error))

    thread = threading.Thread(target=run)
    thread.start()
    try:
        def received(count):
            deadline = time.monotonic() + 5
            while (len(loaded.transport.records) < count
                   and time.monotonic() < deadline and not failures):
                time.sleep(0.01)
            assert len(loaded.transport.records) >= count, snapshot()

        def completed_usn(count):
            deadline = time.monotonic() + 5
            while (sum(e.kind == "usn" and e.code is None for e in runtime.events) < count
                   and not failures):
                assert time.monotonic() < deadline, snapshot()
                time.sleep(0.01)
            assert not failures, snapshot()

        received(1)
        completed_usn(1)
        for value, count in ((5.0, 2), (10.0, 3)):
            clock[0] = value
            received(count)
            assert loaded.transport.records[-1]["cursor"].startswith("ntfs-usn:continuous:")
            row = loaded.transport.records[-1]
            proof = int(row["cursor"].split(":")[2]) / 1000
            observed = datetime.fromisoformat(row["occurred_at"].replace("Z", "+00:00")).timestamp()
            assert 0 <= observed - proof < 15
            # Delivery precedes scheduling; wait for the following capture to finish.
            completed_usn(count)
        assert loaded.config.settings.heartbeat_seconds == 30
    finally:
        stop.set()
        thread.join(2)
    assert not thread.is_alive() and not failures, snapshot()
