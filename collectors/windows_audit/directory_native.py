"""Owned bounded platform LDAP/DNS process; no credential or NTLM fallback."""

import json
import os
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Annotated, Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from collectors.windows.capture_process import _Job, _JobLimits
from packages.contracts.directory import DirectoryScope, DirectoryUser, dns_name

from .directory_resolver import Computer, DnsRecord, LookupError, Witnesses

SCRIPT = Path(__file__).with_name("directory_query.ps1")
_ERRORS = {
    "MACHINE_IDENTITY_REQUIRED",
    "DIRECTORY_SCOPE_MISMATCH",
    "LDAP_UNAVAILABLE",
    "DNS_UNAVAILABLE",
    "LOOKUP_LIMIT",
    "DIRECTORY_LIMIT",
    "DIRECTORY_STOPPED",
    "DIRECTORY_PROTOCOL_INVALID",
    "MULTIPLE_MATCHES",
}


class DirectoryError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code if code in _ERRORS else "DIRECTORY_PROTOCOL_INVALID"
        super().__init__(self.code)


class DirectorySettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    scope: DirectoryScope
    ldap_server: Annotated[str, Field(min_length=3, max_length=253, strict=True)]
    refresh_seconds: Annotated[int, Field(ge=900, le=86400, strict=True)] = 900
    page_size: Annotated[int, Field(ge=1, le=256, strict=True)] = 256
    max_objects: Annotated[int, Field(ge=1, le=100000, strict=True)] = 100000
    max_seconds: Annotated[int, Field(ge=1, le=60, strict=True)] = 60

    @model_validator(mode="after")
    def selected_namespace(self) -> Self:
        if not dns_name(self.ldap_server).endswith("." + self.scope.dns_domain):
            raise ValueError("DIRECTORY_SCOPE_MISMATCH")
        return self


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DirectoryError("DIRECTORY_PROTOCOL_INVALID")
        result[key] = value
    return result


def read_frames(stream: IO[bytes]) -> Iterator[dict[str, Any]]:
    total = 0
    for _ in range(513):
        raw = stream.readline(4 * 1024**2 + 1)
        total += len(raw)
        if not raw or len(raw) > 4 * 1024**2 or total > 32 * 1024**2 or not raw.endswith(b"\n"):
            raise DirectoryError("DIRECTORY_PROTOCOL_INVALID")
        try:
            value = json.loads(raw, object_pairs_hook=_unique)
        except (ValueError, UnicodeError):
            raise DirectoryError("DIRECTORY_PROTOCOL_INVALID") from None
        if not isinstance(value, dict):
            raise DirectoryError("DIRECTORY_PROTOCOL_INVALID")
        kind = value.get("type")
        if kind == "error" and set(value) == {"type", "code"} and isinstance(value["code"], str):
            raise DirectoryError(value["code"])
        if kind == "page":
            if (
                set(value) != {"type", "page_index", "records", "finished"}
                or type(value["finished"]) is not bool
                or type(value["page_index"]) is not int
                or not 0 <= value["page_index"] < 512
                or not isinstance(value["records"], list)
                or len(value["records"]) > 256
            ):
                raise DirectoryError("DIRECTORY_PROTOCOL_INVALID")
            for record in value["records"]:
                DirectoryUser.model_validate(record)
            terminal = value["finished"]
        elif kind == "lookup" and set(value) == {"type", "ptr", "forward", "computers"}:
            terminal = True
        else:
            raise DirectoryError("DIRECTORY_PROTOCOL_INVALID")
        if terminal:
            if stream.read(1):
                raise DirectoryError("DIRECTORY_PROTOCOL_INVALID")
            yield value
            return
        yield value
    raise DirectoryError("DIRECTORY_LIMIT")


