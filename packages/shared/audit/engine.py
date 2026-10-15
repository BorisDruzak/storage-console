"""Indexed bounded background matching, independent of arrival order."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, literal, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection, RowMapping
from sqlalchemy.sql import Select

from packages.contracts.audit import AuditEvent, CollectorCoverage, CoverageFailure
from packages.shared.jobs import enqueue, lock_key
from packages.shared.models.activity import change_events
from packages.shared.models.audit import (
    audit_candidates,
    audit_correlations,
    audit_evidence,
    audit_health_observations,
    audit_identity_observations,
)
from packages.shared.models.core import collectors, volume_aliases, volumes
from packages.shared.models.jobs import ingest_batches

from .correlation import RULE_VERSION, WINDOW, decide
from .keys import ordinal_key, path_key

PAGE = 32
CANDIDATES = 64


def alias_window_query(
    source: UUID,
    volume: str,
    start: datetime,
    end: datetime,
    *,
    after_at: datetime | None = None,
    after: UUID | None = None,
) -> Select[Any]:
    key = tuple_(
        change_events.c.volume_identity,
        change_events.c.occurred_at,
        change_events.c.id,
    )
    if (after_at is None) != (after is None):
        raise ValueError("INVALID_ALIAS_CURSOR")
    if after_at is not None:
        if after_at.tzinfo is None or not start - WINDOW <= after_at <= end + WINDOW:
            raise ValueError("INVALID_ALIAS_CURSOR")
        lower = key > tuple_(literal(volume), literal(after_at), literal(after))
    else:
        lower = key >= tuple_(literal(volume), literal(start - WINDOW), literal(UUID(int=0)))
    query = select(change_events).where(
        change_events.c.source_node_id == source,
        lower,
        key <= tuple_(literal(volume), literal(end + WINDOW), literal(UUID(int=(1 << 128) - 1))),
    )
    return query.order_by(
        change_events.c.volume_identity,
        change_events.c.occurred_at,
        change_events.c.id,
    ).limit(PAGE + 1)


def candidate_query(source: UUID, volume: str, paths: list[str], at: datetime) -> Select[Any]:
    return (
        select(audit_evidence)
        .where(
            audit_evidence.c.source_node_id == source,
            audit_evidence.c.volume_id == volume,
            audit_evidence.c.path_key.in_([path_key(p) for p in paths]),
            audit_evidence.c.occurred_at >= at - WINDOW,
            audit_evidence.c.occurred_at <= at + WINDOW,
            audit_evidence.c.event_id == 4663,
        )
        .order_by(audit_evidence.c.occurred_at, audit_evidence.c.id)
        .limit(CANDIDATES + 1)
    )


def identity(
    connection: Connection, change: RowMapping, access: AuditEvent, relative_path: str
) -> tuple[str, UUID | None]:
    observations = (
        connection.execute(
            select(audit_identity_observations)
            .join(collectors, collectors.c.id == audit_identity_observations.c.collector_id)
            .where(
                collectors.c.enabled.is_(True),
                collectors.c.collector_type == "WINDOWS",
                audit_identity_observations.c.source_node_id == change["source_node_id"],
                audit_identity_observations.c.volume_id == change["volume_identity"],
                audit_identity_observations.c.file_id == change["file_id"],
                audit_identity_observations.c.occurred_at < access.occurred_at,
                audit_identity_observations.c.occurred_at
                >= access.occurred_at - timedelta(seconds=60),
            )
            .order_by(audit_identity_observations.c.occurred_at.desc())
            .limit(2)
        )
        .mappings()
        .all()
    )
    if not observations:
        return "PATH_TIME_ONLY", None
    prior = observations[0]
    same_time = (
        connection.execute(
            select(audit_identity_observations.c.payload)
            .where(
                audit_identity_observations.c.source_node_id == change["source_node_id"],
                audit_identity_observations.c.volume_id == change["volume_identity"],
                audit_identity_observations.c.file_id == change["file_id"],
                audit_identity_observations.c.occurred_at == prior["occurred_at"],
            )
            .limit(CANDIDATES + 1)
        )
        .scalars()
        .all()
    )
    if len(same_time) > CANDIDATES or any(payload != prior["payload"] for payload in same_time):
        return "IDENTITY_UNCERTAIN", None
    if (
        len(observations) > 1
        and observations[1]["occurred_at"] == prior["occurred_at"]
        and observations[1]["payload"] != prior["payload"]
    ):
        return "IDENTITY_UNCERTAIN", None
    payload = prior["payload"]
    if (
        payload.get("link_count") != 1
        or payload.get("object_type") != "FILE"
        or ordinal_key(payload["relative_path"]) != ordinal_key(relative_path)
    ):
        return "IDENTITY_UNCERTAIN", None
    # Equal-time conflicting inventory and another FileId at the same name fail closed.
    conflicting = connection.scalar(
        select(audit_identity_observations.c.id)
        .where(
            audit_identity_observations.c.source_node_id == change["source_node_id"],
            audit_identity_observations.c.volume_id == change["volume_identity"],
            audit_identity_observations.c.path_key == path_key(relative_path),
            audit_identity_observations.c.file_id != change["file_id"],
            audit_identity_observations.c.occurred_at >= prior["occurred_at"],
            audit_identity_observations.c.occurred_at <= change["occurred_at"] + WINDOW,
        )
        .limit(1)
    )
    if conflicting:
        return "PATH_REUSED", None
    changes = (
        connection.execute(
            select(change_events)
            .where(
                change_events.c.source_node_id == change["source_node_id"],
                change_events.c.volume_identity == change["volume_identity"],
                change_events.c.occurred_at >= prior["occurred_at"],
                change_events.c.occurred_at <= change["occurred_at"] + WINDOW,
                change_events.c.id != change["id"],
                change_events.c.event_type.in_(
                    ["CREATE", "DELETE", "RENAME", "METADATA_CHANGE", "SECURITY_CHANGE"]
                ),
                or_(
                    change_events.c.file_id == change["file_id"],
                    change_events.c.event_type.in_(["CREATE", "DELETE", "RENAME"]),
                ),
            )
            .limit(CANDIDATES + 1)
        )
        .mappings()
        .all()
    )
    if len(changes) > CANDIDATES:
        return "IDENTITY_LIMIT", None
    name = ordinal_key(relative_path)
    for event in changes:
        paths = [
            ordinal_key(p) for p in (event["old_relative_path"], event["new_relative_path"]) if p
        ]
        if (
            event["file_id"] == change["file_id"]
            or not paths
            or any(name == p or name.startswith(p.rstrip("\\") + "\\") for p in paths)
        ):
            return "LIFECYCLE_OR_PARENT_CHANGE", None
    return "PROVEN_PRIOR_IDENTITY", prior["id"]


@dataclass(frozen=True)
class CoverageReport:
    passed: bool
    reason: Literal["COMPLETE", "COLLECTOR_TOPOLOGY", "INCOMPLETE"]
    start: datetime
    end: datetime
    collectors: list[CollectorCoverage]


def _witness(
    payload: dict[str, Any], kind: str, access: AuditEvent, at: datetime
) -> tuple[list[CoverageFailure], datetime | None]:
    if kind == "AUDIT_WINDOWS":
        health = payload.get("audit") or {}
        checks: list[tuple[CoverageFailure, bool]] = [
            ("AUDIT_CONFIGURATION", not health.get("configured")),
            ("AUDIT_POLICY", not health.get("policy_verified")),
            ("AUDIT_SACL", not health.get("sacl_verified")),
            ("AUDIT_GAP", bool(health.get("gap"))),
            ("AUDIT_BACKLOG", bool(health.get("backlog_count"))),
            ("AUDIT_QUARANTINE", bool(health.get("quarantine"))),
            ("AUDIT_ERROR", bool(health.get("error_code"))),
            ("AUDIT_STATE", health.get("state") != "HEALTHY"),
            ("AUDIT_BOOT", health.get("boot_id") != access.boot_id),
            ("AUDIT_GENERATION", health.get("generation") != str(access.generation)),
            ("AUDIT_HOST", health.get("host_id") != str(access.host_id)),
        ]
        failures = [code for code, failed in checks if failed]
        collected = health.get("last_collected_at")
        return failures, datetime.fromisoformat(collected) if collected and not failures else None
    pieces = (payload.get("cursor") or "").split(":")
    failures = []
    if (len(pieces) != 4 or pieces[:2] != ["ntfs-usn", "continuous"]
            or not pieces[2].isascii() or not pieces[2].isdigit()):
        failures.append("USN_CURSOR")
    if payload.get("error_code"):
        failures.append("USN_ERROR")
    if (payload.get("lag_seconds") or 0) > 15:
        failures.append("USN_LAG")
    if failures:
        return failures, None
    try:
        progress = int(pieces[2]) / 1000
    except (ValueError, OverflowError):
        return ["USN_CURSOR"], None
    if not 0 <= at.timestamp() - progress < 15:
        return ["USN_PROOF_AGE"], None
    return [], datetime.fromtimestamp(progress, tz=at.tzinfo)


def coverage_report(
    connection: Connection,
    source: UUID,
    access: AuditEvent,
    at: datetime,
    identity_at: datetime | None = None,
    *, explain: bool = True,
) -> CoverageReport:
    # Two dated witnesses around the historical interval, never current HEALTHY alone.
    start, end = min(access.occurred_at, at) - WINDOW, max(access.occurred_at, at) + WINDOW
    if identity_at is not None:
        start = min(start, identity_at)
    rows = (
        connection.execute(
            select(collectors).where(
                collectors.c.source_node_id == source,
                collectors.c.enabled.is_(True),
                collectors.c.collector_type.in_(["WINDOWS", "AUDIT_WINDOWS"]),
            )
        )
        .mappings()
        .all()
    )
    if sorted(r["collector_type"] for r in rows) != ["AUDIT_WINDOWS", "WINDOWS"]:
        return CoverageReport(False, "COLLECTOR_TOPOLOGY", start, end, [])
    reports: list[CollectorCoverage] = []
    for collector in rows:
        witnesses = (
            connection.execute(
                select(audit_health_observations)
                .where(
                    audit_health_observations.c.collector_id == collector["id"],
                    audit_health_observations.c.occurred_at >= start - timedelta(seconds=120),
                    audit_health_observations.c.occurred_at <= end + timedelta(seconds=120),
                )
                .order_by(audit_health_observations.c.occurred_at)
                .limit(129)
            )
            .mappings()
            .all()
        )
        report = CollectorCoverage(
            collector_type=collector["collector_type"], witness_count=len(witnesses),
            overflow=len(witnesses) > 128,
        )
        reports.append(report)
        if report.overflow:
            report.failures.append("WITNESS_LIMIT")
            if not explain:
                return CoverageReport(False, "INCOMPLETE", start, end, reports)
            continue
        good: list[datetime] = []
        for witness in witnesses:
            failures, proof = _witness(
                witness["payload"], collector["collector_type"], access, witness["occurred_at"]
            )
            if failures and report.first_bad_at is None:
                report.first_bad_at = witness["occurred_at"]
            for failure in failures:
                if failure not in report.failures:
                    report.failures.append(failure)
            if failures and not explain:
                return CoverageReport(False, "INCOMPLETE", start, end, reports)
            if proof is not None:
                good.append(proof)
        if good:
            report.first_proof_at, report.last_proof_at = min(good), max(good)
            report.covers_start, report.covers_end = min(good) <= start, max(good) >= end
        if not report.covers_start:
            report.failures.append("MISSING_START_WITNESS")
        if not report.covers_end:
            report.failures.append("MISSING_END_WITNESS")
        if report.failures and not explain:
            return CoverageReport(False, "INCOMPLETE", start, end, reports)
    passed = all(not report.failures for report in reports)
    return CoverageReport(passed, "COMPLETE" if passed else "INCOMPLETE", start, end, reports)


def coverage(
    connection: Connection, source: UUID, access: AuditEvent, at: datetime,
    identity_at: datetime | None = None,
) -> bool:
    return coverage_report(connection, source, access, at, identity_at, explain=False).passed


def correlate(connection: Connection, change: RowMapping) -> None:
    relative = (
        change["old_relative_path"]
        if change["event_type"] == "DELETE"
        else change["new_relative_path"]
    )
    aliases = (
        connection.execute(
            select(volume_aliases.c.alias)
            .join(volumes, volumes.c.id == volume_aliases.c.volume_id)
            .where(
                volumes.c.source_node_id == change["source_node_id"],
                volumes.c.unique_identity == change["volume_identity"],
                volume_aliases.c.first_seen_at <= change["occurred_at"] - WINDOW,
                volume_aliases.c.last_seen_at >= change["occurred_at"] + WINDOW,
                or_(
                    volume_aliases.c.ended_at.is_(None),
                    volume_aliases.c.ended_at > change["occurred_at"] + WINDOW,
                ),
            )
            .limit(17)
        )
        .scalars()
        .all()
    )
    paths = (
        [a.rstrip("\\/") + "\\" + relative.replace("/", "\\") for a in aliases] if relative else []
    )
    rows = (
        connection.execute(
            candidate_query(
                change["source_node_id"], change["volume_identity"], paths, change["occurred_at"]
            )
        )
        .mappings()
        .all()
    )
    saturated = len(rows) > CANDIDATES or len(aliases) > 16
    rows = list(rows[:CANDIDATES])
    events = [AuditEvent.model_validate(row["payload"]) for row in rows]
    reason, supporting_id = "PATH_TIME_ONLY", None
    proof = False
    proofs: dict[int, tuple[str, UUID | None, bool]] = {}
    queried: set[tuple[Any, ...]] = set()
    for access in list(events):
        reason, supporting_id = identity(connection, change, access, relative or "")
        identity_at = (
            connection.scalar(
                select(audit_identity_observations.c.occurred_at).where(
                    audit_identity_observations.c.id == supporting_id
                )
            )
            if supporting_id
            else None
        )
        proof = coverage(
            connection, change["source_node_id"], access, change["occurred_at"], identity_at
        )
        proofs[access.record_id] = reason, supporting_id, proof
        group = access.host_id, access.generation, access.logon_id, access.sid
        if group in queried:
            continue
        queried.add(group)
        related = (
            connection.execute(
                select(audit_evidence)
                .where(
                    audit_evidence.c.source_node_id == change["source_node_id"],
                    audit_evidence.c.host_id == access.host_id,
                    audit_evidence.c.generation == access.generation,
                    audit_evidence.c.logon_id == str(access.logon_id),
                    audit_evidence.c.sid == access.sid,
                    audit_evidence.c.event_id.in_([4660, 4624]),
                    audit_evidence.c.occurred_at >= access.occurred_at - timedelta(days=1),
                    audit_evidence.c.occurred_at <= access.occurred_at + timedelta(seconds=30),
                )
                .order_by(audit_evidence.c.occurred_at)
                .limit(CANDIDATES + 1)
            )
            .mappings()
            .all()
        )
        saturated |= len(related) > CANDIDATES
        rows.extend(related[:CANDIDATES])
        if len(rows) > 256:
            saturated = True
            rows = rows[:256]
            break
    unique = {row["id"]: row for row in rows}
    events = [AuditEvent.model_validate(row["payload"]) for row in unique.values()]
    decision = decide(
        dict(change),
        events,
        identity_reason=reason,
        coverage=proof,
        saturated=saturated,
        identity_checks={key: value[0] for key, value in proofs.items()},
        coverage_checks={key: value[2] for key, value in proofs.items()},
    )
    actor = decision.actor
    if actor is not None:
        actor["identity_evidence_id"] = str(proofs[decision.supporting_record_id or 0][1])
        actor["logon_id"] = str(actor["logon_id"])
    statement = insert(audit_correlations).values(
        change_event_id=change["id"],
        rule_version=RULE_VERSION,
        **{"class": decision.classification},
        reason=decision.reason,
        actor=actor,
    )
    connection.execute(
        statement.on_conflict_do_update(
            constraint="uq_audit_correlation_change",
            set_={
                "rule_version": RULE_VERSION,
                "class": decision.classification,
                "reason": decision.reason,
                "actor": actor,
                "evaluated_at": func.now(),
            },
        )
    )
    for row in unique.values():
        statement = insert(audit_candidates).values(
            change_event_id=change["id"],
            audit_evidence_id=row["id"],
            rule_version=RULE_VERSION,
            method="SCOPED_SECURITY_USN",
            **{"class": decision.classification},
            reason=decision.reason,
        )
        connection.execute(
            statement.on_conflict_do_update(
                constraint="uq_audit_candidate",
                set_={"class": decision.classification, "reason": decision.reason},
            )
        )


def process(connection: Connection, job: RowMapping) -> None:
    payload: dict[str, Any] = job["payload"]
    receipt = (
        connection.execute(
            select(ingest_batches).where(ingest_batches.c.id == UUID(payload["receipt_id"]))
        )
        .mappings()
        .one()
    )
    source = connection.scalar(
        select(collectors.c.source_node_id).where(collectors.c.id == receipt["collector_id"])
    )
    assert source is not None
    connection.execute(select(func.set_config("lock_timeout", "2s", True)))
    connection.execute(select(func.pg_advisory_xact_lock(lock_key("audit-source:" + str(source)))))
    # Health and inventory close prior windows; bounded historical matching runs
    # for the dated receipt window, not a current-time sweep or synchronous join.
    margin = (
        timedelta(seconds=120)
        if receipt["kind"] in ("changes", "heartbeat", "inventory")
        else WINDOW
    )
    query = select(change_events).where(
        change_events.c.source_node_id == source,
        change_events.c.occurred_at >= receipt["first_event_at"] - margin,
        change_events.c.occurred_at <= receipt["last_event_at"] + margin,
    )
    if "alias_window" in payload:
        window = payload["alias_window"]
        start = datetime.fromisoformat(window["start_at"])
        end = datetime.fromisoformat(window["end_at"])
        if (
            receipt["kind"] != "inventory"
            or start.tzinfo is None
            or end.tzinfo is None
            or start >= end
            or not receipt["first_event_at"] <= end <= receipt["last_event_at"]
        ):
            raise ValueError("INVALID_ALIAS_WINDOW")
        # A later mount witness can close an hour-old interval. Revisit that
        # actual advanced interval only, never sweep unrelated source history.
        query = alias_window_query(
            source,
            window["volume_identity"],
            start,
            end,
            after_at=datetime.fromisoformat(payload["after_at"]) if "after" in payload else None,
            after=UUID(payload["after"]) if "after" in payload else None,
        )
    else:
        if "after" in payload:
            query = query.where(change_events.c.id > UUID(payload["after"]))
        query = query.order_by(change_events.c.id).limit(PAGE + 1)
    rows = connection.execute(query).mappings().all()
    for row in rows[:PAGE]:
        correlate(connection, row)
    if len(rows) > PAGE:
        next_payload = {**payload, "after": str(rows[PAGE - 1]["id"])}
        if "alias_window" in payload:
            next_payload["after_at"] = rows[PAGE - 1]["occurred_at"].isoformat()
        suffix = ":alias:" + str(payload["alias_index"]) if "alias_window" in payload else ""
        enqueue(
            connection,
            "audit_correlate",
            next_payload,
            "audit:" + payload["receipt_id"] + suffix + ":" + next_payload["after"],
        )
