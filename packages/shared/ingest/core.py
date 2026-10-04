from typing import cast
from uuid import UUID

from sqlalchemy import insert, select, tuple_, update
from sqlalchemy.engine import Connection

from packages.contracts.changes import ChangeRecord
from packages.contracts.inventory import FileObjectRecord, ShareRecord, VolumeRecord
from packages.shared.models.activity import change_events
from packages.shared.models.core import (
    filesystem_objects,
    shares,
    volume_aliases,
    volumes,
)

from . import paths
from .errors import IngestConflict as IngestConflict


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
        if (
            existing is not None
            and record.link_count is None
            and not existing["multiple_paths_observed"]
            and record.occurred_at < existing["last_seen_at"]
        ):
            return
        values = dict(
            object_type=record.object_type,
            size_bytes=record.size_bytes,
            last_seen_at=record.occurred_at,
        )
        if existing is None:
            target = connection.scalar(
                insert(filesystem_objects)
                .values(
                    volume_id=target_volume,
                    file_id=record.file_id,
                    first_seen_at=record.occurred_at,
                    parent_file_id=record.parent_file_id,
                    current_name=record.name,
                    current_relative_path=record.relative_path,
                    **values,
                )
                .returning(filesystem_objects.c.id)
            )
            target = cast(UUID, target)
            multiple = False
            count_at = None
        else:
            target = existing["id"]
            multiple = existing["multiple_paths_observed"]
            count_at = existing["link_count_at"]
            if record.occurred_at < existing["first_seen_at"]:
                connection.execute(
                    update(filesystem_objects)
                    .where(filesystem_objects.c.id == target)
                    .values(first_seen_at=record.occurred_at)
                )
            if record.occurred_at >= existing["last_seen_at"]:
                connection.execute(
                    update(filesystem_objects)
                    .where(filesystem_objects.c.id == target)
                    .values(**values)
                )
        if record.link_count is not None:
            count_values: dict[str, object] = {}
            if count_at is None or record.occurred_at >= count_at:
                count_values.update(link_count=record.link_count, link_count_at=record.occurred_at)
            if record.link_count > 1:
                multiple = True
                count_values["multiple_paths_observed"] = True
            if count_values:
                connection.execute(
                    update(filesystem_objects)
                    .where(filesystem_objects.c.id == target)
                    .values(**count_values)
                )
        if record.link_count == 1 or (record.link_count is None and not multiple):
            paths.sole(
                connection,
                target,
                record.relative_path,
                record.occurred_at,
                strict=record.link_count is not None,
            )
        paths.observe(
            connection,
            target,
            record.relative_path,
            record.occurred_at,
            name=record.name,
            parent_file_id=record.parent_file_id,
            legacy_tie=record.link_count is None and not multiple,
        )
        if existing is None:
            _hydrate_changes(connection, source, target, record)
        paths.representative(connection, target)


def _hydrate_changes(
    connection: Connection, source: UUID, target: UUID, record: FileObjectRecord
) -> None:
    condition = (
        (change_events.c.source_node_id == source)
        & (change_events.c.volume_identity == record.volume_identity)
        & (change_events.c.file_id == record.file_id)
        & (change_events.c.object_id.is_(None))
    )
    latest = record.occurred_at
    cursor = None
    while True:
        page = select(change_events).where(condition)
        if cursor is not None:
            page = page.where(tuple_(change_events.c.occurred_at, change_events.c.id) > cursor)
        rows = (
            connection.execute(
                page.order_by(change_events.c.occurred_at, change_events.c.id).limit(256)
            )
            .mappings()
            .all()
        )
        if not rows:
            break
        for row in rows:
            event = ChangeRecord.model_validate(
                {key: row[key] for key in ChangeRecord.model_fields}
            )
            _path_change(connection, target, event)
            latest = max(latest, event.occurred_at)
        last = rows[-1]
        cursor = (last["occurred_at"], last["id"])
    if latest > record.occurred_at:
        connection.execute(
            update(filesystem_objects)
            .where(filesystem_objects.c.id == target)
            .values(last_seen_at=latest)
        )


def _path_change(connection: Connection, target: UUID, record: ChangeRecord) -> None:
    if record.event_type == "DELETE":
        if record.old_relative_path is None:
            paths.delete(connection, target, record.occurred_at)
        else:
            paths.end(connection, target, record.old_relative_path, record.occurred_at)
    elif record.event_type == "RENAME":
        old, new = record.old_relative_path, record.new_relative_path
        assert old is not None and new is not None
        if old != new:
            paths.end(connection, target, old, record.occurred_at)
        paths.observe(
            connection,
            target,
            new,
            record.occurred_at,
            name=new.replace("\\", "/").rsplit("/", 1)[-1],
            parent_file_id=record.parent_file_id,
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
    if existing is None:
        return
    _path_change(connection, existing["id"], record)
    if record.occurred_at >= existing["last_seen_at"]:
        connection.execute(
            update(filesystem_objects)
            .where(filesystem_objects.c.id == existing["id"])
            .values(last_seen_at=record.occurred_at)
        )
    paths.representative(connection, existing["id"])
