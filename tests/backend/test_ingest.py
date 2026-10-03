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


@pytest.mark.parametrize(
    "route,table,record",
    [
        (
            "telemetry",
            "metric_samples_1m",
            dict(metric_name="capacity.free", value=50, unit="bytes"),
        ),
        (
            "events",
            "collector_events",
            dict(
                source_event_id="synthetic-4663",
                evidence_type="WINDOWS_4663",
                actor_identity="synthetic-actor",
                confidence=0.7,
            ),
        ),
        (
            "acl",
            "acl_snapshots",
            dict(
                scope_identity="Dept",
                dacl_fingerprint="a" * 64,
                owner_identity="synthetic-owner",
                inheritance_enabled=True,
                aces=[
                    dict(
                        principal_identity="synthetic-principal",
                        ace_type="ALLOW",
                        access_mask=1,
                        inherited=True,
                    )
                ],
            ),
        ),
        (
            "recovery",
            "vss_snapshots",
            dict(kind="vss", volume_identity="v", snapshot_identity="snapshot", state="AVAILABLE"),
        ),
        (
            "hygiene",
            "hygiene_snapshots",
            dict(
                scope_identity="Dept",
                quality="PARTIAL",
                file_count=1,
                directory_count=1,
                total_bytes=10,
                zero_byte_count=0,
            ),
        ),
        (
            "diagnostic-bundles",
            "diagnostic_bundles",
            dict(trigger_type="LATENCY", sha256="b" * 64, status="METADATA_ONLY"),
        ),
    ],
)
def test_domain_ingest_persists_metadata_and_replays_once(ingest_setup, route, table, record):
    client, engine, collector, token, source = ingest_setup
    at = datetime.now(UTC)
    headers = {"Authorization": "Bearer " + token}
    assert (
        client.post(
            "/api/v1/ingest/inventory",
            headers=headers,
            json=batch(
                collector,
                [dict(kind="volume", unique_identity="v", filesystem="NTFS")],
                "volume",
                at,
            ),
        ).status_code
        == 202
    )
    record = dict(record)
    if route == "recovery":
        record["created_at"] = at.isoformat()
    if route == "diagnostic-bundles":
        record.update(first_event_at=at.isoformat(), last_event_at=at.isoformat())
    payload = batch(collector, [record], route, at)
    response = client.post("/api/v1/ingest/" + route, headers=headers, json=payload)
    assert response.status_code == 202, response.text
    assert (
        client.post("/api/v1/ingest/" + route, headers=headers, json=payload).json()["duplicate"]
        is True
    )
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(metadata.tables[table])) == 1
        assert (
            connection.scalar(select(func.count()).select_from(metadata.tables["health_findings"]))
            == 0
        )
        if route == "events":
            row = connection.execute(select(metadata.tables[table])).mappings().one()
            assert row["source_node_id"] == source
            assert row["actor_identity"] == "synthetic-actor"
            assert row["confidence"] == 0.7
        if route == "acl":
            assert (
                connection.scalar(select(func.count()).select_from(metadata.tables["acl_aces"]))
                == 1
            )


def test_event_link_requires_same_source_and_rejection_is_atomic(ingest_setup):
    from packages.shared.models.activity import (
        change_events,
        collector_events,
        event_evidence_links,
    )

    client, engine, collector, token, source = ingest_setup
    headers = {"Authorization": "Bearer " + token}
    other, foreign, own = uuid4(), uuid4(), uuid4()
    at = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(source_nodes).values(
                id=other,
                source_type="FILESERVER",
                hostname="synthetic-other",
                instance_id=str(other),
            )
        )
        for identity, node in [(foreign, other), (own, source)]:
            connection.execute(
                insert(change_events).values(
                    id=identity,
                    source_node_id=node,
                    volume_identity="unresolved",
                    file_id="42",
                    event_type="WRITE",
                    occurred_at=at,
                )
            )
    records = [
        dict(source_event_id="one", evidence_type="WINDOWS_4663", confidence=0.5),
        dict(
            source_event_id="two",
            evidence_type="WINDOWS_4660",
            confidence=0.8,
            change_event_id=str(foreign),
        ),
    ]
    assert (
        client.post(
            "/api/v1/ingest/events", headers=headers, json=batch(collector, records)
        ).status_code
        == 409
    )
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(collector_events)) == 0
        assert connection.scalar(select(func.count()).select_from(ingest_batches)) == 0
    records[1]["change_event_id"] = str(own)
    assert (
        client.post(
            "/api/v1/ingest/events", headers=headers, json=batch(collector, records)
        ).status_code
        == 202
    )
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(collector_events)) == 2
        assert connection.scalar(select(func.count()).select_from(event_evidence_links)) == 1
        assert (
            connection.scalar(
                select(func.count()).select_from(metadata.tables["event_attributions"])
            )
            == 0
        )


