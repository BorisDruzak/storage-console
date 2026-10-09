"""Small Win32 SCM binding. No shell, service wrapper, registry or state writes."""

from __future__ import annotations

import ctypes
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .errors import SecurityError
from .scm import RECOVERY, ServiceSpec, ServiceStatus

D = ctypes.c_uint32
P = ctypes.c_void_p
W = ctypes.c_wchar_p


class Status(ctypes.Structure):
    _fields_ = [(name, D) for name in (
        "kind", "state", "controls", "exit", "specific", "checkpoint", "hint", "pid", "flags",
    )]


class Config(ctypes.Structure):
    _fields_ = [("kind", D), ("start", D), ("error", D), ("command", W),
                ("group", W), ("tag", D), ("dependencies", W), ("account", W), ("display", W)]


class Action(ctypes.Structure):
    _fields_ = [("kind", D), ("delay", D)]


class Recovery(ctypes.Structure):
    _fields_ = [("reset", D), ("reboot", W), ("command", W), ("count", D),
                ("actions", ctypes.POINTER(Action))]


def api() -> Any:
    if os.name != "nt":
        raise SecurityError("PLATFORM_UNSUPPORTED")
    dll = vars(ctypes)["WinDLL"]("advapi32", use_last_error=True)
    signatures = {
        "OpenSCManagerW": ([W, W, D], P),
        "OpenServiceW": ([P, W, D], P),
        "CloseServiceHandle": ([P], D),
        "CreateServiceW": ([P, W, W, D, D, D, D, W, W, P, W, W, W], P),
        "ChangeServiceConfig2W": ([P, D, P], D),
        "QueryServiceConfigW": ([P, P, D, ctypes.POINTER(D)], D),
        "QueryServiceConfig2W": ([P, D, P, D, ctypes.POINTER(D)], D),
        "QueryServiceStatusEx": ([P, D, P, D, ctypes.POINTER(D)], D),
        "StartServiceW": ([P, D, P], D),
        "ControlService": ([P, D, P], D),
        "DeleteService": ([P], D),
        "RegisterServiceCtrlHandlerExW": ([W, P, P], P),
        "SetServiceStatus": ([P, P], D),
        "StartServiceCtrlDispatcherW": ([P], D),
        "RegisterEventSourceW": ([W, W], P),
        "ReportEventW": ([P, ctypes.c_uint16, ctypes.c_uint16, D, P,
                          ctypes.c_uint16, D, P, P], D),
        "DeregisterEventSource": ([P], D),
    }
    for name, (args, result) in signatures.items():
        function = getattr(dll, name)
        function.argtypes, function.restype = args, result
    return dll


def last_error() -> int:
    return int(vars(ctypes)["get_last_error"]())


def check(result: object) -> None:
    if not result:
        error = last_error()
        codes = {5: "SERVICE_ACCESS_DENIED", 1072: "SERVICE_REMOVING",
                 1060: "SERVICE_NOT_INSTALLED",
                 1058: "SERVICE_DISABLED", 1063: "SERVICE_DISPATCH_REQUIRED"}
        raise SecurityError(codes.get(error, "SCM_FAILED"))


