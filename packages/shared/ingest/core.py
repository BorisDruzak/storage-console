from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from packages.contracts.changes import ChangeRecord
from packages.contracts.inventory import FileObjectRecord, ShareRecord, VolumeRecord
from packages.shared.models.activity import change_events
from packages.shared.models.core import (
    filesystem_objects,
    object_path_history,
    shares,
    volume_aliases,
    volumes,
)


class IngestConflict(Exception):
    """A bounded machine conflict; never exposes SQL or collector data."""


def volume_id(connection: Connection, source: UUID, identity: str) -> UUID:
    result = connection.scalar(
        select(volumes.c.id).where(
            volumes.c.source_node_id == source,
            volumes.c.unique_identity == identity,
        )
    )
    if result is None:
        raise IngestConflict("UNKNOWN_VOLUME")
    return cast(UUID, result)


def inventory(
    connection: Connection, source: UUID, record: VolumeRecord | ShareRecord | FileObjectRecord
) -> None:
    if isinstance(record, VolumeRecord):
        existing = (
            connection.execute(
                select(volumes).where(
                    volumes.c.source_node_id == source,
                    volumes.c.unique_identity == record.unique_identity,
                )
            )
            .mappings()
            .one_or_none()
        )
        values: dict[str, object] = dict(
            filesystem=record.filesystem,
            label=record.label,
            total_bytes=record.total_bytes,
            free_bytes=record.free_bytes,
            last_seen_at=record.occurred_at,
        )
        if existing is None:
            target = connection.scalar(
                insert(volumes)
                .values(
                    source_node_id=source,
                    unique_identity=record.unique_identity,
                    first_seen_at=record.occurred_at,
                    **values,
                )
                .returning(volumes.c.id)
            )
        else:
            if record.occurred_at < existing["last_seen_at"]:
                return
            target = existing["id"]
            connection.execute(update(volumes).where(volumes.c.id == target).values(**values))
        active = (
            connection.execute(
                select(volume_aliases).where(
                    volume_aliases.c.volume_id == target,
                    volume_aliases.c.ended_at.is_(None),
                )
            )
            .mappings()
            .all()
        )
        active_names = {row["alias"] for row in active}
        for row in active:
            alias_values = dict(last_seen_at=record.occurred_at)
            if row["alias"] not in record.mount_aliases:
                alias_values["ended_at"] = record.occurred_at
            connection.execute(
                update(volume_aliases)
                .where(volume_aliases.c.id == row["id"])
                .values(**alias_values)
            )
        for alias in set(record.mount_aliases) - active_names:
            others = (
                connection.execute(
                    select(volume_aliases)
                    .join(volumes)
                    .where(
                        volumes.c.source_node_id == source,
                        volume_aliases.c.volume_id != target,
                        volume_aliases.c.alias == alias,
                    )
                )
                .mappings()
                .all()
            )
            if any(
                max(row["last_seen_at"], row["ended_at"] or row["last_seen_at"])
                > record.occurred_at
                for row in others
            ):
                continue
            for row in others:
                if row["ended_at"] is not None:
                    continue
                connection.execute(
                    update(volume_aliases)
                    .where(
                        volume_aliases.c.id == row["id"],
                    )
                    .values(ended_at=record.occurred_at)
                )
            connection.execute(
                insert(volume_aliases).values(
                    volume_id=target,
                    alias=alias,
                    first_seen_at=record.occurred_at,
                    last_seen_at=record.occurred_at,
                )
            )
    elif isinstance(record, ShareRecord):
        target_volume = (
            volume_id(connection, source, record.volume_identity)
            if (record.volume_identity is not None)
            else None
        )
        existing = (
            connection.execute(
                select(shares).where(
                    shares.c.source_node_id == source,
                    shares.c.name == record.name,
                )
            )
            .mappings()
            .one_or_none()
        )
        values = dict(
            volume_id=target_volume,
            relative_path=record.relative_path,
            protocol=record.protocol,
            last_seen_at=record.occurred_at,
        )
        if existing is None:
            connection.execute(
                insert(shares).values(source_node_id=source, name=record.name, **values)
            )
        elif record.occurred_at >= existing["last_seen_at"]:
            connection.execute(update(shares).where(shares.c.id == existing["id"]).values(**values))
    else:
        target_volume = volume_id(connection, source, record.volume_identity)
        existing = (
            connection.execute(
                select(filesystem_objects).where(
                    filesystem_objects.c.volume_id == target_volume,
                    filesystem_objects.c.file_id == record.file_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        values = dict(
            parent_file_id=record.parent_file_id,
            object_type=record.object_type,
            current_name=record.name,
            current_relative_path=record.relative_path,
            size_bytes=record.size_bytes,
            last_seen_at=record.occurred_at,
            deleted_at=None,
        )
        if existing is None:
            target = connection.scalar(
                insert(filesystem_objects)
                .values(
                    volume_id=target_volume,
                    file_id=record.file_id,
                    first_seen_at=record.occurred_at,
                    **values,
                )
                .returning(filesystem_objects.c.id)
            )
            connection.execute(
                insert(object_path_history).values(
                    object_id=target,
                    relative_path=record.relative_path,
                    valid_from_at=record.occurred_at,
                )
            )
        elif record.occurred_at >= existing["last_seen_at"]:
            if existing["current_relative_path"] != record.relative_path:
                change_path(connection, existing["id"], record.relative_path, record.occurred_at)
            connection.execute(
                update(filesystem_objects)
                .where(filesystem_objects.c.id == existing["id"])
                .values(**values)
            )


def change_path(connection: Connection, target: UUID, path: str, at: datetime) -> None:
    connection.execute(
        update(object_path_history)
        .where(
            object_path_history.c.object_id == target,
            object_path_history.c.valid_until_at.is_(None),
        )
        .values(valid_until_at=at)
    )
    connection.execute(
        insert(object_path_history).values(object_id=target, relative_path=path, valid_from_at=at)
    )


def change(connection: Connection, source: UUID, record: ChangeRecord) -> None:
    existing = (
        connection.execute(
            select(filesystem_objects)
            .join(volumes)
            .where(
                volumes.c.source_node_id == source,
                volumes.c.unique_identity == record.volume_identity,
                filesystem_objects.c.file_id == record.file_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    connection.execute(
        insert(change_events).values(
            source_node_id=source,
            object_id=existing["id"] if existing else None,
            **record.model_dump(),
        )
    )
    if existing is None or record.occurred_at < existing["last_seen_at"]:
        return
    values: dict[str, object] = dict(last_seen_at=record.occurred_at)
    if record.event_type == "DELETE":
        values["deleted_at"] = record.occurred_at
    elif record.event_type == "RENAME":
        path = record.new_relative_path
        assert path is not None
        if path != existing["current_relative_path"]:
            change_path(connection, existing["id"], path, record.occurred_at)
        values.update(
            current_relative_path=path,
            current_name=path.replace("\\", "/").rsplit("/", 1)[-1],
            parent_file_id=record.parent_file_id,
        )
    connection.execute(
        update(filesystem_objects).where(filesystem_objects.c.id == existing["id"]).values(**values)
    )
