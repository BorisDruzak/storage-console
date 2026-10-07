"""SCM host for the existing collector runtime, with separate operator-stop intent."""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path

from .errors import SecurityError
from .scm import ServiceSpec


class RuntimeHost:
    def __init__(
        self, prepare: Callable[[threading.Event], Callable[[threading.Event], object]],
        report: Callable[..., None], log: Callable[[str], None],
    ) -> None:
        self.prepare, self.report, self.log = prepare, report, log
        self.stop = threading.Event()
        self.requested_stop = threading.Event()
        self._lock = threading.RLock()
        self._state = "START_PENDING"

    def _report(self, state: str, code: int = 0) -> None:
        with self._lock:
            self._state = state
            if code:
                self.report(state, code)
            else:
                self.report(state)

    def control(self, control: int) -> int:
        # HandlerEx must return promptly; Runtime performs its own bounded cleanup.
        with self._lock:
            if control in {1, 5}:
                self.requested_stop.set()
                self.stop.set()
                if self._state != "STOPPED":
                    self._report("STOP_PENDING")
                return 0
            if control == 4:  # INTERROGATE
                if self._state != "STOPPED":
                    self._report(self._state)
                return 0
            return 120  # ERROR_CALL_NOT_IMPLEMENTED

    def run(self) -> int:
        running = False
        try:
            self._report("START_PENDING")
            runtime = self.prepare(self.stop)
            with self._lock:
                if not self.requested_stop.is_set():
                    self._report("RUNNING")
                    running = True
            runtime(self.stop)
            if not self.requested_stop.is_set():
                raise SecurityError("RUNTIME_FAILED")
            self._report("STOPPED")
            return 0
        except Exception as error:
            code = error.code if isinstance(error, SecurityError) else "RUNTIME_FAILED"
            self.log(code)
            # Failed initialization is fail-closed. Unexpected RUNNING termination
            # must leave SCM without STOPPED so the one crash recovery can apply.
            if not running or self.requested_stop.is_set():
                self._report("STOPPED", 1066)
            return 1


