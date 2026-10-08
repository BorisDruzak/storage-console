"""Bounded Activity read model; USN evidence never supplies user attribution."""

import re
from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.engine import Engine, RowMapping

from packages.contracts.changes import EventType
from packages.contracts.read import Activity, ActivityItem
from packages.shared.models.activity import change_events

from .sources import database_time, require_source, snapshot, source_data
from .validity import VALIDITY_HEADER, rows_validity, stamp


def _progress_remaining(cursor: str | None, now: datetime) -> float | None:
    match = re.fullmatch(r"ntfs-usn:continuous:([0-9]{13}):[0-9a-f]{64}", cursor or "")
    if match is None:
        return None
    age = now.timestamp()-int(match[1])/1000
    return 15-age if 0 <= age < 15 else None


def _item(row: RowMapping) -> ActivityItem:
    old, new = row["old_relative_path"], row["new_relative_path"]
    kind = row["event_type"]
    known = (old is not None and new is not None if kind == "RENAME" else
             old is not None if kind == "DELETE" else new is not None)
    source_id = row["source_event_id"]
    return ActivityItem(
        id=row["id"], source_id=row["source_node_id"], object_id=row["object_id"],
        volume_identity=row["volume_identity"], file_id=row["file_id"],
        parent_file_id=row["parent_file_id"], occurred_at=row["occurred_at"], event_type=kind,
        old_relative_path=old, new_relative_path=new, reason_mask=row["reason_mask"],
        source_event_id=source_id,
        provenance="NTFS_USN" if source_id and source_id.startswith("ntfs-usn:") else "UNKNOWN",
        path_quality="COMPLETE" if known else "UNAVAILABLE",
    )


def register(result: APIRouter, engine: Engine) -> None:
    @result.get("/activity")
    def activity(
        response: Response,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0, le=10000)] = 0,
        source_id: UUID | None = None,
        event_type: EventType | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> Activity:
        with snapshot(engine) as connection:
            now = database_time(connection)
            end = end_at or now
            start = start_at or end - timedelta(days=1)
            if (start.tzinfo is None or end.tzinfo is None or start > end
                    or end - start > timedelta(days=31)):
                raise HTTPException(422, detail="INVALID_ACTIVITY_WINDOW")
            data = source_data()
            sources = select(data).where(data.c.source_type == "FILESERVER")
            query = select(change_events).where(
                change_events.c.occurred_at >= start, change_events.c.occurred_at <= end,
            )
            if source_id is not None:
                require_source(connection, source_id)
                query = query.where(change_events.c.source_node_id == source_id)
                sources = sources.where(data.c.id == source_id)
            if event_type is not None:
                query = query.where(change_events.c.event_type == event_type)
            rows = connection.execute(
                query.order_by(change_events.c.occurred_at.desc(), change_events.c.id.desc())
                .limit(limit).offset(offset)
            ).mappings().all()
            source_rows = connection.execute(sources).mappings().all()
            rows_validity(response, source_rows)
            progress = [_progress_remaining(row["cursor"], now) for row in source_rows]
            complete = bool(source_rows) and all(
                row["freshness_state"] == "HEALTHY" and row["collector_count"] == 1
                and remaining is not None
                for row, remaining in zip(source_rows, progress, strict=True)
            )
            if complete:
                stamp(response, int(response.headers[VALIDITY_HEADER])/1000, *progress)
            gap = any((row["cursor"] or "").startswith("ntfs-usn:gap:") for row in source_rows)
            stale = any(row["freshness_state"] in ("OBSERVE", "WARNING", "CRITICAL")
                        for row in source_rows)
            return Activity(
                items=[_item(row) for row in rows],
                total=connection.scalar(select(func.count()).select_from(query.subquery())) or 0,
                limit=limit, offset=offset, evaluated_at=now,
                window_start_at=start, window_end_at=end,
                quality="COMPLETE" if complete else "STALE" if stale else "UNAVAILABLE",
                continuity="CONTINUOUS_SINCE_BASELINE" if complete else "GAP" if gap else "UNKNOWN",
            )
