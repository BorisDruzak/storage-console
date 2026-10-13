"""Separate service specification using the shared native SCM ABI, never the USN identity."""

import ctypes
from dataclasses import dataclass

from collectors.windows._scm_native import Action, D, NativeBackend, Recovery, check
from collectors.windows.errors import SecurityError
from collectors.windows.scm import RECOVERY, ServiceSpec, _path

SERVICE_NAME = "SosnadminStorageAudit"


@dataclass(frozen=True)
class AuditServiceSpec:
    executable: str
    state_path: str
    name: str = SERVICE_NAME

    def __post_init__(self) -> None:
        object.__setattr__(self, "executable", _path(self.executable))
        object.__setattr__(self, "state_path", _path(self.state_path))
        if self.name != SERVICE_NAME and not (
            self.name.startswith(SERVICE_NAME + "Test")
            and self.name.isascii()
            and self.name.isalnum()
            and len(self.name) <= 96
        ):
            raise ValueError("AUDIT_SERVICE_NAME_INVALID")

    @property
    def command(self) -> str:
        return (
            f'"{self.executable}" -I -m collectors.windows_audit.service '
            f'--name {self.name} --state "{self.state_path}"'
        )


class AuditBackend(NativeBackend):
    def create(self, spec: ServiceSpec) -> None:
        if not isinstance(spec, AuditServiceSpec):
            raise SecurityError("AUDIT_SERVICE_NAME_INVALID")
        with self._manager(1 | 2) as manager:
            # Display names also must be unique in SCM; never share the USN registration name.
            display = "Storage Console Windows Security Audit"
            if spec.name != SERVICE_NAME:
                display += " " + spec.name
            handle = self.api.CreateServiceW(
                manager,
                spec.name,
                display,
                0xF01FF,
                0x10,
                2,
                1,
                spec.command,
                None,
                None,
                None,
                None,
                None,
            )
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
                self.api.DeleteService(handle)
                raise
            finally:
                self.api.CloseServiceHandle(handle)
