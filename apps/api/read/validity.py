from collections.abc import Sequence
from datetime import datetime
from math import floor

from fastapi import Response
from sqlalchemy import func, select
from sqlalchemy.engine import Connection, RowMapping

from .inventory import inventory_validity
from .overview import domain_validity
from .sources import source_data

VALIDITY_HEADER = "X-Evidence-Valid-For-Ms"
MAX_VALIDITY_SECONDS = 35


def stamp(response: Response, *seconds: float | None) -> None:
    remaining = min([MAX_VALIDITY_SECONDS, *(value for value in seconds if value is not None)])
    response.headers[VALIDITY_HEADER] = str(max(0, floor(remaining * 1000)))
    # A cached HTTP response must never acquire a fresh relative lifetime.
    response.headers["Cache-Control"] = "no-store"


def source_validity(connection: Connection) -> float | None:
    data = source_data()
    value = connection.scalar(select(func.min(data.c.next_change_seconds)))
    return float(value) if value is not None else None


def overview_validity(
    connection: Connection, response: Response, now: datetime, stale_seconds: int
) -> None:
    stamp(
        response,
        source_validity(connection),
        domain_validity(connection),
        inventory_validity(connection, now, stale_seconds),
    )


def rows_validity(response: Response, rows: Sequence[RowMapping]) -> None:
    stamp(
        response,
        *(
            float(row["next_change_seconds"])
            for row in rows
            if row["next_change_seconds"] is not None
        ),
    )


def storage_validity(
    response: Response, rows: Sequence[RowMapping], now: datetime, stale_seconds: int
) -> None:
    remaining = [
        stale_seconds - (now - row["last_seen_at"]).total_seconds()
        if row["last_seen_at"] <= now
        else (row["last_seen_at"] - now).total_seconds()
        for row in rows
    ]
    stamp(response, *(value for value in remaining if value >= 0))
