"""Admin-only projections; sensitive filters are CSRF-protected POST bodies."""

from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.engine import Connection, Engine, RowMapping

from apps.api.directory_read import directory_stream, names
from apps.api.ingest import ApiError
from apps.api.read.sources import database_time, require_source, snapshot
from apps.api.read.validity import stamp
from apps.api.user_auth.dependencies import require_csrf, require_permission
from packages.contracts.audit import (
    AuditActor,
    AuditCandidateView,
    AuditCoverage,
    AuditEvent,
    AuditHealth,
    AuditObject,
    AuditPage,
    AuditRecordView,
    AuditSearch,
    AuditStream,
    ChangeAudit,
)
from packages.contracts.directory import DirectoryStream
from packages.shared.audit.correlation import RULE_VERSION
from packages.shared.audit.engine import coverage_report, identity
from packages.shared.models.activity import change_events
from packages.shared.models.audit import (
    audit_candidates,
    audit_correlations,
    audit_evidence,
    audit_identity_observations,
    audit_streams,
)
from packages.shared.models.core import collectors, filesystem_objects, source_nodes, volumes


def record(row: RowMapping, observations: dict[str, Any] | None = None) -> AuditRecordView:
    return AuditRecordView(
        id=row["id"],
        source_id=row["source_node_id"],
        audit_collector_id=row["audit_collector_id"],
        first_received_at=row["first_received_at"],
        digest=row["digest"],
        evidence=row["payload"],
        numeric_fields={
            key: str(row["payload"][key])
            for key in ("record_id", "logon_id", "handle_id", "process_id", "access_mask")
            if row["payload"].get(key) is not None
        },
        **(observations or {}),
    )


