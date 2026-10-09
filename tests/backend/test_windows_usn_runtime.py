import json
import threading
import time
from dataclasses import replace

from test_windows_runtime import prepared

from collectors.windows.inventory import CaptureError
from collectors.windows.producer import CaptureReport
from collectors.windows.runtime import Runtime


def test_blocked_usn_keeps_heartbeat_inventory_and_shutdown_independent(tmp_path):
    loaded = replace(prepared(tmp_path), usn_enabled=True)
    children = []

    class Capture:
        def __init__(self, kind):
            self.kind = kind
            children.append((kind, "start"))

        def poll(self):
            return CaptureReport(1, 1, True, ()) if self.kind == "inventory" else None

        def stop(self, grace):
            children.append((self.kind, "stop"))
            return CaptureReport(0, 0, False, ("STOPPED",))

    runtime = Runtime(loaded, capture_factory=lambda: Capture("inventory"),
                      usn_factory=lambda: Capture("usn"))
    stop = threading.Event()
    thread = threading.Thread(target=runtime.run, args=(stop,))
    thread.start()
    try:
        deadline = time.monotonic() + 4
        while len(loaded.transport.records) < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert len(loaded.transport.records) >= 2
        assert children.count(("inventory", "start")) >= 1
        assert children.count(("usn", "start")) == 1
        assert all(row["error_code"] == "USN_BOOTSTRAP" for row in loaded.transport.records)
        assert all(row["cursor"].startswith("ntfs-usn:unknown:")
                   for row in loaded.transport.records)
    finally:
        stop.set()
        thread.join(2)
    assert not thread.is_alive() and ("usn", "stop") in children


def test_completed_inventory_does_not_clear_usn_gap(tmp_path):
    loaded = replace(prepared(tmp_path), usn_enabled=True)

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
    thread = threading.Thread(target=runtime.run, args=(stop,))
    thread.start()
    try:
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            rows = list(loaded.transport.records)
            if rows and rows[-1].get("error_code") == "CONTINUITY_GAP":
                break
            time.sleep(0.05)
        assert rows[-1]["error_code"] == "CONTINUITY_GAP"
        assert rows[-1]["cursor"].startswith("ntfs-usn:gap:")
    finally:
        stop.set()
        thread.join(2)
    assert not thread.is_alive()


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
            failures.append(type(error).__name__)

    thread = threading.Thread(target=run)
    thread.start()
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            rows = list(loaded.transport.records)
            if len(attempts)>1 and any(row.get("error_code") == "USN_STALE" for row in rows):
                break
            time.sleep(0.01)
        assert any(row.get("error_code") == "USN_STALE" for row in rows)
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
    started = time.monotonic()

    class Capture:
        def poll(self):
            return CaptureReport(0, 0, True, ())

        def stop(self, grace):
            return CaptureReport(0, 0, False, ("STOPPED",))

    runtime = Runtime(loaded, capture_factory=Capture, usn_factory=Capture,
                      monotonic=lambda:(time.monotonic()-started)*20)
    stop = threading.Event()
    thread = threading.Thread(target=runtime.run, args=(stop,))
    thread.start()
    try:
        deadline = time.monotonic()+1.2
        while len(loaded.transport.records)<3 and time.monotonic()<deadline:
            time.sleep(0.01)
        assert len(loaded.transport.records)>=3
        assert loaded.transport.records[-1]["cursor"].startswith("ntfs-usn:continuous:")
        assert loaded.config.settings.heartbeat_seconds == 30
    finally:
        stop.set()
        thread.join(2)
    assert not thread.is_alive()
