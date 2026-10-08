import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, create_engine, func, insert, select, text
from sqlalchemy.engine import make_url

from packages.contracts.changes import ChangeRecord
from packages.contracts.inventory import FileObjectRecord, VolumeRecord
from packages.shared.ingest.core import change, inventory
from packages.shared.models.core import filesystem_objects, object_path_history, object_path_states

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"
)


@pytest.fixture
def migration_setup(monkeypatch):
    base = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "migration_alias_" + uuid4().hex
    with base.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(os.environ["TEST_DATABASE_URL"]).update_query_dict(
        {"options": f"-csearch_path={schema}"}
    )
    engine = create_engine(url)
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    config = Config("alembic.ini")
    try:
        command.upgrade(config, "0004")
        yield engine, config
    finally:
        engine.dispose()
        with base.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


@pytest.mark.parametrize("deleted", [False, True])
@pytest.mark.parametrize("old_path", [None, "a/x"])
def test_existing_paths_and_deleted_watermarks_survive_upgrade(migration_setup, deleted, old_path):
    engine, config = migration_setup
    old = MetaData()
    old.reflect(engine)
    source, volume, target, interval = (uuid4() for _ in range(4))
    at = datetime(2026, 1, 1, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(old.tables["source_nodes"]).values(
                id=source, source_type="FILESERVER", hostname="synthetic", instance_id=str(source)
            )
        )
        connection.execute(
            insert(old.tables["volumes"]).values(
                id=volume,
                source_node_id=source,
                unique_identity="v",
                filesystem="NTFS",
                first_seen_at=at,
                last_seen_at=at,
            )
        )
        connection.execute(
            insert(old.tables["filesystem_objects"]).values(
                id=target,
                volume_id=volume,
                file_id="42",
                object_type="FILE",
                current_name="x",
                current_relative_path="a/x",
                parent_file_id="a",
                first_seen_at=at,
                last_seen_at=at + timedelta(seconds=10),
                deleted_at=at + timedelta(seconds=10) if deleted else None,
            )
        )
        connection.execute(
            insert(old.tables["object_path_history"]).values(
                id=interval, object_id=target, relative_path="a/x", valid_from_at=at
            )
        )
        connection.execute(
            insert(old.tables["change_events"]).values(
                id=uuid4(),
                source_node_id=source,
                object_id=target,
                volume_identity="v",
                file_id="42",
                event_type="DELETE",
                old_relative_path=old_path,
                occurred_at=at + timedelta(seconds=5),
            )
        )
    command.upgrade(config, "head")
    command.check(config)

    with engine.connect() as connection:
        obj = connection.execute(select(filesystem_objects)).mappings().one()
        state = connection.execute(select(object_path_states)).mappings().one()
        history = (
            connection.execute(
                select(object_path_history).order_by(object_path_history.c.valid_from_at)
            )
            .mappings()
            .all()
        )
    assert obj["id"] == target
    assert obj["last_deleted_at"] == at + timedelta(seconds=10 if deleted else 5)
    assert state["relative_path"] == "a/x"
    assert (state["active_history_id"] is None) == deleted
    assert state["parent_file_id"] == "a"
    assert history[0]["id"] == interval
    assert history[0]["valid_until_at"] == at + timedelta(seconds=10 if deleted else 5)
    if not deleted:
        assert len(history) == 2
        assert history[1]["id"] == state["active_history_id"]
        assert history[1]["valid_from_at"] == at + timedelta(seconds=10)
        assert history[1]["valid_until_at"] is None
    command.downgrade(config, "0004")
    command.upgrade(config, "head")
    command.check(config)


def test_backfill_crosses_keyset_pages_and_refuses_lossy_downgrade(migration_setup):
    engine, config = migration_setup
    old = MetaData()
    old.reflect(engine)
    source, volume, target, active = (uuid4() for _ in range(4))
    at = datetime(2026, 1, 1, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(old.tables["source_nodes"]).values(
                id=source, source_type="FILESERVER", hostname="synthetic", instance_id=str(source)
            )
        )
        connection.execute(
            insert(old.tables["volumes"]).values(
                id=volume,
                source_node_id=source,
                unique_identity="v",
                filesystem="NTFS",
                first_seen_at=at,
                last_seen_at=at,
            )
        )
        connection.execute(
            insert(old.tables["filesystem_objects"]).values(
                id=target,
                volume_id=volume,
                file_id="42",
                object_type="FILE",
                current_name="x",
                current_relative_path="active/x",
                first_seen_at=at,
                last_seen_at=at + timedelta(seconds=20),
            )
        )
        connection.execute(
            insert(old.tables["object_path_history"]),
            [
                dict(
                    id=uuid4(),
                    object_id=target,
                    relative_path=f"old/{n}",
                    valid_from_at=at,
                    valid_until_at=at + timedelta(seconds=10),
                )
                for n in range(513)
            ]
            + [
                dict(
                    id=active,
                    object_id=target,
                    relative_path="active/x",
                    valid_from_at=at,
                    valid_until_at=None,
                )
            ],
        )
    command.upgrade(config, "head")
    command.check(config)
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(object_path_history)) == 514
        assert connection.scalar(select(func.count()).select_from(object_path_states)) == 514
        state = (
            connection.execute(
                select(object_path_states).where(object_path_states.c.active_history_id == active)
            )
            .mappings()
            .one()
        )
        assert state["seen_at"] == at + timedelta(seconds=20)
    from packages.shared.ingest import paths

    with engine.begin() as connection:
        paths.observe(
            connection,
            target,
            "second/x",
            at + timedelta(seconds=30),
            name="x",
            parent_file_id=None,
        )
    with pytest.raises(RuntimeError, match="SIMULTANEOUS_PATHS_REQUIRE_COMPATIBLE_ROLLBACK"):
        command.downgrade(config, "0004")
    command.check(config)
    with engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(object_path_states)
                .where(object_path_states.c.active_history_id.is_not(None))
            )
            == 2
        )