def dispatch(spec: ServiceSpec) -> int:
    from ._scm_native import D, P, Status, W, api, check
    from .configuration import load
    from .runtime import Runtime
    from .security import ProtectedState

    native = api()
    factory = vars(ctypes)["WINFUNCTYPE"]
    main_type = factory(None, D, P)
    control_type = factory(D, D, D, P, P)

    class Entry(ctypes.Structure):
        _fields_ = [("name", W), ("main", P)]

    class Dispatcher:
        def __init__(self) -> None:
            self.handle: int | None = None
            self.lock = threading.RLock()
            self.status = Status(kind=0x10)
            self.deadline = time.monotonic() + 30
            self.stop_seconds = 125.0
            self.finished = threading.Event()
            self.result = 1
            self.host = RuntimeHost(self.prepare, self.report, self.log)

        def log(self, code: str) -> None:
            # Static machine codes only. Never exception text, identity, path or token.
            safe = code if code.isascii() and all(c.isupper() or c == "_" for c in code) else (
                "RUNTIME_FAILED"
            )
            handle = native.RegisterEventSourceW(None, spec.name)
            if handle:
                strings = (W * 1)(safe)
                try:
                    native.ReportEventW(handle, 1, 0, 1, None, 1, 0, strings, None)
                finally:
                    native.DeregisterEventSource(handle)

        def prepare(self, stop: threading.Event) -> Callable[[threading.Event], object]:
            stack = ExitStack()
            try:
                state = stack.enter_context(ProtectedState(Path(spec.state_path)))
                state.validate_file("outbox.sqlite3")
                loaded = load(state)
                self.stop_seconds = loaded.config.settings.stop_seconds + 3
                runtime = Runtime(loaded)
            except Exception:
                stack.close()
                raise
            def run(event: threading.Event) -> None:
                try:
                    runtime.run(event)
                finally:
                    stack.close()
            return run

        def report(self, state: str, code: int = 0) -> None:
            states = {"STOPPED": 1, "START_PENDING": 2, "STOP_PENDING": 3, "RUNNING": 4}
            with self.lock:
                target = states[state]
                if self.status.state != target:
                    self.status.checkpoint = 0
                    self.deadline = time.monotonic() + (
                        self.stop_seconds if target == 3 else 30
                    )
                self.status.state = target
                self.status.exit = code
                self.status.specific = int(bool(code))
                self.status.controls = 1 | 4 if target == 4 else 0
                self.status.hint = 5000 if target in {2, 3} else 0
                self.status.checkpoint = self.status.checkpoint + 1 if target in {2, 3} else 0
                check(native.SetServiceStatus(self.handle, ctypes.byref(self.status)))

        def watch(self) -> None:
            while not self.finished.wait(2):
                with self.lock:
                    if self.status.state not in {2, 3}:
                        continue
                    if time.monotonic() >= self.deadline:
                        self.log("SERVICE_STOP_TIMEOUT" if self.status.state == 3 else (
                            "SERVICE_START_TIMEOUT"
                        ))
                        self.report("STOPPED", 1066)
                        # Own-process service only; Job Object closes all capture children.
                        os._exit(1)
                    self.status.checkpoint += 1
                    check(native.SetServiceStatus(self.handle, ctypes.byref(self.status)))

        def watch_safe(self) -> None:
            try:
                self.watch()
            except BaseException:
                # A failed watchdog must not leave an unbounded stop or print
                # an exception from a privileged background thread.
                self.log("SCM_FAILED")
                try:
                    self.report("STOPPED", 1066)
                except BaseException:
                    pass
                os._exit(1)

        def control(self, control: int, event: int, data: int, context: int) -> int:
            try:
                return self.host.control(control)
            except BaseException:
                self.log("SCM_FAILED")
                self.host.requested_stop.set()
                self.host.stop.set()
                return 1

        def main(self, count: int, arguments: int) -> None:
            watcher: threading.Thread | None = None
            try:
                handle = native.RegisterServiceCtrlHandlerExW(spec.name, control_callback, None)
                check(handle)
                self.handle = int(handle)
                watcher = threading.Thread(
                    target=self.watch_safe, name="collector-scm-status", daemon=True,
                )
                watcher.start()
                self.result = self.host.run()
                if self.result:
                    # A failed cleanup may leave a non-daemon delivery thread.
                    # Terminate this own-process host instead of waiting forever.
                    # Reported STOPPED prevents recovery for explicit stop/startup
                    # failure; an unexpected exit without STOPPED recovers once.
                    os._exit(1)
            except BaseException:
                self.log("SCM_FAILED")
                if self.handle:
                    try:
                        if self.status.state != 4 or self.host.requested_stop.is_set():
                            self.report("STOPPED", 1066)
                    except BaseException:
                        pass
                os._exit(1)
            finally:
                self.finished.set()
                if watcher:
                    watcher.join(3)

    dispatcher = Dispatcher()
    # Keep strong references through the blocking dispatcher. Foreign SCM threads
    # invoke these callbacks; no Python exception may cross either ABI boundary.
    control_callback = control_type(dispatcher.control)
    main_callback = main_type(dispatcher.main)
    entries = (Entry * 2)(Entry(spec.name, ctypes.cast(main_callback, P)), Entry(None, None))
    check(native.StartServiceCtrlDispatcherW(entries))
    return dispatcher.result


def main() -> int:
    from .cli import ArgumentsError, Parser
    parser = Parser(prog="storage-collector-service")
    parser.add_argument("--name", required=True)
    parser.add_argument("--state", required=True)
    try:
        args = parser.parse_args()
        return dispatch(ServiceSpec(sys.executable, args.state, args.name))
    except (ArgumentsError, SecurityError, OSError, ValueError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
