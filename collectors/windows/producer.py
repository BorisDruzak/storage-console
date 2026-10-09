"""Bounded observations into the transactional outbox, without native cursor claims."""

import math
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import ValidationError

from collectors.common.outbox import Checkpoint, Outbox, OutboxError
from packages.contracts.common import BatchEnvelope
from packages.contracts.heartbeat import HeartbeatRecord
from packages.contracts.inventory import InventoryRecord

from .inventory import CODES, CaptureError, Observation, Scope

_INVENTORY = "windows:inventory"
_HEARTBEAT = "windows:heartbeat"


@dataclass(frozen=True)
class CaptureReport:
    records: int
    batches: int
    completed: bool
    errors: tuple[str, ...]


def _outbox_failure(error: OutboxError) -> str:
    return {
        "CAPACITY": "CAPACITY",
        "CHECKPOINT_CONFLICT": "STATE_MISMATCH",
        "INVALID_BATCH": "METADATA_INVALID",
        "STOPPED": "STOPPED",
    }.get(error.code, "NATIVE_FAILED")


def _state(
    box: Outbox, stream: str, scope: Scope | None = None, *, retry_locks: bool = False,
) -> Checkpoint:
    try:
        state = box.checkpoint(stream)
    except OutboxError as error:
        if retry_locks:
            raise
        raise CaptureError(_outbox_failure(error)) from None
    if state.revision == 0 and state.value is None:
        return state
    value = state.value
    expected = (
        {"kind", "sequence"}
        if scope is None
        else {"kind", "scope", "scan_id", "sequence", "completed"}
    )
    if (
        not isinstance(value, dict)
        or set(value) != expected
        or value["kind"] != stream
        or type(value["sequence"]) is not int
        or not 1 <= value["sequence"] < 2**63
    ):
        raise CaptureError("STATE_MISMATCH")
    if scope is not None:
        if (
            value["scope"] != scope.fingerprint
            or type(value["completed"]) is not bool
            or not isinstance(value["scan_id"], str)
        ):
            raise CaptureError("STATE_MISMATCH")
        try:
            UUID(value["scan_id"])
        except ValueError:
            raise CaptureError("STATE_MISMATCH") from None
    return state


def _inventory_batch(
    box: Outbox, records: list[InventoryRecord], now: datetime
) -> BatchEnvelope[InventoryRecord]:
    return BatchEnvelope[InventoryRecord](
        collector_id=box.collector_id,
        batch_id=str(uuid4()),
        schema_version=1,
        sent_at=now,
        first_event_at=min(r.occurred_at for r in records),
        last_event_at=max(r.occurred_at for r in records),
        record_count=len(records),
        records=records,
    )


def capture_inventory(
    box: Outbox,
    scope: Scope,
    observations: Iterator[Observation],
    *,
    max_records: int = 256,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    stopped: Callable[[], bool] = lambda: False,
    capacity_wait_seconds: float = 0,
    monotonic: Callable[[], float] = time.monotonic,
    wait: Callable[[float], object] = time.sleep,
) -> CaptureReport:
    if not isinstance(scope, Scope):
        raise CaptureError("INVALID_SCOPE")
    if type(max_records) is not int or not 1 <= max_records <= 512:
        raise CaptureError("METADATA_INVALID")
    if (
        type(capacity_wait_seconds) not in (int, float)
        or not math.isfinite(capacity_wait_seconds)
        or not 0 <= capacity_wait_seconds <= 30
    ):
        raise CaptureError("METADATA_INVALID")
    source = iter(observations)
    errors: set[str] = set()
    persisted, batches, completed = 0, 0, False
    bucket: list[InventoryRecord] = []
    size = 0
    budget = min(8 * 1024**2, box.limits.max_body_bytes) - 2048
    scan_id = str(uuid4())
    revision = 0
    source_closed = False

    def close_source() -> None:
        nonlocal source_closed
        if source_closed:
            return
        source_closed = True
        close = getattr(source, "close", None)
        if close is not None:
            try:
                close()
            except Exception:
                errors.add("NATIVE_FAILED")

    def flush(final: bool) -> None:
        nonlocal revision, persisted, batches, bucket, size
        if not bucket:
            return
        batch = _inventory_batch(box, bucket, clock())
        deadline = monotonic() + capacity_wait_seconds
        while True:
            if stopped():
                raise OutboxError("STOPPED")
            try:
                box.enqueue(
                    "inventory",
                    batch,
                    _INVENTORY,
                    revision,
                    {
                        "kind": _INVENTORY,
                        "scope": scope.fingerprint,
                        "scan_id": scan_id,
                        "sequence": batches + 1,
                        "completed": final,
                    },
                )
                break
            except OutboxError as error:
                remaining = deadline - monotonic()
                if error.code != "CAPACITY" or remaining <= 0:
                    raise
                wait(min(0.1, remaining))
        revision += 1
        persisted += len(bucket)
        batches += 1
        bucket, size = [], 0

    try:
        # Validate durable scope before advancing the lazy native iterator.
        revision = _state(box, _INVENTORY, scope).revision
        while True:
            if stopped():
                errors.add("STOPPED")
                break
            try:
                item = next(source)
            except StopIteration:
                close_source()
                completed = not errors and bool(persisted or bucket)
                flush(completed)
                break
            except Exception as error:
                errors.add(error.code if isinstance(error, CaptureError) else "NATIVE_FAILED")
                flush(False)
                break
            if not isinstance(item, Observation):
                errors.add("METADATA_INVALID")
                flush(False)
                break
            if item.error_code:
                errors.add(item.error_code)
                continue
            record = cast(InventoryRecord, item.record)
            record_size = len(record.model_dump_json().encode("utf-8")) + 1
            if record_size > budget:
                errors.add("METADATA_INVALID")
                flush(False)
                break
            if len(bucket) >= max_records or size + record_size > budget:
                flush(False)
            bucket.append(record)
            size += record_size
    except OutboxError as error:
        completed = False
        errors.add(_outbox_failure(error))
    except (ValueError, TypeError, UnicodeError, ValidationError):
        completed = False
        errors.add("METADATA_INVALID")
    except CaptureError:
        raise
    except Exception:
        completed = False
        errors.add("NATIVE_FAILED")
    finally:
        close_source()
        if errors:
            completed = False
    return CaptureReport(persisted, batches, completed, tuple(sorted(errors)))


def capture_heartbeat(
    box: Outbox,
    *,
    error_code: str | None = None,
    cursor: str | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> str:
    if error_code is not None and error_code not in CODES:
        raise CaptureError("METADATA_INVALID")
    state = _state(box, _HEARTBEAT, retry_locks=True)
    sequence = 1 if state.value is None else cast(dict[str, int], state.value)["sequence"] + 1
    try:
        now = clock()
        record = HeartbeatRecord(occurred_at=now, version="0.1.0", error_code=error_code,
                                 cursor=cursor)
        batch = BatchEnvelope[HeartbeatRecord](
            collector_id=box.collector_id,
            batch_id=str(uuid4()),
            schema_version=1,
            sent_at=now,
            first_event_at=now,
            last_event_at=now,
            record_count=1,
            records=[record],
        )
        return box.enqueue(
            "heartbeat",
            batch,
            _HEARTBEAT,
            state.revision,
            {"kind": _HEARTBEAT, "sequence": sequence},
        )
    except OutboxError as error:
        if error.code != "CAPACITY":
            raise
        raise CaptureError(_outbox_failure(error)) from None
    except (ValueError, TypeError, ValidationError):
        raise CaptureError("METADATA_INVALID") from None