class NativeBackend:
    def __init__(self) -> None:
        self.api = api()

    @contextmanager
    def _manager(self, access: int = 1) -> Iterator[int]:
        handle = self.api.OpenSCManagerW(None, None, access)
        check(handle)
        try:
            yield int(handle)
        finally:
            self.api.CloseServiceHandle(handle)

    @contextmanager
    def _service(self, spec: ServiceSpec, access: int) -> Iterator[int | None]:
        with self._manager() as manager:
            handle = self.api.OpenServiceW(manager, spec.name, access)
            if not handle and last_error() == 1060:
                yield None
                return
            check(handle)
            try:
                yield int(handle)
            finally:
                self.api.CloseServiceHandle(handle)

    def _config_buffer(self, handle: int, level: int | None = None) -> Any:
        # SCM documents an 8 KiB maximum. The fixed bound also rejects bad counts.
        buffer = ctypes.create_string_buffer(8192)
        needed = D()
        result = (
            self.api.QueryServiceConfigW(handle, buffer, len(buffer), ctypes.byref(needed))
            if level is None else self.api.QueryServiceConfig2W(
                handle, level, buffer, len(buffer), ctypes.byref(needed),
            )
        )
        check(result)
        return buffer

    def query(self, spec: ServiceSpec) -> ServiceStatus | None:
        with self._service(spec, 1 | 4) as handle:
            if handle is None:
                return None
            config_buffer = self._config_buffer(handle)
            config = Config.from_buffer(config_buffer)
            delayed = D.from_buffer(self._config_buffer(handle, 3)).value
            recovery_buffer = self._config_buffer(handle, 2)
            recovery = Recovery.from_buffer(recovery_buffer)
            if recovery.count > 64:
                raise SecurityError("SERVICE_CONFLICT")
            actions = tuple((int(recovery.actions[i].kind), int(recovery.actions[i].delay))
                            for i in range(recovery.count))
            flag = D.from_buffer(self._config_buffer(handle, 4)).value
            status, needed = Status(), D()
            check(self.api.QueryServiceStatusEx(
                handle, 0, ctypes.byref(status), ctypes.sizeof(status), ctypes.byref(needed),
            ))
            states = {1: "STOPPED", 2: "START_PENDING", 3: "STOP_PENDING", 4: "RUNNING",
                      5: "CONTINUE_PENDING", 6: "PAUSE_PENDING", 7: "PAUSED"}
            return ServiceStatus(
                states.get(status.state, "UNKNOWN"), config.command or "", int(config.start),
                config.account or "", int(config.kind), int(status.pid), int(status.exit),
                bool(delayed), actions, int(recovery.reset), bool(flag), recovery.command or "",
            )

    def create(self, spec: ServiceSpec) -> None:
        with self._manager(1 | 2) as manager:
            handle = self.api.CreateServiceW(
                manager, spec.name, "Storage Console Collector", 0xF01FF, 0x10, 2, 1,
                spec.command, None, None, None, None, None,
            )
            if not handle and last_error() == 1073:
                return  # Manager re-queries and validates a concurrent registration.
            check(handle)
            try:
                delayed = D(1)
                check(self.api.ChangeServiceConfig2W(handle, 3, ctypes.byref(delayed)))
                actions = (Action * len(RECOVERY))(*(Action(*item) for item in RECOVERY))
                recovery = Recovery(86400, None, None, len(actions), actions)
                check(self.api.ChangeServiceConfig2W(handle, 2, ctypes.byref(recovery)))
                flag = D(0)
                check(self.api.ChangeServiceConfig2W(handle, 4, ctypes.byref(flag)))
            except Exception:
                self.api.DeleteService(handle)  # Only the registration created by this call.
                raise
            finally:
                self.api.CloseServiceHandle(handle)

    def configure_recovery(self, spec: ServiceSpec) -> None:
        with self._service(spec, 2) as handle:
            if handle is None:
                raise SecurityError("SERVICE_NOT_INSTALLED")
            actions = (Action * len(RECOVERY))(*(Action(*item) for item in RECOVERY))
            recovery = Recovery(86400, None, None, len(actions), actions)
            check(self.api.ChangeServiceConfig2W(handle, 2, ctypes.byref(recovery)))

    def start(self, spec: ServiceSpec) -> None:
        with self._service(spec, 0x10) as handle:
            if handle is None:
                raise SecurityError("SERVICE_NOT_INSTALLED")
            result = self.api.StartServiceW(handle, 0, None)
            if not result and last_error() == 1056:
                return
            check(result)

    def stop(self, spec: ServiceSpec) -> None:
        with self._service(spec, 0x20) as handle:
            if handle is None:
                raise SecurityError("SERVICE_NOT_INSTALLED")
            status = Status()
            result = self.api.ControlService(handle, 1, ctypes.byref(status))
            if not result and last_error() == 1062:
                return
            check(result)

    def delete(self, spec: ServiceSpec) -> None:
        with self._service(spec, 0x10000 | 0x20 | 4) as handle:
            if handle is not None:
                check(self.api.DeleteService(handle))
                deadline = time.monotonic() + 150
                stop_sent = False
                while True:
                    status, needed = Status(), D()
                    check(self.api.QueryServiceStatusEx(
                        handle, 0, ctypes.byref(status), ctypes.sizeof(status),
                        ctypes.byref(needed),
                    ))
                    if status.state == 1:
                        return
                    if time.monotonic() >= deadline:
                        raise SecurityError("SERVICE_STOP_TIMEOUT")
                    if status.state == 4 and not stop_sent:
                        result = self.api.ControlService(handle, 1, ctypes.byref(Status()))
                        if not result and last_error() != 1062:
                            check(result)
                        stop_sent = True
                    time.sleep(0.2)
