import hashlib
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, insert, select, text, update

from apps.api.main import create_app
from packages.shared.models import metadata
from packages.shared.models.core import (
    collectors,
    filesystem_objects,
    object_path_history,
    source_nodes,
    volume_aliases,
    volumes,
)
from packages.shared.models.jobs import ingest_batches
from packages.shared.settings import Settings

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL required")


@pytest.fixture
def ingest_setup():
    base = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "test_" + uuid4().hex
    with base.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        os.environ["TEST_DATABASE_URL"], connect_args={"options": f"-csearch_path={schema}"}
    )
    metadata.create_all(engine)
    source, collector = uuid4(), uuid4()
    token = secrets.token_urlsafe(32)
    with engine.begin() as connection:
        connection.execute(
            insert(source_nodes).values(
                id=source, source_type="FILESERVER", hostname="synthetic", instance_id=str(source)
            )
        )
        connection.execute(
            insert(collectors).values(
                id=collector,
                source_node_id=source,
                collector_type="WINDOWS",
                token_hash=hashlib.sha256(("collector:" + token).encode()).hexdigest(),
            )
        )
    client = TestClient(create_app(Settings(), engine))
    try:
        yield client, engine, collector, token, source
    finally:
        client.close()
        engine.dispose()
        with base.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


def batch(collector, records, batch_id="synthetic", at=None):
    now = (at or datetime.now(UTC)).isoformat()
    return dict(
        collector_id=str(collector),
        batch_id=batch_id,
        schema_version=1,
        sent_at=now,
        first_event_at=now,
        last_event_at=now,
        record_count=len(records),
        records=[dict(occurred_at=now, **r) for r in records],
    )


def test_ingest_auth_and_replay_boundary(ingest_setup):
    client, engine, collector, token, source = ingest_setup
    payload = batch(collector, [dict(version="test")])
    route = "/api/v1/ingest/heartbeat"
    assert client.post(route, json=payload).status_code == 401
    assert (
        client.post(route, json=payload, headers={"Authorization": "Bearer wrong"}).status_code
        == 401
    )
    headers = {"Authorization": "Bearer " + token}
    assert (
        client.post(
            route, json=dict(payload, collector_id=str(uuid4())), headers=headers
        ).status_code
        == 401
    )
    assert client.post(route, json=payload, headers=headers).json()["duplicate"] is False
    assert client.post(route, json=payload, headers=headers).json()["duplicate"] is True
    changed = dict(payload, records=[dict(payload["records"][0], version="changed")])
    assert client.post(route, json=changed, headers=headers).status_code == 409
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(ingest_batches)) == 1
        assert (
            connection.scalar(
                select(source_nodes.c.last_success_at).where(source_nodes.c.id == source)
            )
            is not None
        )


def test_concurrent_upload_commits_one_batch(ingest_setup):
    client, engine, collector, token, _ = ingest_setup
    payload = batch(collector, [dict(version="test")])

    def upload(_):
        return client.post(
            "/api/v1/ingest/heartbeat", json=payload, headers={"Authorization": "Bearer " + token}
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(upload, range(2)))
    assert [r.status_code for r in responses] == [202, 202]
    assert sorted(r.json()["duplicate"] for r in responses) == [False, True]
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(ingest_batches)) == 1


