"""Separate service specification using the shared native SCM ABI, never the USN identity."""

from dataclasses import dataclass

from collectors.windows.scm import _path

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
