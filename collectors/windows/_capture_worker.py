"""Installed isolated capture child. Never receives credentials or prints evidence."""

import ctypes
import json
import os
import sys
import threading
import time
from io import BufferedReader, RawIOBase
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from collectors.common.outbox import Outbox, OutboxError

from .capture_process import CaptureProcess
from .configuration import RuntimeSettings, _unique
from .errors import SecurityError
from .inventory import CODES, CaptureError, Scope
from .native import NativeInventory
from .producer import CaptureReport, capture_inventory
from .security import ProtectedState, _api
from .usn_capture import capture_usn


class _Request(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    state: str = Field(repr=False, min_length=1, max_length=32700)
    collector_id: UUID
    credential_version: UUID = Field(repr=False)
    roots: tuple[str, ...] = Field(repr=False, min_length=1, max_length=32)
    settings: RuntimeSettings
    mode: Literal["inventory", "usn"] = "inventory"


_STARTUP_RETRY_SECONDS = 30


def _open_outbox(state: ProtectedState, request: _Request, stopped: threading.Event) -> Outbox:
    # This bounds starting another retry, not an in-flight SQLite constructor:
    # its existing per-statement busy timeout can finish after this deadline.
    # Parent process/Job shutdown remains the hard cancellation boundary.
    deadline = time.monotonic() + _STARTUP_RETRY_SECONDS
    delay = 0.05
    last: OutboxError | None = None
    while True:
        if stopped.is_set():
            raise CaptureError("STOPPED")
        if time.monotonic() >= deadline:
            raise last or OutboxError("STATE_UNAVAILABLE", sqlite_errorcode=5)
        try:
            state.validate_file("outbox.sqlite3")
            box = Outbox(
                state.root / "outbox.sqlite3", request.collector_id, request.settings.limits()
            )
            if stopped.is_set():
                raise CaptureError("STOPPED")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise last or OutboxError("STATE_UNAVAILABLE", sqlite_errorcode=5)
            with box.busy_budget(remaining):
                binding = box.credential_binding()
            if binding != request.credential_version:
                raise CaptureError("STATE_MISMATCH")
            if stopped.is_set():
                raise CaptureError("STOPPED")
            return box
        except OutboxError as error:
            if not error.retryable:
                raise
            last = error
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            if stopped.wait(min(delay, remaining)):
                raise CaptureError("STOPPED") from None
            delay = min(delay * 2, 1)


def main() -> int:
    report = CaptureReport(0, 0, False, ("METADATA_INVALID",))
    try:
        # Raw readline cannot prefetch the subsequent STOP command into a buffered reader.
        raw = cast(RawIOBase, cast(BufferedReader, sys.stdin.buffer).raw).readline(131073)
        if not raw.endswith(b"\n") or len(raw) > 131072:
            raise ValueError
        json.loads(raw, object_pairs_hook=_unique)
        request = _Request.model_validate_json(raw)
        scope = Scope(request.roots)
    except (ValueError, TypeError, ValidationError, CaptureError, OutboxError):
        pass
    else:
        stopped = threading.Event()
        finished = threading.Event()
        control_thread: threading.Thread | None = None

        def control() -> None:
            try:
                api = _api()
                api.bind(api.kernel, "GetStdHandle", [ctypes.c_uint32], ctypes.c_void_p)
                api.bind(
                    api.kernel,
                    "PeekNamedPipe",
                    [
                        ctypes.c_void_p,
                        ctypes.c_void_p,
                        ctypes.c_uint32,
                        ctypes.c_void_p,
                        ctypes.POINTER(ctypes.c_uint32),
                        ctypes.c_void_p,
                    ],
                    ctypes.c_int32,
                )
                handle = api.kernel.GetStdHandle(0xFFFFFFF6)
                while not finished.is_set():
                    available = ctypes.c_uint32()
                    if not api.kernel.PeekNamedPipe(
                        handle, None, 0, None, ctypes.byref(available), None
                    ):
                        stopped.set()
                        return
                    if available.value:
                        os.read(sys.stdin.fileno(), min(16, available.value))
                        stopped.set()
                        return
                    finished.wait(0.05)
            except Exception:
                stopped.set()

        try:
            with ProtectedState(Path(request.state), _child=True) as state:
                control_thread = threading.Thread(
                    target=control, name="capture-control", daemon=False
                )
                control_thread.start()
                box = _open_outbox(state, request, stopped)
                if stopped.is_set():
                    raise CaptureError("STOPPED")
                if request.mode == "usn":
                    report = capture_usn(box, scope, stopped=stopped.is_set)
                else:
                    report = capture_inventory(
                    box,
                    scope,
                    NativeInventory().scan(scope),
                    max_records=request.settings.batch_records,
                    stopped=stopped.is_set,
                    capacity_wait_seconds=request.settings.capacity_wait_seconds,
                    wait=stopped.wait,
                    )
        except CaptureError as error:
            report = CaptureReport(
                0, 0, False, (error.code if error.code in CODES else "NATIVE_FAILED",)
            )
        except (SecurityError, OutboxError):
            report = CaptureReport(0, 0, False, ("STATE_MISMATCH",))
        except Exception:
            report = CaptureReport(0, 0, False, ("NATIVE_FAILED",))
        finally:
            finished.set()
            if control_thread is not None:
                control_thread.join(1)
                if control_thread.is_alive():
                    report = CaptureReport(0, 0, False, ("NATIVE_FAILED",))
    try:
        sys.stdout.buffer.write(CaptureProcess.encode(report))
        sys.stdout.buffer.flush()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
