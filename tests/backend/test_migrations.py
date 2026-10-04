import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.engine import make_url

from packages.shared.models.authorization import acl_aces, acl_snapshots
from packages.shared.models.core import source_nodes, volumes
from packages.shared.models.recovery import backup_jobs, backup_snapshots, vss_snapshots
from packages.shared.models.security import roles, user_roles, users


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required")
def test_existing_recovery_rows_survive_evidence_migration(monkeypatch):
    base = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "migration_test_" + uuid4().hex
    with base.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(os.environ["TEST_DATABASE_URL"]).update_query_dict(
        {"options": f"-csearch_path={schema}"}
    )
    engine = create_engine(url)
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    config = Config("alembic.ini")
    try:
        command.upgrade(config, "0002")
        at = datetime.now(UTC)
        source, volume = uuid4(), uuid4()
        with engine.begin() as connection:
            connection.execute(
                insert(source_nodes).values(
                    id=source,
                    source_type="FILESERVER",
                    hostname="synthetic",
                    instance_id=str(source),
                )
            )
            connection.execute(
                insert(volumes).values(
                    id=volume, source_node_id=source, unique_identity="v", filesystem="NTFS"
                )
            )
            connection.execute(
                insert(vss_snapshots).values(
                    volume_id=volume, snapshot_identity="s", created_at=at, state="AVAILABLE"
                )
            )
            job_id = connection.scalar(
                insert(backup_jobs)
                .values(
                    source_node_id=source,
                    job_identity="j",
                    workload_identity="vm",
                    state="COMPLETE",
                    started_at=at,
                    finished_at=at,
                )
                .returning(backup_jobs.c.id)
            )
            connection.execute(
                insert(backup_snapshots).values(
                    backup_job_id=job_id,
                    snapshot_identity="backup-s",
                    created_at=at,
                    consistency="UNKNOWN",
                )
            )
            snapshot_id = connection.scalar(
                insert(acl_snapshots)
                .values(
                    source_node_id=source,
                    scope_identity="synthetic",
                    dacl_fingerprint="a" * 64,
                    inheritance_enabled=True,
                    observed_at=at,
                )
                .returning(acl_snapshots.c.id)
            )
            for kind in ["ALLOW", "DENY"]:
                connection.execute(
                    insert(acl_aces).values(
                        snapshot_id=snapshot_id,
                        unresolved_sid="synthetic",
                        ace_type=kind,
                        access_mask=1,
                        inherited=False,
                    )
                )
        command.upgrade(config, "head")
        command.check(config)
        for table in [vss_snapshots, backup_jobs, backup_snapshots]:
            with engine.connect() as connection:
                assert connection.execute(select(table)).one().observed_at == at
        with engine.connect() as connection:
            assert connection.execute(select(acl_aces.c.ordinal)).scalars().all() == [None, None]
        command.downgrade(config, "0002")
        command.upgrade(config, "head")
        command.check(config)
    finally:
        engine.dispose()
        with base.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required")
def test_auth_upgrade_preserves_existing_user_and_role_assignment(monkeypatch):
    base = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "migration_test_" + uuid4().hex
    with base.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(os.environ["TEST_DATABASE_URL"]).update_query_dict(
        {"options": f"-csearch_path={schema}"}
    )
    engine = create_engine(url)
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    config = Config("alembic.ini")
    user, role = uuid4(), uuid4()
    try:
        command.upgrade(config, "0003")
        with engine.begin() as connection:
            # Historical schema has no enabled column yet.
            connection.execute(
                text(
                    "INSERT INTO users (id, username, auth_provider) VALUES (:id, :name, 'local')"
                ),
                {"id": user, "name": "synthetic-existing"},
            )
            connection.execute(insert(roles).values(id=role, code="storage_admin"))
            connection.execute(insert(user_roles).values(user_id=user, role_id=role))
        for _ in range(2):
            command.upgrade(config, "head")
            command.check(config)
            with engine.connect() as connection:
                assert connection.scalar(select(users.c.enabled).where(users.c.id == user)) is True
                assert set(connection.scalars(select(roles.c.code))) == {
                    "storage_admin",
                    "storage_operator",
                    "auditor",
                    "analyst",
                    "viewer",
                }
                assert connection.scalar(select(user_roles.c.role_id)) == role
            command.downgrade(config, "0003")
        command.upgrade(config, "head")
    finally:
        engine.dispose()
        with base.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()
