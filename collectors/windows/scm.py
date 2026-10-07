"""Bounded SCM operations; registration identity is checked before every mutation."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PureWindowsPath
from typing import Protocol

from .errors import SecurityError

SERVICE_NAME = "SosnadminStorageCollector"


def _path(value: str) -> str:
    path = PureWindowsPath(value)
    if (
        not path.is_absolute() or len(path.drive) != 2 or path.drive[1] != ":"
        or len(path.parts) < 2 or ".." in path.parts
        or any(character in value for character in '\"\r\n\x00')
        or value.endswith(("\\", " ", "."))
    ):
        raise SecurityError("SERVICE_PATH_INVALID")
    return str(path)


@dataclass(frozen=True)
class ServiceSpec:
    executable: str
    state_path: str
    name: str = SERVICE_NAME

    def __post_init__(self) -> None:
        object.__setattr__(self, "executable", _path(self.executable))
        object.__setattr__(self, "state_path", _path(self.state_path))
        # Alternate names are limited to owned disposable acceptance services.
        if self.name != SERVICE_NAME and not (
            self.name.startswith(SERVICE_NAME + "Test")
            and self.name.isascii() and self.name.isalnum() and len(self.name) <= 96
        ):
            raise SecurityError("SERVICE_NAME_INVALID")

    @property
    def command(self) -> str:
        # Always quote both paths; no credential or mutable operator argument.
        return (f'"{self.executable}" -I -m collectors.windows.service '
                f'--name {self.name} --state "{self.state_path}"')

    @classmethod
    def registered(cls, executable: str, command: str) -> ServiceSpec:
        prefix = (f'"{_path(executable)}" -I -m collectors.windows.service '
                  f'--name {SERVICE_NAME} --state "')
        if not command.startswith(prefix) or not command.endswith('"'):
            raise SecurityError("SERVICE_CONFLICT")
        try:
            spec = cls(executable, command[len(prefix):-1])
        except SecurityError:
            raise SecurityError("SERVICE_CONFLICT") from None
        if spec.command != command:
            raise SecurityError("SERVICE_CONFLICT")
        return spec


@dataclass(frozen=True)
class ServiceStatus:
    state: str
    command: str
    start_type: int
    account: str
    service_type: int
    pid: int
    exit_code: int
    delayed: bool
    recovery: tuple[tuple[int, int], ...]
    recovery_reset_seconds: int
    recover_non_crash: bool
    failure_command: str = ""


class Backend(Protocol):
    def query(self, spec: ServiceSpec) -> ServiceStatus | None: ...
    def create(self, spec: ServiceSpec) -> None: ...
    def start(self, spec: ServiceSpec) -> None: ...
    def stop(self, spec: ServiceSpec) -> None: ...
    def delete(self, spec: ServiceSpec) -> None: ...


class ServiceManager:
    def __init__(
        self, spec: ServiceSpec, backend: Backend, *, timeout: float = 150,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 0 < timeout <= 180:
            raise SecurityError("INVALID_SETTINGS")
        self.spec, self.backend = spec, backend
        self.timeout, self.monotonic, self.sleep = timeout, monotonic, sleep

    def status(self) -> ServiceStatus | None:
        status = self.backend.query(self.spec)
        if status is not None and (
            status.command != self.spec.command or status.account.casefold() != "localsystem"
            or status.service_type != 0x10 or status.start_type not in {2, 4}
            or not status.delayed or status.recovery != ((1, 10000), (0, 0))
            or status.recovery_reset_seconds != 86400 or status.recover_non_crash
            or status.failure_command
        ):
            raise SecurityError("SERVICE_CONFLICT")
        return status

    def _required(self) -> ServiceStatus:
        status = self.status()
        if status is None:
            raise SecurityError("SERVICE_NOT_INSTALLED")
        return status

    def install(self) -> ServiceStatus:
        status = self.status()
        if status is None:
            self.backend.create(self.spec)
            status = self._required()
        return status

    def _wait(self, target: str, pending: str, code: str) -> ServiceStatus:
        status = self._required()
        if status.state == target:
            return status
        deadline = self.monotonic() + self.timeout
        while status.state == pending:
            if self.monotonic() >= deadline:
                raise SecurityError(code + "_TIMEOUT")
            self.sleep(0.2)
            status = self._required()
            if status.state == target:
                return status
        raise SecurityError(code + "_FAILED")

    def start(self) -> ServiceStatus:
        status = self._required()
        if status.start_type == 4:
            raise SecurityError("SERVICE_DISABLED")
        if status.state == "RUNNING":
            return status
        if status.state == "STOPPED":
            self.backend.start(self.spec)
        elif status.state != "START_PENDING":
            raise SecurityError("SERVICE_TRANSITION_BUSY")
        return self._wait("RUNNING", "START_PENDING", "SERVICE_START")

    def stop(self) -> ServiceStatus:
        status = self._required()
        if status.state == "STOPPED":
            if status.exit_code == 1067:
                # SCM can still have a queued restart. A STOP control cannot
                # cancel it; never promise a stable operator stop in this state.
                raise SecurityError("SERVICE_RECOVERY_PENDING")
            return status
        if status.state == "RUNNING":
            self.backend.stop(self.spec)
        elif status.state != "STOP_PENDING":
            raise SecurityError("SERVICE_TRANSITION_BUSY")
        return self._wait("STOPPED", "STOP_PENDING", "SERVICE_STOP")

    def uninstall(self) -> None:
        status = self.status()
        if status is not None:
            if status.state != "STOPPED":
                self.stop()
            # Deleting the registration cancels a pending crash restart. The
            # native backend retains its handle and drains any concurrent start.
            self.backend.delete(self.spec)
