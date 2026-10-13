"""Machine DPAPI configuration and payload encryption; protected state owns the lock."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from collectors.common.transport import Transport
from collectors.windows.security import ProtectedState, seal, unseal

from .scope import AuditScope

QUEUE_NAME = "audit.sqlite3"
CONFIG_NAME = "audit-config.dpapi"


class MachineCipher:
    # The existing machine DPAPI primitive bounds one blob to 64 KiB. Chunking
    # preserves that bound for a larger local cache; blobs remain inside a protected root.
    def protect(self, value: bytes) -> bytes:
        if not 0 < len(value) <= 4 * 1024**2:
            raise ValueError("AUDIT_PAYLOAD_INVALID")
        return json.dumps(
            [
                base64.b64encode(seal(value[i : i + 48000])).decode("ascii")
                for i in range(0, len(value), 48000)
            ],
            separators=(",", ":"),
        ).encode()

    def unprotect(self, value: bytes) -> bytes:
        if len(value) > 6 * 1024**2:
            raise ValueError("AUDIT_PAYLOAD_INVALID")
        blobs = json.loads(value)
        if not isinstance(blobs, list) or not 1 <= len(blobs) <= 88:
            raise ValueError("AUDIT_PAYLOAD_INVALID")
        return b"".join(unseal(base64.b64decode(blob, validate=True)) for blob in blobs)


class AuditConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    collector_id: UUID
    host_id: UUID
    source_id: UUID
    generation: UUID
    roots: dict[str, str] = Field(min_length=1, max_length=16)
    origin: str = Field(max_length=2048)
    ca_file: str = Field(max_length=32768)
    token: SecretStr = Field(repr=False)
    configured: bool = False  # Operator-verified effective policy AND narrow SACL.
    initial_baseline: bool = False
    mode: Literal["capture_only"] = "capture_only"  # Central audit ingest is Stage B.

    @model_validator(mode="after")
    def validate_settings(self) -> AuditConfig:
        AuditScope(self.roots)
        if not 32 <= len(self.token.get_secret_value()) <= 4096:
            raise ValueError("AUDIT_CREDENTIAL_INVALID")
        Transport(
            self.origin,
            Path(self.ca_file),
            self.token.get_secret_value(),
            collector_id=self.collector_id,
        )
        return self


def activate(state: ProtectedState, config: AuditConfig) -> None:
    # Initialization only; a new identity/generation cannot overwrite an existing queue.
    if (state.root / CONFIG_NAME).exists() or (state.root / QUEUE_NAME).exists():
        raise ValueError("AUDIT_ALREADY_INITIALIZED")
    value = config.model_dump(mode="json")
    value["token"] = config.token.get_secret_value()
    state.write(CONFIG_NAME, seal(json.dumps(value, separators=(",", ":")).encode()))
    state.create_file(QUEUE_NAME)


def load(state: ProtectedState) -> AuditConfig:
    return AuditConfig.model_validate_json(unseal(state.read(CONFIG_NAME, 65536)))
