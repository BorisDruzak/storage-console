"""Explicit once-per-rule derived recheck; immutable source evidence is never edited."""

from uuid import UUID

from sqlalchemy import func, insert, select
from sqlalchemy.engine import Connection, RowMapping

from packages.shared.jobs import enqueue, lock_key
from packages.shared.models.activity import change_events
from packages.shared.models.audit import audit_correlations
from packages.shared.models.jobs import jobs
from packages.shared.models.security import audit_log

from .correlation import RULE_VERSION
from .engine import correlate


class ChangeNotFound(Exception):
    pass


class RecheckConflict(Exception):
    pass


def request(connection: Connection, change_id: UUID, requester: UUID) -> RowMapping:
    connection.execute(select(func.set_config("lock_timeout", "2s", True)))
    if connection.scalar(select(change_events.c.id).where(change_events.c.id == change_id)) is None:
        raise ChangeNotFound
    key = "audit-recheck:" + RULE_VERSION + ":" + str(change_id)
    connection.execute(select(func.pg_advisory_xact_lock(lock_key(key))))
    previous = (
        connection.execute(select(jobs).where(jobs.c.idempotency_key == key))
        .mappings()
        .one_or_none()
    )
    if previous is not None:
        payload = previous["payload"]
        if (
            previous["kind"] != "audit_recheck"
            or not isinstance(payload, dict)
            or set(payload) != {"change_id", "rule_version", "requested_by"}
            or payload["change_id"] != str(change_id)
            or payload["rule_version"] != RULE_VERSION
        ):
            raise RecheckConflict
        return previous
    job_id = enqueue(
        connection,
        "audit_recheck",
        {
            "change_id": str(change_id),
            "rule_version": RULE_VERSION,
            "requested_by": str(requester),
        },
        key,
    )
    connection.execute(
        insert(audit_log).values(
            user_id=requester,
            action="audit.recheck_requested",
            resource_type="change_event",
            resource_identity=str(change_id),
            result="QUEUED",
            details={"rule_version": RULE_VERSION, "job_id": str(job_id)},
        )
    )
    return connection.execute(select(jobs).where(jobs.c.id == job_id)).mappings().one()


def _summary(row: RowMapping | None) -> dict[str, str] | None:
    return {key: row[key] for key in ("rule_version", "class", "reason")} if row else None


def process(connection: Connection, job: RowMapping) -> None:
    payload = job["payload"]
    if set(payload) != {"change_id", "rule_version", "requested_by"}:
        raise ValueError("INVALID_AUDIT_RECHECK_PAYLOAD")
    if payload["rule_version"] != RULE_VERSION:
        raise ValueError("AUDIT_RULE_VERSION_CHANGED")
    change_id, requester = UUID(payload["change_id"]), UUID(payload["requested_by"])
    change = (
        connection.execute(select(change_events).where(change_events.c.id == change_id))
        .mappings()
        .one_or_none()
    )
    if change is None:
        raise ValueError("CHANGE_NOT_FOUND")
    connection.execute(select(func.set_config("lock_timeout", "2s", True)))
    connection.execute(
        select(
            func.pg_advisory_xact_lock(lock_key("audit-source:" + str(change["source_node_id"])))
        )
    )
    query = select(audit_correlations).where(audit_correlations.c.change_event_id == change_id)
    before = connection.execute(query).mappings().one_or_none()
    correlate(connection, change)
    after = connection.execute(query).mappings().one()
    connection.execute(
        insert(audit_log).values(
            user_id=requester,
            action="audit.recheck_completed",
            resource_type="change_event",
            resource_identity=str(change_id),
            result="COMPLETE",
            details={
                "job_id": str(job["id"]),
                "before": _summary(before),
                "after": _summary(after),
            },
        )
    )