def test_backup_keeps_verification_restore_and_newer_job_state(ingest_setup):
    from packages.shared.models.recovery import (
        backup_jobs,
        backup_snapshots,
        backup_verifications,
        restore_tests,
    )

    client, engine, collector, token, _ = ingest_setup
    headers = {"Authorization": "Bearer " + token}
    at = datetime.now(UTC)
    start = (at - timedelta(seconds=60)).isoformat()
    record = dict(
        kind="backup",
        job_identity="job",
        workload_identity="workload",
        state="COMPLETE",
        started_at=start,
        finished_at=(at - timedelta(seconds=20)).isoformat(),
        snapshot_identity="snapshot",
        snapshot_created_at=(at - timedelta(seconds=40)).isoformat(),
        consistency="VSS_QUIESCED",
        verification_state="COMPLETE",
        verified_at=at.isoformat(),
        restore_test_state="FAILED",
        tested_at=at.isoformat(),
        measured_rto_seconds=12,
    )
    payload = batch(collector, [record], "complete", at)
    assert client.post("/api/v1/ingest/recovery", json=payload, headers=headers).status_code == 202
    assert client.post("/api/v1/ingest/recovery", json=payload, headers=headers).json()["duplicate"]
    late = dict(
        kind="backup",
        job_identity="job",
        workload_identity="workload",
        state="RUNNING",
        started_at=start,
    )
    assert (
        client.post(
            "/api/v1/ingest/recovery",
            json=batch(collector, [late], "late", at - timedelta(seconds=10)),
            headers=headers,
        ).status_code
        == 202
    )
    with engine.connect() as connection:
        assert connection.execute(select(backup_jobs)).one().state == "COMPLETE"
        assert connection.execute(select(backup_snapshots)).one().consistency == "VSS_QUIESCED"
        assert connection.execute(select(backup_verifications)).one().state == "COMPLETE"
        restore = connection.execute(select(restore_tests)).one()
        assert restore.state == "FAILED"
        assert restore.measured_rto_seconds == 12


def test_hygiene_child_metadata_is_preserved(ingest_setup):
    client, engine, collector, token, _ = ingest_setup
    at = datetime.now(UTC)
    record = dict(
        scope_identity="Dept",
        quality="PARTIAL",
        file_count=5,
        directory_count=1,
        total_bytes=100,
        zero_byte_count=2,
        long_paths=[dict(relative_path="synthetic-long-path", path_length=240, bucket="240+")],
        large_files=[dict(relative_path="large", size_bytes=100, last_write_at=at.isoformat())],
        temp_artifacts=[dict(classification="STALE", file_count=2, total_bytes=20)],
    )
    assert (
        client.post(
            "/api/v1/ingest/hygiene",
            headers={"Authorization": "Bearer " + token},
            json=batch(collector, [record], at=at),
        ).status_code
        == 202
    )
    with engine.connect() as connection:
        stats = connection.execute(select(metadata.tables["scope_stats"])).one()
        assert stats.zero_byte_count == 2
        for table in ["long_path_samples", "large_file_samples", "temp_artifact_stats"]:
            assert connection.scalar(select(func.count()).select_from(metadata.tables[table])) == 1


def test_acl_preserves_ace_order(ingest_setup):
    client, engine, collector, token, _ = ingest_setup
    record = dict(
        scope_identity="Dept",
        dacl_fingerprint="c" * 64,
        inheritance_enabled=True,
        aces=[
            dict(principal_identity="same-principal", ace_type=kind, access_mask=1, inherited=False)
            for kind in ["DENY", "ALLOW"]
        ],
    )
    assert (
        client.post(
            "/api/v1/ingest/acl",
            headers={"Authorization": "Bearer " + token},
            json=batch(collector, [record]),
        ).status_code
        == 202
    )
    aces = metadata.tables["acl_aces"]
    with engine.connect() as connection:
        rows = connection.execute(select(aces).order_by(aces.c.ordinal)).all()
        assert [row.ace_type for row in rows] == ["DENY", "ALLOW"]
        assert [row.ordinal for row in rows] == [0, 1]


def test_snapshot_ordering_is_independent_of_other_snapshots_in_job(ingest_setup):
    client, engine, collector, token, _ = ingest_setup
    at = datetime.now(UTC)
    records = [("a", "UNKNOWN", 20), ("b", "UNKNOWN", 10), ("a", "VSS_QUIESCED", 15)]
    for index, (identity, consistency, lag) in enumerate(records):
        record = dict(
            kind="backup",
            job_identity="same-job",
            workload_identity="vm",
            state="COMPLETE",
            started_at=(at - timedelta(seconds=100)).isoformat(),
            finished_at=(at - timedelta(seconds=60)).isoformat(),
            snapshot_identity=identity,
            snapshot_created_at=(at - timedelta(seconds=80)).isoformat(),
            consistency=consistency,
        )
        assert (
            client.post(
                "/api/v1/ingest/recovery",
                headers={"Authorization": "Bearer " + token},
                json=batch(collector, [record], str(index), at - timedelta(seconds=lag)),
            ).status_code
            == 202
        )
    snapshots = metadata.tables["backup_snapshots"]
    with engine.connect() as connection:
        row = connection.execute(
            select(snapshots).where(snapshots.c.snapshot_identity == "a")
        ).one()
        assert row.consistency == "VSS_QUIESCED"
