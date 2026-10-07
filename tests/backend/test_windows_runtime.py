import json
import threading
import time
from uuid import uuid4

from collectors.common.outbox import Outbox
from collectors.common.transport import DeliveryOutcome
from collectors.windows.configuration import Loaded, PrivateConfig, RuntimeSettings
from collectors.windows.producer import CaptureReport
from collectors.windows.runtime import Runtime


class Sender:
    def __init__(self, collector_id):
        self.collector_id = collector_id
        self.records = []

    def send(self, claim):
        self.records.extend(json.loads(claim.body)["records"])
        return DeliveryOutcome("accepted", duplicate=False)


def prepared(tmp_path):
    box = Outbox(tmp_path / "private" / "queue", uuid4())
    settings = RuntimeSettings(heartbeat_seconds=1, inventory_seconds=1, poll_seconds=0.05)
    config = PrivateConfig(
        collector_id=box.collector_id,
        credential_version=uuid4(),
        origin="https://localhost",
        roots=("C:\\synthetic",),
        encrypted_token="synthetic",
        settings=settings,
    )
    return Loaded(config, box, Sender(box.collector_id))


def test_heartbeat_delivery_is_independent_of_a_blocked_inventory(tmp_path):
    loaded = prepared(tmp_path)
    scans = []

    class Capture:
        def poll(self):
            return None

        def stop(self, grace):
            scans.append("stopped")
            return CaptureReport(0, 0, False, ("STOPPED",))

    def start():
        scans.append("started")
        return Capture()

    runtime = Runtime(loaded, capture_factory=start)
    stop = threading.Event()
    thread = threading.Thread(target=runtime.run, args=(stop,))
    thread.start()
    try:
        deadline = time.monotonic() + 4
        while len(loaded.transport.records) < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert len(loaded.transport.records) >= 2
        assert scans == ["started"]
    finally:
        stop.set()
        thread.join(2)
    assert not thread.is_alive() and scans == ["started", "stopped"]


def test_inventory_error_stays_in_heartbeats_until_completed_recovery(tmp_path):
    loaded = prepared(tmp_path)
    attempts = []

    class Capture:
        def __init__(self, report):
            self.report = report

        def poll(self):
            return self.report

        def stop(self, grace):
            return self.report

    def start():
        attempts.append(True)
        return Capture(
            CaptureReport(1, 1, len(attempts) > 1, () if len(attempts) > 1 else ("ACCESS_DENIED",))
        )

    runtime = Runtime(loaded, capture_factory=start)
    stop = threading.Event()
    thread = threading.Thread(target=runtime.run, args=(stop,))
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            records = list(loaded.transport.records)
            errors = [record.get("error_code") for record in records]
            if "ACCESS_DENIED" in errors and errors[-1] is None and len(attempts) > 1:
                break
            time.sleep(0.05)
        assert "ACCESS_DENIED" in errors and errors[-1] is None
    finally:
        stop.set()
        thread.join(2)
    assert not thread.is_alive()