class DirectoryJob(_Job):
    def __init__(self) -> None:
        import ctypes

        self._close_lock = threading.Lock()
        super().__init__()
        limits = _JobLimits()
        limits.basic.flags = 0x2308  # process/job memory, count, kill on close.
        limits.basic.processes = 2
        limits.memory[0] = limits.memory[1] = 256 * 1024**2
        if not self._api.kernel.SetInformationJobObject(
            self._handle,
            9,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            self.close()
            raise DirectoryError("LOOKUP_LIMIT")

    def close(self) -> None:
        with self._close_lock:
            handle, self._handle = self._handle, None
        if handle:
            self._api.kernel.CloseHandle(handle)


class NativeDirectory:
    def __init__(self, settings: DirectorySettings, *, stop: threading.Event | None = None) -> None:
        self.settings = settings
        self.stop = stop or threading.Event()

    def _run(
        self, mode: str, stop: threading.Event, ip: str | None = None
    ) -> Iterator[dict[str, Any]]:
        if os.name != "nt":
            raise DirectoryError("LDAP_UNAVAILABLE")
        payload = self.settings.model_dump(mode="json") | {"mode": mode, "ip": ip}
        system = Path(os.environ.get("SystemRoot", "C:/Windows"))
        executable = system / "System32/WindowsPowerShell/v1.0/powershell.exe"
        job = DirectoryJob()
        child: subprocess.Popen[bytes] | None = None
        done, expired = threading.Event(), threading.Event()
        timer: threading.Thread | None = None
        try:
            child = subprocess.Popen(
                [str(executable), "-NoProfile", "-NonInteractive", "-File", str(SCRIPT)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000,
            )
            job.assign(child)
            assert child.stdin is not None and child.stdout is not None
            deadline = time.monotonic() + min(
                self.settings.max_seconds, 10 if mode == "lookup" else 60
            )

            def watchdog() -> None:
                while not done.wait(0.1):
                    if stop.is_set() or time.monotonic() >= deadline:
                        expired.set()
                        job.close()
                        return

            timer = threading.Thread(target=watchdog, name="directory-deadline", daemon=False)
            timer.start()
            child.stdin.write(json.dumps(payload, separators=(",", ":")).encode() + b"\n")
            child.stdin.flush()
            for frame in read_frames(child.stdout):
                if expired.is_set():
                    raise DirectoryError("DIRECTORY_STOPPED" if stop.is_set() else "LOOKUP_LIMIT")
                terminal = frame["type"] == "lookup" or frame.get("finished") is True
                if terminal and child.wait(timeout=2) != 0:
                    raise DirectoryError("LDAP_UNAVAILABLE")
                yield frame
                if not terminal:
                    child.stdin.write(b"ACK\n")
                    child.stdin.flush()
        except DirectoryError:
            if expired.is_set():
                raise DirectoryError(
                    "DIRECTORY_STOPPED" if stop.is_set() else "LOOKUP_LIMIT"
                ) from None
            raise
        except (OSError, subprocess.SubprocessError, ValueError):
            raise DirectoryError("LDAP_UNAVAILABLE") from None
        finally:
            done.set()
            job.close()
            if child is not None:
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=2)
                for pipe in (child.stdin, child.stdout):
                    if pipe is not None:
                        try:
                            pipe.close()
                        except OSError:
                            pass
            if timer is not None:
                timer.join(2)

    def users(self, stop: threading.Event) -> Iterator[dict[str, Any]]:
        yield from self._run("users", stop)

    def lookup(self, ip: str, scope: DirectoryScope) -> Witnesses:
        if scope != self.settings.scope:
            raise LookupError("DOMAIN_MISMATCH")
        try:
            frames = list(self._run("lookup", self.stop, ip))
            if len(frames) != 1:
                raise DirectoryError("DIRECTORY_PROTOCOL_INVALID")
            value = frames[0]
            if len(value["ptr"]) > 2 or len(value["forward"]) > 16 or len(value["computers"]) > 2:
                raise DirectoryError("LOOKUP_LIMIT")
            ptr = [DnsRecord(row["value"], row["ttl"]) for row in value["ptr"]]
            forward = [DnsRecord(row["value"], row["ttl"]) for row in value["forward"]]
            computers = [
                Computer(
                    row["sid"], UUID(row["guid"]), row["name"], row["dns_hostname"], row["enabled"]
                )
                for row in value["computers"]
            ]
            if any(type(row.enabled) is not bool for row in computers):
                raise DirectoryError("DIRECTORY_PROTOCOL_INVALID")
            return Witnesses(ptr, forward, computers)
        except DirectoryError as error:
            if error.code == "MULTIPLE_MATCHES":
                raise LookupError("MULTIPLE_MATCHES") from None
            raise LookupError(
                "DNS_UNAVAILABLE" if error.code == "DNS_UNAVAILABLE" else "LDAP_UNAVAILABLE"
            ) from None
        except (ValueError, TypeError, KeyError):
            raise LookupError("LOOKUP_LIMIT") from None
