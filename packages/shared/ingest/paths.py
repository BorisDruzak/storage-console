"""Dated path evidence; caller owns the source lock and transaction."""

from datetime import datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import Connection, RowMapping

from packages.shared.models.core import filesystem_objects, object_path_history, object_path_states

from .errors import IngestConflict


def digest(path: str) -> str:
    return sha256(path.encode()).hexdigest()


def _object(connection: Connection, target: UUID) -> RowMapping:
    return (
        connection.execute(select(filesystem_objects).where(filesystem_objects.c.id == target))
        .mappings()
        .one()
    )


def _state(connection: Connection, target: UUID, path: str) -> RowMapping:
    key = digest(path)
    row = (
        connection.execute(
            select(object_path_states).where(
                object_path_states.c.object_id == target, object_path_states.c.path_digest == key
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is not None:
        if row["relative_path"] != path:
            raise IngestConflict("PATH_DIGEST_CONFLICT")
        return row
    return (
        connection.execute(
            insert(object_path_states)
            .values(object_id=target, relative_path=path, path_digest=key)
            .returning(object_path_states)
        )
        .mappings()
        .one()
    )


def observe(
    connection: Connection,
    target: UUID,
    path: str,
    at: datetime,
    *,
    name: str | None,
    parent_file_id: str | None,
    legacy_tie: bool = False,
) -> None:
    row = _state(connection, target, path)
    obj = _object(connection, target)
    values: dict[str, object] = {}
    if row["seen_at"] is None or at >= row["seen_at"]:
        values.update(seen_at=at, name=name, parent_file_id=parent_file_id)
    inferred_end = row["ended_at"]
    if legacy_tie and inferred_end == at:
        inferred_end = None
    boundaries = [inferred_end, row["event_ended_at"], obj["last_deleted_at"]]
    if obj["sole_path_digest"] != row["path_digest"]:
        boundaries.append(obj["sole_path_at"])
    boundary = max((value for value in boundaries if value is not None), default=None)
    if boundary is None or at > boundary:
        if row["active_history_id"] is None:
            history = connection.scalar(
                insert(object_path_history)
                .values(object_id=target, relative_path=path, valid_from_at=at)
                .returning(object_path_history.c.id)
            )
            values["active_history_id"] = history
        else:
            connection.execute(
                update(object_path_history)
                .where(
                    object_path_history.c.id == row["active_history_id"],
                    object_path_history.c.valid_from_at > at,
                )
                .values(valid_from_at=at)
            )
    if values:
        connection.execute(
            update(object_path_states).where(object_path_states.c.id == row["id"]).values(**values)
        )


def _end_matching(connection: Connection, target: UUID, at: datetime, keep: str | None) -> None:
    condition = (
        (object_path_states.c.object_id == target)
        & (object_path_states.c.active_history_id.is_not(None))
        & (object_path_states.c.seen_at <= at)
    )
    if keep is not None:
        condition &= object_path_states.c.path_digest != keep
    connection.execute(
        update(object_path_history)
        .where(
            object_path_history.c.id.in_(
                select(object_path_states.c.active_history_id).where(condition)
            )
        )
        .values(valid_until_at=at)
    )
    connection.execute(
        update(object_path_states).where(condition).values(active_history_id=None, ended_at=at)
    )


def end(connection: Connection, target: UUID, path: str, at: datetime) -> None:
    row = _state(connection, target, path)
    if row["event_ended_at"] is not None and row["event_ended_at"] > at:
        return
    values: dict[str, object] = dict(event_ended_at=at)
    if row["ended_at"] is None or row["ended_at"] <= at:
        values["ended_at"] = at
    if row["active_history_id"] is not None and row["seen_at"] <= at:
        connection.execute(
            update(object_path_history)
            .where(object_path_history.c.id == row["active_history_id"])
            .values(valid_until_at=at)
        )
        values["active_history_id"] = None
    connection.execute(
        update(object_path_states).where(object_path_states.c.id == row["id"]).values(**values)
    )


def sole(
    connection: Connection, target: UUID, path: str, at: datetime, *, strict: bool = True
) -> None:
    row = _state(connection, target, path)
    obj = _object(connection, target)
    if obj["sole_path_at"] is not None and obj["sole_path_at"] > at:
        return
    if strict and obj["sole_path_at"] == at and obj["sole_path_digest"] != row["path_digest"]:
        raise IngestConflict("SOLE_PATH_CONFLICT")
    connection.execute(
        update(filesystem_objects)
        .where(filesystem_objects.c.id == target)
        .values(sole_path_digest=row["path_digest"], sole_path_at=at)
    )
    _end_matching(connection, target, at, row["path_digest"])


def delete(connection: Connection, target: UUID, at: datetime) -> None:
    obj = _object(connection, target)
    if obj["last_deleted_at"] is not None and obj["last_deleted_at"] > at:
        return
    connection.execute(
        update(filesystem_objects)
        .where(filesystem_objects.c.id == target)
        .values(last_deleted_at=at)
    )
    _end_matching(connection, target, at, None)


def representative(connection: Connection, target: UUID) -> None:
    obj = _object(connection, target)
    row = (
        connection.execute(
            select(object_path_states)
            .join(
                object_path_history,
                object_path_states.c.active_history_id == object_path_history.c.id,
            )
            .where(object_path_states.c.object_id == target)
            .order_by(
                (object_path_states.c.relative_path == obj["current_relative_path"]).desc(),
                object_path_history.c.valid_from_at,
                object_path_history.c.id,
            )
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        latest_positive = connection.scalar(
            select(func.max(object_path_states.c.seen_at)).where(
                object_path_states.c.object_id == target
            )
        )
        deleted = obj["last_deleted_at"]
        if deleted is not None and latest_positive is not None and latest_positive > deleted:
            deleted = None
        values: dict[str, object] = dict(deleted_at=deleted)
    else:
        values = dict(
            current_relative_path=row["relative_path"],
            current_name=row["name"] or row["relative_path"].replace("\\", "/").rsplit("/", 1)[-1],
            parent_file_id=row["parent_file_id"],
            deleted_at=None,
        )
    connection.execute(
        update(filesystem_objects).where(filesystem_objects.c.id == target).values(**values)
    )
