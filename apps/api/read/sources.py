from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select
from sqlalchemy.engine import Connection, Engine, RowMapping
from sqlalchemy.sql.selectable import CTE

from packages.contracts.read import Freshness, Source
from packages.shared.models.core import collector_heartbeats, collectors, source_nodes
from packages.shared.models.jobs import ingest_batches


@contextmanager
def snapshot(engine: Engine) -> Iterator[Connection]:
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            yield connection


def database_time(connection: Connection) -> datetime:
    return cast(datetime, connection.scalar(select(func.now())))


def source_data() -> CTE:
    batches = (
        select(
            ingest_batches.c.collector_id,
            func.max(ingest_batches.c.last_event_at).label("last_event_at"),
        )
        .group_by(ingest_batches.c.collector_id)
        .subquery()
    )
    heartbeat = select(
        collector_heartbeats.c.collector_id,
        collector_heartbeats.c.cursor,
        collector_heartbeats.c.lag_seconds,
        func.row_number()
        .over(
            partition_by=collector_heartbeats.c.collector_id,
            order_by=(
                collector_heartbeats.c.occurred_at.desc(),
                collector_heartbeats.c.id.desc(),
            ),
        )
        .label("position"),
    ).subquery()
    raw = (
        select(
            collectors.c.id.label("collector_id"),
            collectors.c.source_node_id,
            source_nodes.c.expected_cadence_seconds,
            source_nodes.c.last_success_at,
            collectors.c.last_seen_at.label("last_collector_at"),
            batches.c.last_event_at,
            heartbeat.c.cursor,
            heartbeat.c.lag_seconds,
        )
        .join(source_nodes, source_nodes.c.id == collectors.c.source_node_id)
        .outerjoin(batches, batches.c.collector_id == collectors.c.id)
        .outerjoin(
            heartbeat,
            (heartbeat.c.collector_id == collectors.c.id) & (heartbeat.c.position == 1),
        )
        .where(collectors.c.enabled.is_(True))
        .cte("collector_observations")
    )
    missing = or_(
        raw.c.last_success_at.is_(None),
        raw.c.last_event_at.is_(None),
        raw.c.last_collector_at.is_(None),
    )
    future = or_(
        raw.c.last_success_at > func.now(),
        raw.c.last_event_at > func.now(),
        raw.c.last_collector_at > func.now(),
    )
    age = func.greatest(
        func.extract("epoch", func.now() - raw.c.last_success_at),
        func.extract("epoch", func.now() - raw.c.last_event_at),
        func.extract("epoch", func.now() - raw.c.last_collector_at),
        func.coalesce(raw.c.lag_seconds, 0),
    )
    # Incomplete collector coverage cannot establish source freshness.
    ranked = select(
        raw,
        case(
            (future, 9),
            (missing, 8),
            (age <= raw.c.expected_cadence_seconds, 1),
            (age <= 2 * raw.c.expected_cadence_seconds, 2),
            (age <= 4 * raw.c.expected_cadence_seconds, 3),
            else_=4,
        ).label("rank"),
        case((missing | future, None), else_=age).label("age_seconds"),
    ).cte("collector_freshness")
    worst = select(
        ranked,
        func.count().over(partition_by=ranked.c.source_node_id).label("collector_count"),
        func.count()
        .filter(ranked.c.rank >= 8)
        .over(partition_by=ranked.c.source_node_id)
        .label("unknown_collector_count"),
        func.row_number()
        .over(
            partition_by=ranked.c.source_node_id,
            order_by=(
                ranked.c.rank.desc(),
                ranked.c.age_seconds.desc().nulls_last(),
                ranked.c.collector_id,
            ),
        )
        .label("position"),
    ).subquery()
    return (
        select(
            source_nodes,
            worst.c.last_collector_at,
            worst.c.last_event_at,
            worst.c.cursor,
            worst.c.lag_seconds,
            worst.c.age_seconds,
            worst.c.collector_id.label("bottleneck_collector_id"),
            func.coalesce(worst.c.collector_count, 0).label("collector_count"),
            func.coalesce(worst.c.unknown_collector_count, 0).label("unknown_collector_count"),
            case(
                (worst.c.rank == 1, "HEALTHY"),
                (worst.c.rank == 2, "OBSERVE"),
                (worst.c.rank == 3, "WARNING"),
                (worst.c.rank == 4, "CRITICAL"),
                else_="UNKNOWN",
            ).label("freshness_state"),
            case(
                (worst.c.collector_id.is_(None), "NOT_CONFIGURED"),
                (worst.c.rank == 9, "FUTURE_TIMESTAMP"),
                (worst.c.rank == 8, "NEVER_SEEN"),
                (worst.c.rank == 1, "CURRENT"),
                else_="MISSED_INTERVALS",
            ).label("freshness_reason"),
        )
        .outerjoin(worst, (worst.c.source_node_id == source_nodes.c.id) & (worst.c.position == 1))
        .cte("source_freshness")
    )


def freshness(row: RowMapping) -> Freshness:
    return Freshness.model_validate(
        dict(
            state=row["freshness_state"],
            reason=row["freshness_reason"],
            expected_cadence_seconds=row["expected_cadence_seconds"],
            last_success_at=row["last_success_at"],
            last_event_at=row["last_event_at"],
            last_collector_at=row["last_collector_at"],
            age_seconds=float(row["age_seconds"]) if row["age_seconds"] is not None else None,
            cursor=row["cursor"],
            lag_seconds=row["lag_seconds"],
            collector_count=row["collector_count"],
            unknown_collector_count=row["unknown_collector_count"],
            bottleneck_collector_id=row["bottleneck_collector_id"],
        )
    )


def source(row: RowMapping) -> Source:
    return Source.model_validate(
        dict(
            id=row["id"],
            source_type=row["source_type"],
            hostname=row["hostname"],
            fqdn=row["fqdn"],
            instance_id=row["instance_id"],
            created_at=row["created_at"],
            freshness=freshness(row),
        )
    )


def require_source(connection: Connection, identity: UUID) -> RowMapping:
    data = source_data()
    row = connection.execute(select(data).where(data.c.id == identity)).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, detail="SOURCE_NOT_FOUND")
    return row
