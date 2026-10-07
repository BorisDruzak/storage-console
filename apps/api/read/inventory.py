"""Inventory read summaries; measured capacity never establishes domain health."""

from datetime import datetime
from typing import cast

from sqlalchemy import Numeric, and_, case, func, select
from sqlalchemy.engine import Connection

from packages.contracts.read import CapacityState, CapacitySummary, InventorySummary
from packages.shared.models.core import volumes


def summaries(
    connection: Connection, now: datetime, stale_seconds: int, object_count: int
) -> tuple[CapacitySummary, InventorySummary]:
    current = and_(
        volumes.c.last_seen_at <= now,
        func.extract("epoch", now - volumes.c.last_seen_at) <= stale_seconds,
    )
    usable = and_(current, volumes.c.total_bytes > 0, volumes.c.free_bytes.is_not(None))
    # Numeric arithmetic avoids bigint overflow and division rounding at thresholds.
    used_percent = (
        (volumes.c.total_bytes.cast(Numeric) - volumes.c.free_bytes)
        * 100
        / func.nullif(volumes.c.total_bytes, 0)
    )
    rank = case(
        (used_percent >= 90, 4),
        (used_percent >= 80, 3),
        (used_percent >= 70, 2),
        else_=1,
    )
    row = (
        connection.execute(
            select(
                func.count().label("volume_count"),
                func.count().filter(usable).label("current_count"),
                func.sum(volumes.c.total_bytes).filter(usable).label("total"),
                func.sum(volumes.c.free_bytes).filter(usable).label("free"),
                func.max(rank).filter(usable).label("worst"),
                func.max(volumes.c.last_seen_at).filter(usable).label("capacity_at"),
                func.max(volumes.c.last_seen_at)
                .filter(volumes.c.last_seen_at <= now)
                .label("inventory_at"),
            )
        )
        .mappings()
        .one()
    )
    total = int(row["total"]) if row["total"] is not None else None
    free = int(row["free"]) if row["free"] is not None else None
    used = total - free if total is not None and free is not None else None
    states = ("UNKNOWN", "HEALTHY", "OBSERVE", "WARNING", "CRITICAL")
    capacity = CapacitySummary(
        state=cast(CapacityState, states[row["worst"] or 0]),
        total_bytes=total,
        free_bytes=free,
        used_bytes=used,
        used_percent=used * 100 / total if used is not None and total else None,
        volume_count=row["volume_count"],
        current_volume_count=row["current_count"],
        unavailable_volume_count=row["volume_count"] - row["current_count"],
        latest_inventory_at=row["capacity_at"],
    )
    filesystems = list(
        connection.scalars(select(volumes.c.filesystem).distinct().order_by(volumes.c.filesystem))
    )
    return capacity, InventorySummary(
        latest_inventory_at=row["inventory_at"],
        volume_count=row["volume_count"],
        filesystem_types=filesystems,
        filesystem_objects=object_count,
    )


def inventory_validity(connection: Connection, now: datetime, stale_seconds: int) -> float | None:
    age = func.extract("epoch", now - volumes.c.last_seen_at)
    remaining = case((age < 0, -age), else_=stale_seconds - age)
    value = connection.scalar(select(func.min(remaining)).where(remaining >= 0))
    return float(value) if value is not None else None
