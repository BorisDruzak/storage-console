"""Synthetic inventory refresh must preserve history with bounded database work."""

import os
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, insert, select

from packages.contracts.changes import ChangeRecord
from packages.contracts.inventory import FileObjectRecord, VolumeRecord
from packages.shared.ingest import paths
from packages.shared.ingest.core import change, inventory
from packages.shared.models.core import (
    filesystem_objects,
    object_path_history,
    object_path_states,
    source_nodes,
    volumes,
)

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL required")


def test_unchanged_single_path_inventory_has_bounded_sql_and_keeps_history(ingest_setup):
    _, engine, _, _, source = ingest_setup
    at = datetime.now(UTC)
    records = [
        FileObjectRecord(
            occurred_at=at,
            volume_identity="synthetic-volume",
            file_id=str(i),
            object_type="FILE",
            name=f"Report{i}",
            relative_path=f"Dept/Report{i}",
            size_bytes=39,
            link_count=1,
        )
        for i in range(20)
    ]
    with engine.begin() as connection:
        inventory(
            connection,
            source,
            VolumeRecord(occurred_at=at, unique_identity="synthetic-volume", filesystem="NTFS"),
        )
        for record in records:
            inventory(connection, source, record)
        before = connection.execute(select(object_path_history)).mappings().all()
    sql = []

    def count(_conn, _cursor, statement, _parameters, _context, _many):
        sql.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    started = time.monotonic()
    try:
        with engine.begin() as connection:
            for record in records:
                inventory(
                    connection,
                    source,
                    record.model_copy(update={"occurred_at": at + timedelta(hours=1)}),
                )
    finally:
        event.remove(engine, "before_cursor_execute", count)
    with engine.connect() as connection:
        after = connection.execute(select(object_path_history)).mappings().all()
        seen = connection.execute(select(filesystem_objects.c.last_seen_at)).scalars().all()
    assert sorted(before, key=lambda r: str(r["id"])) == sorted(after, key=lambda r: str(r["id"]))
    assert all(value == at + timedelta(hours=1) for value in seen)
    print({"objects": 20, "sql_count": len(sql), "elapsed_seconds": time.monotonic() - started})
    assert len(sql) <= 5 * len(records)


@pytest.mark.parametrize(
    "scenario",
    [
        "stable",
        "size",
        "rename",
        "multiple",
        "older",
        "parent",
        "partial_rename",
        "late_end",
        "equal_rename",
        "delayed_partial",
        "delete_reuse",
    ],
)
def test_refresh_has_same_dated_state_as_general_reconciliation(
    ingest_setup, monkeypatch, scenario
):
    _, engine, _, _, first = ingest_setup
    second = uuid4()
    at = datetime.now(UTC)
    initial = FileObjectRecord(
        occurred_at=at,
        volume_identity="v",
        file_id="42",
        object_type="FILE",
        name="Report",
        relative_path="Dept/Report",
        size_bytes=39,
        link_count=1,
    )
    delta = {"occurred_at": at + timedelta(hours=1)}
    delta.update(
        {
            "size": {"size_bytes": 40},
            "rename": {"name": "New", "relative_path": "Dept/New"},
            "multiple": {"link_count": 2},
            "older": {"occurred_at": at - timedelta(hours=1)},
            "parent": {"parent_file_id": "another-parent"},
        }.get(scenario, {})
    )
    later = initial.model_copy(update=delta)
    with engine.begin() as connection:
        connection.execute(
            insert(source_nodes).values(
                id=second,
                source_type="FILESERVER",
                hostname="synthetic-comparison",
                instance_id=str(second),
            )
        )
        for source in (first, second):
            inventory(
                connection,
                source,
                VolumeRecord(
                    occurred_at=at,
                    unique_identity="v",
                    filesystem="NTFS",
                ),
            )
            inventory(connection, source, initial)
            if scenario == "partial_rename":
                change(
                    connection,
                    source,
                    ChangeRecord(
                        occurred_at=at + timedelta(minutes=30),
                        volume_identity="v",
                        file_id="42",
                        event_type="RENAME",
                        new_relative_path="Dept/Other",
                        path_quality="UNAVAILABLE",
                    ),
                )
        inventory(connection, first, later)
        with monkeypatch.context() as patch:
            patch.setattr(paths, "refresh_single", lambda *_: False)
            inventory(connection, second, later)
        if scenario in ("late_end", "equal_rename", "delayed_partial", "delete_reuse"):
            for source in (first, second):
                followup = ChangeRecord(
                    occurred_at=at + timedelta(minutes=60 if scenario == "equal_rename" else 30),
                    volume_identity="v",
                    file_id="42",
                    event_type="DELETE" if scenario == "delete_reuse" else "RENAME",
                    old_relative_path=(
                        None if scenario in ("delayed_partial", "delete_reuse") else "Dept/Report"
                    ),
                    new_relative_path=None if scenario == "delete_reuse" else "Dept/New",
                    path_quality="UNAVAILABLE",
                )
                change(connection, source, followup)
                if scenario == "delete_reuse":
                    inventory(
                        connection,
                        source,
                        initial.model_copy(
                            update={
                                "occurred_at": at + timedelta(hours=2),
                            }
                        ),
                    )

        def snapshot(source):
            volume = connection.scalar(
                select(volumes.c.id).where(
                    volumes.c.source_node_id == source,
                )
            )
            obj = (
                connection.execute(
                    select(filesystem_objects).where(
                        filesystem_objects.c.volume_id == volume,
                    )
                )
                .mappings()
                .one()
            )
            history = (
                connection.execute(
                    select(object_path_history)
                    .where(
                        object_path_history.c.object_id == obj["id"],
                    )
                    .order_by(
                        object_path_history.c.relative_path, object_path_history.c.valid_from_at
                    )
                )
                .mappings()
                .all()
            )
            states = (
                connection.execute(
                    select(object_path_states)
                    .where(
                        object_path_states.c.object_id == obj["id"],
                    )
                    .order_by(object_path_states.c.relative_path)
                )
                .mappings()
                .all()
            )
            return {
                "object": {k: v for k, v in obj.items() if k not in ("id", "volume_id")},
                "history": [
                    {k: v for k, v in r.items() if k not in ("id", "object_id")} for r in history
                ],
                "states": [
                    {
                        **{
                            k: v
                            for k, v in r.items()
                            if k not in ("id", "object_id", "active_history_id")
                        },
                        "active": r["active_history_id"] is not None,
                    }
                    for r in states
                ],
            }

        assert snapshot(first) == snapshot(second)