def stream(connection: Connection, source: UUID) -> AuditStream:
    now = database_time(connection)
    rows = (
        connection.execute(
            select(
                collectors,
                audit_streams.c.health,
                audit_streams.c.reported_at,
                audit_streams.c.accepted_at,
                source_nodes.c.expected_cadence_seconds,
            )
            .join(source_nodes, source_nodes.c.id == collectors.c.source_node_id)
            .outerjoin(audit_streams, audit_streams.c.collector_id == collectors.c.id)
            .where(
                collectors.c.source_node_id == source,
                collectors.c.collector_type == "AUDIT_WINDOWS",
                collectors.c.enabled.is_(True),
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return AuditStream(state="NOT_CONFIGURED", evaluated_at=now)
    if len(rows) != 1:
        return AuditStream(state="UNKNOWN", evaluated_at=now, enabled=True)
    row = rows[0]
    health = AuditHealth.model_validate(row["health"]) if row["health"] else None
    if health is not None and health.readiness_complete is not None:
        health = readiness_projection(health, now)
    state: Literal[
        "NOT_CONFIGURED", "UNKNOWN", "HEALTHY", "STALE", "GAP", "ERROR", "OBSERVE", "BACKPRESSURE"
    ] = "UNKNOWN"
    if health:
        state = health.state
        if health.gap:
            state = "GAP"
        elif not health.configured:
            state = "NOT_CONFIGURED"
        elif (
            row["reported_at"] is None
            or row["reported_at"] > now
            or now - row["reported_at"] > timedelta(seconds=row["expected_cadence_seconds"] * 2)
        ):
            state = "STALE"
        elif health.error_code or health.quarantine:
            state = "ERROR"
        elif health.last_collected_at is None or health.last_collected_at > now:
            state = "UNKNOWN"
        elif now - health.last_collected_at > timedelta(
            seconds=row["expected_cadence_seconds"] * 2
        ):
            state = "STALE"
        elif state == "HEALTHY" and (
            health.backlog_count or not health.policy_verified or not health.sacl_verified
        ):
            state = "OBSERVE"
    return AuditStream(
        collector_id=row["id"],
        enabled=True,
        state=state,
        evaluated_at=now,
        reported_at=row["reported_at"],
        accepted_at=row["accepted_at"],
        diagnostics=health,
    )


def readiness_projection(health: AuditHealth, now: datetime) -> AuditHealth:
    """Expire scope proof independently of heartbeat arrival; never mutate its receipt."""
    checked = health.readiness_checked_at
    age = (
        max(
            health.readiness_age_seconds or 0,
            (now - checked).total_seconds() + (health.readiness_duration_seconds or 0),
        )
        if checked is not None and checked <= now
        else None
    )
    stale = (
        health.readiness_complete is not True
        or health.readiness_stale is not False
        or age is None
        or age > 60
    )
    updates: dict[str, Any] = {"readiness_age_seconds": age, "readiness_stale": stale}
    if stale:
        updates.update(policy_verified=False, sacl_verified=False)
    return health.model_copy(update=updates)


def stamp_stream(
    connection: Connection, response: Response, source: UUID, value: AuditStream
) -> None:
    remaining = 35.0
    if value.state == "HEALTHY" and value.diagnostics and value.reported_at:
        cadence = connection.execute(
            select(source_nodes.c.expected_cadence_seconds).where(source_nodes.c.id == source)
        ).scalar_one()
        for at in (value.reported_at, value.diagnostics.last_collected_at):
            if at is not None:
                remaining = min(
                    remaining, max(0.0, (at - value.evaluated_at).total_seconds() + 2 * cadence)
                )
        if value.diagnostics.readiness_complete is not None:
            proof = readiness_projection(value.diagnostics, value.evaluated_at)
            remaining = min(
                remaining,
                0.0 if proof.readiness_stale else max(
                    0.0, 60 - (proof.readiness_age_seconds or 0)
                ),
            )
    stamp(response, remaining)


def router(engine: Engine) -> APIRouter:
    result = APIRouter(
        prefix="/api/v1/audit",
        tags=["security-audit"],
        dependencies=[Depends(require_permission("read_sensitive_activity"))],
        responses={code: {"model": ApiError} for code in (401, 403, 404, 413, 422, 503)},
    )

    @result.get("/sources/{source_id}")
    def status(source_id: UUID, response: Response) -> AuditStream:
        response.headers["Cache-Control"] = "no-store"
        with snapshot(engine) as connection:
            require_source(connection, source_id)
            value = stream(connection, source_id)
            stamp_stream(connection, response, source_id, value)
            return value

    @result.post("/search", dependencies=[Depends(require_csrf)])
    def search(filters: AuditSearch, response: Response) -> AuditPage:
        response.headers["Cache-Control"] = "no-store"
        with snapshot(engine) as connection:
            now = database_time(connection)
            end = filters.end_at or now
            start = filters.start_at or end - timedelta(days=1)
            if start > end or end - start > timedelta(days=31):
                raise HTTPException(422, detail="INVALID_AUDIT_WINDOW")
            query = select(audit_evidence).where(
                audit_evidence.c.occurred_at >= start, audit_evidence.c.occurred_at <= end
            )
            if filters.source_id is not None:
                require_source(connection, filters.source_id)
                query = query.where(audit_evidence.c.source_node_id == filters.source_id)
            for name in ("event_id", "sid"):
                value = getattr(filters, name)
                if value is not None:
                    query = query.where(audit_evidence.c[name] == value)
            for name in ("account", "client_ip"):
                value = getattr(filters, name)
                if value is not None:
                    query = query.where(audit_evidence.c.payload[name].astext == value)
            if filters.file_id is not None:
                linked = (
                    select(audit_candidates.c.audit_evidence_id)
                    .join(change_events, change_events.c.id == audit_candidates.c.change_event_id)
                    .where(change_events.c.file_id == filters.file_id)
                )
                query = query.where(audit_evidence.c.id.in_(linked))
            rows = (
                connection.execute(
                    query.order_by(audit_evidence.c.occurred_at.desc(), audit_evidence.c.id.desc())
                    .limit(filters.limit + 1)
                    .offset(filters.offset)
                )
                .mappings()
                .all()
            )
            keys = [
                (row["source_node_id"], row["payload"].get("sid"), row["payload"].get("client_ip"))
                for row in rows[: filters.limit]
            ]
            observations = names(connection, keys, now)
            return AuditPage(
                items=[
                    record(row, observations.get(key))
                    for row, key in zip(rows[: filters.limit], keys, strict=True)
                ],
                limit=filters.limit,
                offset=filters.offset,
                has_more=len(rows) > filters.limit,
                evaluated_at=now,
            )

    @result.get("/changes/{change_id}/coverage")
    def historical_coverage(change_id: UUID, response: Response) -> AuditCoverage:
        stamp(response)
        with snapshot(engine) as connection:
            now = database_time(connection)
            change = connection.execute(
                select(change_events).where(change_events.c.id == change_id)
            ).mappings().one_or_none()
            if change is None:
                raise HTTPException(404, detail="CHANGE_NOT_FOUND")
            # Diagnose one exact candidate only; never expand an arbitrary
            # search or run the writing correlate() path on a read request.
            accesses = connection.execute(
                select(audit_evidence.c.payload)
                .join(audit_candidates, audit_candidates.c.audit_evidence_id == audit_evidence.c.id)
                .where(audit_candidates.c.change_event_id == change_id,
                       audit_evidence.c.source_node_id == change["source_node_id"],
                       audit_evidence.c.event_id == 4663,
                       audit_candidates.c.rule_version == RULE_VERSION)
                .limit(2)
            ).scalars().all()
            value = AuditCoverage(
                change_id=change_id, evaluated_at=now, rule_version=RULE_VERSION,
                reason="NO_UNIQUE_ACCESS",
            )
            if len(accesses) != 1:
                return value
            access = AuditEvent.model_validate(accesses[0])
            relative = (change["old_relative_path"] if change["event_type"] == "DELETE"
                        else change["new_relative_path"])
            reason, prior = identity(connection, change, access, relative or "")
            identity_at = connection.scalar(select(audit_identity_observations.c.occurred_at).where(
                audit_identity_observations.c.id == prior
            )) if prior else None
            report = coverage_report(
                connection, change["source_node_id"], access, change["occurred_at"], identity_at
            )
            return value.model_copy(update={
                "identity_reason": reason, "passed": report.passed, "reason": report.reason,
                "interval_start": report.start, "interval_end": report.end,
                "collectors": report.collectors,
            })

    @result.get("/changes/{change_id}")
    def evidence(change_id: UUID, response: Response) -> ChangeAudit:
        response.headers["Cache-Control"] = "no-store"
        with snapshot(engine) as connection:
            change = (
                connection.execute(select(change_events).where(change_events.c.id == change_id))
                .mappings()
                .one_or_none()
            )
            if change is None:
                raise HTTPException(404, detail="CHANGE_NOT_FOUND")
            health = stream(connection, change["source_node_id"])
            stamp_stream(connection, response, change["source_node_id"], health)
            verdict = (
                connection.execute(
                    select(audit_correlations).where(
                        audit_correlations.c.change_event_id == change_id
                    )
                )
                .mappings()
                .one_or_none()
            )
            rows = (
                connection.execute(
                    select(
                        audit_evidence,
                        audit_candidates.c.method,
                        audit_candidates.c["class"],
                        audit_candidates.c.reason,
                        audit_candidates.c.rule_version,
                    )
                    .join(
                        audit_candidates,
                        audit_candidates.c.audit_evidence_id == audit_evidence.c.id,
                    )
                    .where(
                        audit_candidates.c.change_event_id == change_id,
                        audit_candidates.c.rule_version == (
                            verdict["rule_version"] if verdict else RULE_VERSION
                        ),
                    )
                    .order_by(audit_evidence.c.occurred_at, audit_evidence.c.id)
                    .limit(256)
                )
                .mappings()
                .all()
            )
            classification = (
                verdict["class"]
                if verdict
                else (health.state if health.state in ("GAP", "NOT_CONFIGURED") else "UNKNOWN")
            )
            actor = dict(verdict["actor"]) if verdict and verdict["actor"] else None
            keys = [
                (row["source_node_id"], row["payload"].get("sid"), row["payload"].get("client_ip"))
                for row in rows
            ]
            actor_key = (
                (change["source_node_id"], actor["sid"], actor["client_ip"]) if actor else None
            )
            observations = names(
                connection, keys + ([actor_key] if actor_key else []), health.evaluated_at
            )
            if actor is not None and actor_key is not None:
                actor.update(observations.get(actor_key, {}))
            return ChangeAudit(
                change_id=change_id,
                object_id=change["object_id"],
                classification=classification,
                reason=verdict["reason"] if verdict else "NOT_EVALUATED",
                rule_version=verdict["rule_version"] if verdict else None,
                actor=AuditActor.model_validate(actor) if actor is not None else None,
                candidates=[
                    AuditCandidateView(
                        method=row["method"],
                        classification=row["class"],
                        reason=row["reason"],
                        rule_version=row["rule_version"],
                        evidence=record(row, observations.get(key)),
                    )
                    for row, key in zip(rows, keys, strict=True)
                ],
                stream=health,
            )

    @result.get("/objects/{object_id}")
    def object_identity(object_id: UUID, response: Response) -> AuditObject:
        response.headers["Cache-Control"] = "no-store"
        with snapshot(engine) as connection:
            row = (
                connection.execute(
                    select(
                        filesystem_objects.c.file_id,
                        volumes.c.source_node_id,
                        volumes.c.unique_identity,
                    )
                    .join(volumes, volumes.c.id == filesystem_objects.c.volume_id)
                    .where(filesystem_objects.c.id == object_id)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise HTTPException(404, detail="OBJECT_NOT_FOUND")
            return AuditObject(
                object_id=object_id,
                source_id=row["source_node_id"],
                file_id=row["file_id"],
                volume_identity=row["unique_identity"],
            )

    @result.get("/sources/{source_id}/directory")
    def directory_status(source_id: UUID, response: Response) -> DirectoryStream:
        response.headers["Cache-Control"] = "no-store"
        with snapshot(engine) as connection:
            require_source(connection, source_id)
            return directory_stream(connection, source_id, database_time(connection))

    return result