def test_inventory_batch_rolls_back_and_preserves_identity(ingest_setup):
    client, engine, collector, token, _ = ingest_setup
    headers = {"Authorization": "Bearer " + token}
    records = [
        dict(kind="volume", unique_identity="v", filesystem="NTFS", mount_aliases=["X:"]),
        dict(
            kind="object",
            volume_identity="missing",
            file_id="42",
            object_type="FILE",
            name="Report",
            relative_path="Dept/Report",
        ),
    ]
    assert (
        client.post(
            "/api/v1/ingest/inventory", json=batch(collector, records), headers=headers
        ).status_code
        == 409
    )
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(volumes)) == 0
        assert connection.scalar(select(func.count()).select_from(ingest_batches)) == 0
    records[1]["volume_identity"] = "v"
    assert (
        client.post(
            "/api/v1/ingest/inventory", json=batch(collector, records), headers=headers
        ).status_code
        == 202
    )
    changes = [
        dict(
            volume_identity="v",
            file_id="42",
            event_type="RENAME",
            old_relative_path="Dept/Report",
            new_relative_path="Dept/New",
        )
    ]
    assert (
        client.post(
            "/api/v1/ingest/changes", json=batch(collector, changes, "rename"), headers=headers
        ).status_code
        == 202
    )
    changes = [dict(volume_identity="v", file_id="42", event_type="DELETE")]
    assert (
        client.post(
            "/api/v1/ingest/changes", json=batch(collector, changes, "delete"), headers=headers
        ).status_code
        == 202
    )
    with engine.connect() as connection:
        row = connection.execute(select(filesystem_objects)).one()
        assert row.current_relative_path == "Dept/New"
        assert row.deleted_at.tzinfo is not None
        paths = connection.execute(select(object_path_history.c.relative_path)).scalars().all()
        assert set(paths) == {"Dept/Report", "Dept/New"}
    records = [dict(kind="volume", unique_identity="v", filesystem="NTFS", mount_aliases=["Y:"])]
    assert (
        client.post(
            "/api/v1/ingest/inventory", json=batch(collector, records, "alias"), headers=headers
        ).status_code
        == 202
    )
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(volumes)) == 1
        aliases = connection.execute(select(volume_aliases)).mappings().all()
        assert {row["alias"] for row in aliases} == {"X:", "Y:"}
        assert {row["alias"] for row in aliases if row["ended_at"] is None} == {"Y:"}


def test_disabled_and_user_credentials_cannot_ingest(ingest_setup):
    from packages.shared.models.security import users

    client, engine, collector, token, _ = ingest_setup
    payload = batch(collector, [dict(version="test")])
    user_token = secrets.token_urlsafe(32)
    with engine.begin() as connection:
        connection.execute(
            insert(users).values(
                username="synthetic",
                auth_provider="local",
                password_hash=hashlib.sha256(user_token.encode()).hexdigest(),
            )
        )
        connection.execute(
            update(collectors).where(collectors.c.id == collector).values(enabled=False)
        )
    for credential in [user_token, token]:
        assert (
            client.post(
                "/api/v1/ingest/heartbeat",
                json=payload,
                headers={"Authorization": "Bearer " + credential},
            ).status_code
            == 401
        )
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(ingest_batches)) == 0


def test_mount_reassignment_closes_old_binding_and_ignores_late_observation(ingest_setup):
    client, engine, collector, token, _ = ingest_setup
    at = datetime.now(UTC)
    headers = {"Authorization": "Bearer " + token}
    observations = [
        ("volume-a", at),
        ("volume-b", at + timedelta(seconds=2)),
        ("volume-a", at + timedelta(seconds=1)),
    ]
    for index, (identity, time) in enumerate(observations):
        payload = batch(
            collector,
            [
                dict(
                    kind="volume", unique_identity=identity, filesystem="NTFS", mount_aliases=["X:"]
                )
            ],
            str(index),
            at=time,
        )
        assert (
            client.post("/api/v1/ingest/inventory", json=payload, headers=headers).status_code
            == 202
        )
    with engine.connect() as connection:
        active = (
            connection.execute(
                select(volumes.c.unique_identity)
                .join(volume_aliases)
                .where(
                    volume_aliases.c.alias == "X:",
                    volume_aliases.c.ended_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        assert active == ["volume-b"]
        assert connection.scalar(select(func.count()).select_from(volume_aliases)) == 2
    observations = [
        ("volume-b", [], at + timedelta(seconds=3)),
        ("volume-a", ["X:"], at + timedelta(seconds=1, microseconds=1)),
    ]
    for index, (identity, aliases, time) in enumerate(observations):
        payload = batch(
            collector,
            [
                dict(
                    kind="volume",
                    unique_identity=identity,
                    filesystem="NTFS",
                    mount_aliases=aliases,
                )
            ],
            f"released-{index}",
            at=time,
        )
        assert (
            client.post("/api/v1/ingest/inventory", json=payload, headers=headers).status_code
            == 202
        )
    with engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(volume_aliases)
                .where(
                    volume_aliases.c.ended_at.is_(None),
                )
            )
            == 0
        )