@pytest.mark.parametrize("has_inventory", [False, True])
def test_new_path_only_deletion_refuses_destructive_legacy_round_trip(
    migration_setup, has_inventory
):
    engine, config = migration_setup
    old = MetaData()
    old.reflect(engine)
    source, volume, target = (uuid4() for _ in range(3))
    at = datetime(2026, 1, 1, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(old.tables["source_nodes"]).values(
                id=source, source_type="FILESERVER", hostname="synthetic", instance_id=str(source)
            )
        )
        if has_inventory:
            connection.execute(
                insert(old.tables["volumes"]).values(
                    id=volume,
                    source_node_id=source,
                    unique_identity="v",
                    filesystem="NTFS",
                    first_seen_at=at,
                    last_seen_at=at,
                )
            )
            connection.execute(
                insert(old.tables["filesystem_objects"]).values(
                    id=target,
                    volume_id=volume,
                    file_id="42",
                    object_type="FILE",
                    current_name="x",
                    current_relative_path="a/x",
                    first_seen_at=at,
                    last_seen_at=at,
                )
            )
            connection.execute(
                insert(old.tables["object_path_history"]).values(
                    id=uuid4(),
                    object_id=target,
                    relative_path="a/x",
                    valid_from_at=at,
                )
            )
    command.upgrade(config, "head")
    from packages.shared.ingest import paths

    with engine.begin() as connection:
        if has_inventory:
            paths.observe(
                connection, target, "b/x", at + timedelta(seconds=1), name="x", parent_file_id=None
            )
        change(
            connection,
            source,
            ChangeRecord(
                volume_identity="v",
                file_id="42",
                event_type="DELETE",
                old_relative_path="b/x",
                occurred_at=at + timedelta(seconds=2),
            ),
        )
    with pytest.raises(RuntimeError, match="PATH_DELETIONS_REQUIRE_COMPATIBLE_ROLLBACK"):
        command.downgrade(config, "0004")
    command.upgrade(config, "head")
    command.check(config)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0006"
        if has_inventory:
            obj = connection.execute(select(filesystem_objects)).mappings().one()
            assert obj["deleted_at"] is None and obj["current_relative_path"] == "a/x"
            active = (
                connection.execute(
                    select(object_path_states.c.relative_path).where(
                        object_path_states.c.active_history_id.is_not(None)
                    )
                )
                .scalars()
                .all()
            )
            assert active == ["a/x"]


@pytest.mark.parametrize("legacy", [False, True])
def test_first_inventory_hydration_preserves_legacy_delete_semantics(migration_setup, legacy):
    engine, config = migration_setup
    old = MetaData()
    old.reflect(engine)
    source = uuid4()
    at = datetime(2026, 1, 1, tzinfo=UTC)
    event = ChangeRecord(
        volume_identity="v",
        file_id="42",
        event_type="DELETE",
        old_relative_path="a/x",
        occurred_at=at + timedelta(seconds=10),
    )
    with engine.begin() as connection:
        connection.execute(
            insert(old.tables["source_nodes"]).values(
                id=source, source_type="FILESERVER", hostname="synthetic", instance_id=str(source)
            )
        )
        if legacy:
            connection.execute(
                insert(old.tables["change_events"]).values(
                    id=uuid4(),
                    source_node_id=source,
                    **event.model_dump(),
                )
            )
    command.upgrade(config, "head")
    with engine.begin() as connection:
        if not legacy:
            change(connection, source, event)
        inventory(
            connection,
            source,
            VolumeRecord(
                unique_identity="v", filesystem="NTFS", occurred_at=at + timedelta(seconds=1)
            ),
        )
        inventory(
            connection,
            source,
            FileObjectRecord(
                volume_identity="v",
                file_id="42",
                object_type="FILE",
                name="x",
                relative_path="b/x",
                link_count=2,
                occurred_at=at + timedelta(seconds=1),
            ),
        )
    with engine.connect() as connection:
        obj = connection.execute(select(filesystem_objects)).mappings().one()
        active = (
            connection.execute(
                select(object_path_states.c.relative_path).where(
                    object_path_states.c.active_history_id.is_not(None)
                )
            )
            .scalars()
            .all()
        )
    assert obj["deleted_at"] == (event.occurred_at if legacy else None)
    assert active == ([] if legacy else ["b/x"])
