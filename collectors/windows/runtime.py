"""Independent heartbeat, bounded inventory/USN children and delivery thread."""

import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Protocol, TypeVar

from collectors.common.delivery import Delivery
from collectors.common.outbox import OutboxError

from .configuration import Loaded
from .diagnostics import RuntimeFailure, detail
from .errors import SecurityError
from .inventory import CODES, CaptureError
from .producer import CaptureReport, capture_heartbeat

_T = TypeVar("_T")


class _Stopped(Exception):
    pass


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
        usn_factory: Callable[[], Capture] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        diagnostic: Callable[[str], None] = lambda value: None,
    ) -> None:
        self._loaded = loaded
        self._settings = loaded.config.settings
        self._heartbeat_seconds = (
            min(self._settings.heartbeat_seconds, 5)
            if loaded.usn_enabled else self._settings.heartbeat_seconds
        )
        self._capture_factory = capture_factory
        self._usn_factory = usn_factory
        self._monotonic = monotonic
        self._diagnostic = diagnostic
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

    def _state_call(self, stop: threading.Event, action: Callable[[], _T], stage: str) -> _T:
        deadline = self._monotonic() + 30
        delay = 0.1
        reported = False
        last: OutboxError | None = None
        while not stop.is_set():
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise last or OutboxError("STATE_UNAVAILABLE", sqlite_errorcode=5)
            try:
                with self._loaded.outbox.busy_budget(remaining):
                    return action()
            except OutboxError as error:
                if not error.retryable:
                    raise
                if not reported:
                    self._diagnostic(detail(error, stage))
                    self._record(RuntimeEvent(stage, "STATE_BUSY"))
                    reported = True
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    raise
                last = error
                stop.wait(min(delay, remaining))
                delay = min(delay * 2, 2)
        raise _Stopped

    def run(self, stop: threading.Event) -> None:
        if not self._run_lock.acquire(blocking=False):
            raise SecurityError("STATE_BUSY")
        capture: Capture | None = None
        usn: Capture | None = None
        failure = threading.Event()
        failures: list[RuntimeFailure] = []
        thread: threading.Thread | None = None

        def deliver() -> None:
            try:
                while not stop.is_set():
                    result = self._state_call(stop, self._delivery.run_once, "delivery")
                    if result.state != "idle":
                        self._record(RuntimeEvent("delivery", result.code))
                    if result.state != "accepted":
                        stop.wait(self._settings.poll_seconds)
            except _Stopped:
                return
            except Exception as error:
                self._record(RuntimeEvent("delivery", "NATIVE_FAILED"))
                failed = RuntimeFailure("RUNTIME_FAILED", error, "delivery")
                failures.append(failed)
                self._diagnostic(failed.detail)
                failure.set()

        try:
            next_heartbeat = next_inventory = self._monotonic()
            next_usn = next_heartbeat
            usn_started = next_usn
            last_usn: float | None = None
            usn_proof: int | None = None
            error: str | None = None
            usn_error: str | None = "USN_BOOTSTRAP" if self._loaded.usn_enabled else None
            thread = threading.Thread(target=deliver, name="collector-delivery", daemon=False)
            thread.start()
            while not stop.is_set() and not failure.is_set():
                now = self._monotonic()
                if usn is not None:
                    report = usn.poll()
                    if report is not None:
                        usn = None
                        usn_error = (None if report.completed and not report.errors else
                                     report.errors[0] if report.errors and report.errors[0] in CODES
                                     else "USN_UNAVAILABLE")
                        if usn_error is None:
                            # A slow pass cannot make an old journal target look
                            # freshly observed merely because it finally exits.
                            last_usn = usn_started
                            usn_proof = int((datetime.now(UTC).timestamp()-(now-last_usn))*1000)
                        self._record(RuntimeEvent("usn", usn_error, report.records, report.batches))
                        next_usn = now + 2
                    elif now-usn_started >= (600 if last_usn is None else 30):
                        report = usn.stop(self._settings.child_stop_seconds)
                        usn = None
                        usn_error = "USN_STALE"
                        self._record(RuntimeEvent("usn", usn_error, report.records, report.batches))
                        next_usn = now + 2
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
                    progress_stale = last_usn is not None and now-last_usn >= 15
                    uncertain = usn_error or ("USN_STALE" if progress_stale else None) or error
                    if self._state_call(
                        stop, self._loaded.outbox.status, "heartbeat",
                    ).quarantined_count:
                        uncertain = uncertain or "STATE_MISMATCH"
                    try:
                        cursor = None
                        if self._loaded.usn_enabled:
                            continuity = (
                                "gap" if usn_error == "CONTINUITY_GAP" else
                                "unknown" if usn_error or progress_stale else "continuous"
                            )
                            cursor = ("ntfs-usn:" + continuity + ":"
                                      + str(usn_proof or 0) + ":"
                                      + self._loaded.config.scope.fingerprint)
                        self._state_call(stop, partial(capture_heartbeat,
                            self._loaded.outbox, error_code=uncertain, cursor=cursor,
                        ), "heartbeat")
                        self._record(RuntimeEvent("heartbeat", uncertain))
                    except CaptureError as caught:
                        self._record(RuntimeEvent("heartbeat", caught.code))
                    next_heartbeat = self._monotonic() + self._heartbeat_seconds
                if capture is None and now >= next_inventory:
                    try:
                        capture = self._start_capture()
                    except Exception as caught:
                        self._diagnostic(detail(caught, "inventory"))
                        error = "NATIVE_FAILED"
                        self._record(RuntimeEvent("inventory", error))
                        next_inventory = now + self._settings.inventory_seconds
                if self._loaded.usn_enabled and usn is None and now >= next_usn:
                    try:
                        if self._usn_factory is not None:
                            usn = self._usn_factory()
                        else:
                            from .capture_process import CaptureProcess

                            usn = CaptureProcess(self._loaded, mode="usn")
                        usn_started = self._monotonic()
                    except Exception as caught:
                        self._diagnostic(detail(caught, "usn"))
                        usn_error = "USN_UNAVAILABLE"
                        self._record(RuntimeEvent("usn", usn_error))
                        next_usn = now + 2
                stop.wait(self._settings.poll_seconds)
            if failures:
                raise failures[0]
        except _Stopped:
            pass
        except (OutboxError, CaptureError) as caught:
            self._diagnostic(detail(caught, "heartbeat"))
            raise RuntimeFailure("STATE_INVALID", caught, "heartbeat") from None
        finally:
            primary = sys.exception()
            deadline = self._monotonic() + self._settings.stop_seconds
            stop.set()
            try:
                try:
                    self._delivery.close()
                    try:
                        if capture is not None:
                            report = capture.stop(self._settings.child_stop_seconds)
                            self._record(
                                RuntimeEvent("inventory", "STOPPED", report.records, report.batches)
                            )
                    finally:
                        if usn is not None:
                            report = usn.stop(max(0, min(self._settings.child_stop_seconds,
                                                       deadline - self._monotonic())))
                            self._record(RuntimeEvent(
                                "usn", "STOPPED", report.records, report.batches,
                            ))
                finally:
                    if thread is not None:
                        thread.join(max(0, deadline - self._monotonic()))
                        if thread.is_alive():
                            raise SecurityError("STOP_TIMEOUT")
            except Exception as caught:
                self._diagnostic(detail(caught, "cleanup"))
                if primary is None:
                    code = (caught.code if isinstance(caught, (SecurityError, CaptureError))
                            else "RUNTIME_FAILED")
                    raise RuntimeFailure(code, caught, "cleanup") from None
            finally:
                self._run_lock.release()
