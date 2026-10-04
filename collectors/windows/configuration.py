"""Explicit operator activation; startup verifies state and never resumes auth."""

import base64
import json
from dataclasses import dataclass
from typing import Annotated, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from collectors.common.outbox import Limits, Outbox, OutboxError
from collectors.common.transport import Transport, TransportError

from .errors import SecurityError
from .inventory import CaptureError, Scope
from .security import ProtectedState, seal, unseal


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    heartbeat_seconds: Annotated[int, Field(ge=1, le=3600)] = 30
    inventory_seconds: Annotated[int, Field(ge=1, le=86400)] = 3600
    poll_seconds: Annotated[float, Field(ge=0.05, le=5, allow_inf_nan=False)] = 1
    transport_seconds: Annotated[int, Field(ge=1, le=15)] = 15
    stop_seconds: Annotated[int, Field(ge=5, le=120)] = 30
    child_stop_seconds: Annotated[int, Field(ge=1, le=10)] = 3
    capacity_wait_seconds: Annotated[int, Field(ge=0, le=30)] = 5
    batch_records: Annotated[int, Field(ge=1, le=512)] = 512
    retained_batches: Annotated[int, Field(ge=2, le=100000)] = 2048
    retained_bytes: Annotated[int, Field(ge=1, le=8 * 1024**3)] = 512 * 1024**2
    reserve_batches: Annotated[int, Field(ge=1, le=10000)] = 32
    reserve_bytes: Annotated[int, Field(ge=1024, le=1024**2)] = 64 * 1024
    busy_seconds: Annotated[int, Field(ge=1, le=10)] = 5
    heartbeat_burst: Annotated[int, Field(ge=1, le=100)] = 4

    @model_validator(mode="after")
    def deadlines(self) -> Self:
        if (
            self.transport_seconds + self.busy_seconds + self.child_stop_seconds + 1
            > self.stop_seconds
        ):
            raise ValueError("INVALID_SETTINGS")
        try:
            self.limits()
        except OutboxError:
            raise ValueError("INVALID_SETTINGS") from None
        return self

    def limits(self) -> Limits:
        return Limits(
            max_retained_batches=self.retained_batches,
            max_retained_bytes=self.retained_bytes,
            max_body_bytes=min(8 * 1024**2, self.retained_bytes),
            heartbeat_reserve_batches=self.reserve_batches,
            heartbeat_reserve_bytes=self.reserve_bytes,
            busy_timeout_seconds=self.busy_seconds,
        )


class PrivateConfig(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    version: Annotated[int, Field(ge=1, le=1)] = 1
    collector_id: UUID
    credential_version: UUID = Field(repr=False)
    origin: str = Field(repr=False, min_length=1, max_length=512)
    roots: tuple[str, ...] = Field(repr=False, min_length=1, max_length=32)
    encrypted_token: str = Field(repr=False, min_length=1, max_length=87384)
    settings: RuntimeSettings = Field(default_factory=RuntimeSettings)

    @property
    def scope(self) -> Scope:
        return Scope(self.roots)

    @property
    def ca_name(self) -> str:
        return "ca-" + str(self.credential_version) + ".pem"


@dataclass(frozen=True)
class Loaded:
    config: PrivateConfig
    outbox: Outbox
    transport: Transport


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _read(state: ProtectedState) -> PrivateConfig:
    raw = state.read("config.json", 131072)
    try:
        json.loads(raw, object_pairs_hook=_unique)
        config = PrivateConfig.model_validate_json(raw)
        _ = config.scope
        return config
    except (ValueError, TypeError, UnicodeError, CaptureError, OutboxError):
        raise SecurityError("CONFIG_INVALID") from None


def _outbox(state: ProtectedState, config: PrivateConfig) -> Outbox:
    try:
        names = ["outbox.sqlite3" + suffix for suffix in ("", "-journal", "-wal", "-shm")]
        for name in names:
            if (state.root / name).exists():
                state.validate_file(name)
        box = Outbox(state.root / "outbox.sqlite3", config.collector_id, config.settings.limits())
        for name in names:
            if (state.root / name).exists():
                state.validate_file(name)
        return box
    except OutboxError:
        raise SecurityError("STATE_INVALID") from None


def load(state: ProtectedState) -> Loaded:
    config = _read(state)
    box = _outbox(state, config)
    if box.credential_binding() != config.credential_version:
        raise SecurityError("CREDENTIAL_MISMATCH")
    # Verify binding before touching the secret, including after config rollback/crash.
    try:
        state.read(config.ca_name, 128 * 1024)
        token = unseal(base64.b64decode(config.encrypted_token, validate=True)).decode("ascii")
        transport = Transport(
            config.origin,
            state.root / config.ca_name,
            token,
            timeout=config.settings.transport_seconds,
            collector_id=config.collector_id,
        )
    except (ValueError, UnicodeError, TransportError):
        raise SecurityError("CONFIG_INVALID") from None
    return Loaded(config, box, transport)


def activate(
    state: ProtectedState,
    collector_id: UUID,
    origin: str,
    scope: Scope,
    token: str,
    ca: bytes,
    settings: RuntimeSettings | None = None,
) -> PrivateConfig:
    try:
        settings = settings or RuntimeSettings()
        # Revalidate even model_copy/model_construct values before state changes.
        settings = RuntimeSettings.model_validate_json(settings.model_dump_json())
        scope = Scope(scope.roots)
        config = PrivateConfig(
            collector_id=collector_id,
            credential_version=uuid4(),
            origin=origin,
            roots=scope.roots,
            encrypted_token=base64.b64encode(seal(token.encode("ascii"))).decode(),
            settings=settings,
        )
        encoded = config.model_dump_json().encode("utf-8")
        if len(encoded) > 131072:
            raise SecurityError("CONFIG_INVALID")
        if (state.root / "config.json").exists():
            previous = _read(state)
            if previous.collector_id != collector_id:
                raise SecurityError("IDENTITY_CONFLICT")
            if previous.scope.fingerprint != scope.fingerprint:
                raise SecurityError("SCOPE_CHANGED")
        if not isinstance(ca, bytes) or not 1 <= len(ca) <= 128 * 1024:
            raise SecurityError("CONFIG_INVALID")
        # A new version's CA cannot overwrite trust used by a previously active config.
        state.write(config.ca_name, ca)
        Transport(
            origin,
            state.root / config.ca_name,
            token,
            timeout=settings.transport_seconds,
            collector_id=collector_id,
        )
        box = _outbox(state, config)
        box.activate_credentials(config.credential_version)
        # Failure after the DB commit leaves the old config mismatched: fail closed.
        state.write("config.json", encoded)
        return config
    except (
        ValueError,
        TypeError,
        AttributeError,
        UnicodeError,
        ValidationError,
        CaptureError,
        OutboxError,
        TransportError,
    ):
        raise SecurityError("CONFIG_INVALID") from None
