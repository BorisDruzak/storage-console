"""Transactional PostgreSQL jobs. Handlers must keep effects in this connection."""

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection, Engine, RowMapping

from packages.shared.models.jobs import jobs

Handler = Callable[[Connection, RowMapping], None]


class JobConflict(ValueError):
    pass


def lock_key(idempotency_key: str) -> int:
    return int.from_bytes(
        hashlib.sha256(("storage-console-job:" + idempotency_key).encode()).digest()[:8],
        byteorder="big",
        signed=True,
    )


def enqueue(
    connection: Connection,
    kind: str,
    payload: dict[str, Any],
    idempotency_key: str,
    *,
    max_attempts: int = 5,
) -> UUID:
    if not 1 <= len(kind) <= 64 or not 1 <= len(idempotency_key) <= 255:
        raise ValueError("INVALID_JOB_IDENTITY")
    if not 1 <= max_attempts <= 20:
        raise ValueError("INVALID_ATTEMPT_LIMIT")
    # Bound internal metadata too; allow neither non-finite numbers nor opaque objects.
    encoded = json.dumps(payload, allow_nan=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode()) > 65536:
        raise ValueError("JOB_PAYLOAD_TOO_LARGE")
    identity = connection.scalar(
        insert(jobs)
        .values(
            kind=kind,
            payload=payload,
            idempotency_key=idempotency_key,
            status="PENDING",
            max_attempts=max_attempts,
        )
        .on_conflict_do_nothing(index_elements=[jobs.c.idempotency_key])
        .returning(jobs.c.id)
    )
    if identity is not None:
        return cast(UUID, identity)
    previous = (
        connection.execute(select(jobs).where(jobs.c.idempotency_key == idempotency_key))
        .mappings()
        .one()
    )
    if (
        previous["kind"] != kind
        or json.dumps(previous["payload"], allow_nan=False, sort_keys=True, separators=(",", ":"))
        != encoded
        or previous["max_attempts"] != max_attempts
    ):
        raise JobConflict("JOB_IDEMPOTENCY_CONFLICT")
    return cast(UUID, previous["id"])


def process_one(engine: Engine, handlers: Mapping[str, Handler]) -> bool:
    with engine.begin() as connection:
        job = (
            connection.execute(
                select(jobs)
                .where(
                    jobs.c.status.in_(["PENDING", "RETRY"]),
                    jobs.c.next_attempt_at <= func.now(),
                )
                .order_by(jobs.c.next_attempt_at, jobs.c.created_at, jobs.c.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            .mappings()
            .one_or_none()
        )
        if job is None:
            return False
        if not connection.scalar(
            select(
                func.pg_try_advisory_xact_lock(
                    lock_key(job["idempotency_key"]),
                )
            )
        ):
            # Avoid starving later jobs while another transaction holds the resource.
            connection.execute(
                update(jobs)
                .where(jobs.c.id == job["id"])
                .values(
                    next_attempt_at=func.now() + timedelta(seconds=1),
                )
            )
            return False
        attempt = job["attempts"] + 1
        handler = handlers.get(job["kind"])
        error: str | None = None
        if handler is None:
            error = "UNKNOWN_JOB_KIND"
        else:
            try:
                with connection.begin_nested():
                    handler(connection, job)
            except Exception:
                # Persist codes only: handler exceptions can contain private metadata.
                error = "HANDLER_FAILED"
        terminal = error is not None and (handler is None or attempt >= job["max_attempts"])
        connection.execute(
            update(jobs)
            .where(jobs.c.id == job["id"])
            .values(
                attempts=attempt,
                error_code=error,
                status="FAILED" if terminal else "RETRY" if error else "COMPLETE",
                next_attempt_at=func.now() + timedelta(seconds=min(300, 2 ** min(attempt, 9))),
                completed_at=func.now() if terminal or error is None else None,
            )
        )
    return True
