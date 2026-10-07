"""Owned isolated capture worker: private stdin, bounded summary stdout and stop."""

import ctypes
import json
import os
import subprocess
import sys
import threading
from dataclasses import asdict
from pathlib import Path

from .configuration import Loaded, _unique
from .inventory import CODES, CaptureError
from .producer import CaptureReport
from .security import _api


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_int64),
        ("job_time", ctypes.c_int64),
        ("flags", ctypes.c_uint32),
        ("minimum", ctypes.c_size_t),
        ("maximum", ctypes.c_size_t),
        ("processes", ctypes.c_uint32),
        ("affinity", ctypes.c_size_t),
        ("priority", ctypes.c_uint32),
        ("scheduling", ctypes.c_uint32),
    ]


class _JobLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits),
        ("io", ctypes.c_uint64 * 6),
        ("memory", ctypes.c_size_t * 4),
    ]


class _Job:
    def __init__(self) -> None:
        self._api = _api()
        kernel = self._api.kernel
        pointer = ctypes.c_void_p
        self._api.bind(kernel, "CreateJobObjectW", [pointer, ctypes.c_wchar_p], pointer)
        self._api.bind(
            kernel,
            "SetInformationJobObject",
            [pointer, ctypes.c_int, pointer, ctypes.c_uint32],
            ctypes.c_int32,
        )
        self._api.bind(kernel, "AssignProcessToJobObject", [pointer, pointer], ctypes.c_int32)
        self._handle = kernel.CreateJobObjectW(None, None)
        if not self._handle:
            raise CaptureError("NATIVE_FAILED")
        limits = _JobLimits()
        # Windows venv python.exe can be a redirector plus the actual interpreter.
        limits.basic.flags = 0x2008  # KILL_ON_JOB_CLOSE and bounded owned descendants.
        limits.basic.processes = 2
        if not kernel.SetInformationJobObject(
            self._handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            self.close()
            raise CaptureError("NATIVE_FAILED")

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        if not self._api.kernel.AssignProcessToJobObject(self._handle, vars(process)["_handle"]):
            raise CaptureError("NATIVE_FAILED")

    def close(self) -> None:
        if self._handle:
            self._api.kernel.CloseHandle(self._handle)
            self._handle = None


class CaptureProcess:
    def __init__(self, loaded: Loaded, *, python: Path | None = None) -> None:
        if os.name != "nt":
            raise CaptureError("PLATFORM_UNSUPPORTED")
        executable = Path(python or sys.executable).absolute()
        payload = (
            json.dumps(
                {
                    "state": str(loaded.outbox.path.parent),
                    "collector_id": str(loaded.outbox.collector_id),
                    "credential_version": str(loaded.config.credential_version),
                    "roots": list(loaded.config.scope.roots),
                    "settings": loaded.config.settings.model_dump(mode="json"),
                }
            ).encode("utf-8")
            + b"\n"
        )
        if len(payload) > 131072:
            raise CaptureError("METADATA_INVALID")
        self._cancel = threading.Event()
        self._output = b""
        self._io_failed = False
        self._report: CaptureReport | None = None
        self._job = _Job()
        try:
            self._process = subprocess.Popen(
                [str(executable), "-I", "-m", "collectors.windows._capture_worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=executable.parent,
                creationflags=0x08000000,
            )
        except OSError:
            self._job.close()
            raise CaptureError("NATIVE_FAILED") from None
        try:
            # Worker cannot collect until it receives stdin, after job assignment.
            self._job.assign(self._process)
        except CaptureError:
            self._process.kill()
            self._process.wait(timeout=2)
            self._job.close()
            raise

        def write() -> None:
            assert self._process.stdin is not None
            try:
                self._process.stdin.write(payload)
                self._process.stdin.flush()
                self._cancel.wait()
                self._process.stdin.write(b"STOP\n")
                self._process.stdin.flush()
            except (OSError, ValueError):
                self._io_failed = True
            finally:
                try:
                    self._process.stdin.close()
                except OSError:
                    pass

        def read() -> None:
            assert self._process.stdout is not None
            try:
                self._output = self._process.stdout.read(4097)
                if len(self._output) > 4096:
                    self._io_failed = True
                    self._process.kill()
            except (OSError, ValueError):
                self._io_failed = True
            finally:
                self._process.stdout.close()

        self._writer = threading.Thread(target=write, name="capture-input", daemon=False)
        self._reader = threading.Thread(target=read, name="capture-output", daemon=False)
        self._reader.start()
        self._writer.start()

    @staticmethod
    def decode(raw: bytes) -> CaptureReport:
        try:
            if not 1 <= len(raw) <= 4096:
                raise ValueError
            value = json.loads(raw, object_pairs_hook=_unique)
            if not isinstance(value, dict) or set(value) != {
                "records",
                "batches",
                "completed",
                "errors",
            }:
                raise ValueError
            if any(
                type(value[key]) is not int or not 0 <= value[key] < 2**63
                for key in ("records", "batches")
            ):
                raise ValueError
            errors = value["errors"]
            if type(value["completed"]) is not bool or not isinstance(errors, list):
                raise ValueError
            if len(errors) > len(CODES) or any(
                not isinstance(code, str) or code not in CODES for code in errors
            ):
                raise ValueError
            if len(set(errors)) != len(errors) or (value["completed"] and errors):
                raise ValueError
            return CaptureReport(
                value["records"], value["batches"], value["completed"], tuple(errors)
            )
        except (ValueError, TypeError, UnicodeError):
            return CaptureReport(0, 0, False, ("NATIVE_FAILED",))

    def _finish(self, *, stopped: bool = False) -> CaptureReport:
        self._job.close()
        self._cancel.set()
        self._writer.join(1)
        self._reader.join(1)
        if self._writer.is_alive() or self._reader.is_alive():
            raise CaptureError("NATIVE_FAILED")
        if stopped:
            self._report = CaptureReport(0, 0, False, ("STOPPED",))
        elif self._process.returncode != 0 or len(self._output) > 4096:
            self._report = CaptureReport(0, 0, False, ("NATIVE_FAILED",))
        else:
            self._report = self.decode(self._output)
        return self._report

    def poll(self) -> CaptureReport | None:
        if self._report is not None:
            return self._report
        if self._process.poll() is None:
            return None
        return self._finish()

    def stop(self, grace: float) -> CaptureReport:
        if self._report is not None:
            return self._report
        self._cancel.set()
        try:
            self._process.wait(timeout=max(0, grace))
        except subprocess.TimeoutExpired:
            self._process.kill()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                raise CaptureError("NATIVE_FAILED") from None
        return self._finish(stopped=True)

    @staticmethod
    def encode(report: CaptureReport) -> bytes:
        return json.dumps(asdict(report), separators=(",", ":")).encode("ascii")
