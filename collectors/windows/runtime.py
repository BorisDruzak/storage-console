"""Independent heartbeat, one capture child and one bounded delivery thread."""

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from collectors.common.delivery import Delivery
from collectors.common.outbox import OutboxError

from .configuration import Loaded
from .errors import SecurityError
from .inventory import CODES, CaptureError
from .producer import CaptureReport, capture_heartbeat


class Capture(Protocol):
    def poll(self) -> CaptureReport | None: ...

    def stop(self, grace: float) -> CaptureReport: ...


@dataclass(frozen=True)
class RuntimeEvent:
    kind: str
    code: str | None = None
    records: int = 0
    batches: int = 0


class Runtime:
    def __init__(
        self,
        loaded: Loaded,
        *,
        capture_factory: Callable[[], Capture] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._loaded = loaded
        self._settings = loaded.config.settings
        self._capture_factory = capture_factory
        self._monotonic = monotonic
        self._events: deque[RuntimeEvent] = deque(maxlen=64)
        self._event_lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._delivery = Delivery(
            loaded.outbox,
            loaded.transport,
            prefer_heartbeat=True,
            heartbeat_burst=self._settings.heartbeat_burst,
        )

    @property
    def events(self) -> tuple[RuntimeEvent, ...]:
        with self._event_lock:
            return tuple(self._events)

    def _record(self, event: RuntimeEvent) -> None:
        with self._event_lock:
            self._events.append(event)

    def _start_capture(self) -> Capture:
        if self._capture_factory is not None:
            return self._capture_factory()
        # Runtime imports remain portable; the owned worker is started only on demand.
        from .capture_process import CaptureProcess

        return CaptureProcess(self._loaded)

    def run(self, stop: threading.Event) -> None:
        if not self._run_lock.acquire(blocking=False):
            raise SecurityError("STATE_BUSY")
        capture: Capture | None = None
        failure = threading.Event()
        thread: threading.Thread | None = None

        def deliver() -> None:
            try:
                while not stop.is_set():
                    result = self._delivery.run_once()
                    if result.state != "idle":
                        self._record(RuntimeEvent("delivery", result.code))
                    if result.state != "accepted":
                        stop.wait(self._settings.poll_seconds)
            except Exception:
                self._record(RuntimeEvent("delivery", "NATIVE_FAILED"))
                failure.set()

        try:
            next_heartbeat = next_inventory = self._monotonic()
            error: str | None = None
            thread = threading.Thread(target=deliver, name="collector-delivery", daemon=False)
            thread.start()
            while not stop.is_set() and not failure.is_set():
                now = self._monotonic()
                if capture is not None:
                    report = capture.poll()
                    if report is not None:
                        capture = None
                        error = (
                            None
                            if report.completed and not report.errors
                            else (
                                report.errors[0]
                                if report.errors and report.errors[0] in CODES
                                else "NATIVE_FAILED"
                            )
                        )
                        self._record(
                            RuntimeEvent("inventory", error, report.records, report.batches)
                        )
                        next_inventory = now + self._settings.inventory_seconds
                if now >= next_heartbeat:
                    uncertain = error
                    if self._loaded.outbox.status().quarantined_count:
                        uncertain = uncertain or "STATE_MISMATCH"
                    try:
                        capture_heartbeat(self._loaded.outbox, error_code=uncertain)
                        self._record(RuntimeEvent("heartbeat", uncertain))
                    except CaptureError as caught:
                        self._record(RuntimeEvent("heartbeat", caught.code))
                    next_heartbeat = self._monotonic() + self._settings.heartbeat_seconds
                if capture is None and now >= next_inventory:
                    try:
                        capture = self._start_capture()
                    except Exception:
                        error = "NATIVE_FAILED"
                        self._record(RuntimeEvent("inventory", error))
                        next_inventory = now + self._settings.inventory_seconds
                stop.wait(self._settings.poll_seconds)
        except (OutboxError, CaptureError):
            raise SecurityError("STATE_INVALID") from None
        finally:
            deadline = self._monotonic() + self._settings.stop_seconds
            stop.set()
            self._delivery.close()
            try:
                if capture is not None:
                    report = capture.stop(self._settings.child_stop_seconds)
                    self._record(
                        RuntimeEvent("inventory", "STOPPED", report.records, report.batches)
                    )
            finally:
                try:
                    if thread is not None:
                        thread.join(max(0, deadline - self._monotonic()))
                        if thread.is_alive():
                            raise SecurityError("STOP_TIMEOUT")
                finally:
                    self._run_lock.release()
