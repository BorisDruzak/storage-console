import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from collectors.common.delivery import Delivery
from collectors.common.outbox import Outbox
from collectors.common.transport import Transport
from collectors.windows.inventory import Observation, Scope
from collectors.windows.native import NativeInventory
from collectors.windows.producer import capture_heartbeat, capture_inventory
from packages.contracts.inventory import FileObjectRecord, VolumeRecord
from packages.shared.models.core import (
    collector_heartbeats,
    filesystem_objects,
    object_path_history,
    volumes,
)
from packages.shared.models.jobs import ingest_batches
from tests.deployment.collector_delivery import serving_ingest

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL required")


@dataclass
class Setup:
    client: TestClient
    engine: Engine
    collector: UUID
    token: str = field(repr=False)


@pytest.fixture
def inventory_setup(authenticated_setup):
    client, engine, collector, token, _ = authenticated_setup
    return Setup(client, engine, collector, token)


def counts(engine):
    with engine.connect() as connection:
        return tuple(
            connection.scalar(select(func.count()).select_from(table))
            for table in [
                ingest_batches,
                volumes,
                filesystem_objects,
                object_path_history,
                collector_heartbeats,
            ]
        )


def replay_and_drain(box, transport, now):
    claim = box.claim(now)
    initial = transport.send(claim)
    assert initial.kind == "accepted" and not initial.duplicate
    # Lose only the local ACK after the real API committed. Reopen the durable state.
    before = claim.body
    reopened = Outbox(box.path, box.collector_id)
    replay = reopened.claim(now + timedelta(seconds=61))
    assert replay.body == before and replay.batch_id == claim.batch_id
    duplicate = transport.send(replay)
    assert duplicate.kind == "accepted" and duplicate.duplicate
    assert reopened.acknowledge(replay)
    delivery = Delivery(reopened, transport, clock=lambda: now + timedelta(seconds=61))
    accepted = 0
    while reopened.status().pending_count:
        assert delivery.run_once().state == "accepted"
        accepted += 1
    return accepted


def test_generated_inventory_and_heartbeat_real_https_replay(inventory_setup, tmp_path):
    setup = inventory_setup
    now = datetime.now(UTC)
    scope = Scope(("C:\\synthetic",))
    provider = iter(
        [
            Observation(
                record=VolumeRecord(
                    occurred_at=now, unique_identity="synthetic-volume", filesystem="NTFS"
                )
            ),
            Observation(
                record=FileObjectRecord(
                    occurred_at=now,
                    volume_identity="synthetic-volume",
                    file_id="synthetic-object",
                    object_type="FILE",
                    name="synthetic.txt",
                    relative_path="synthetic\\synthetic.txt",
                    size_bytes=9,
                )
            ),
        ]
    )
    box = Outbox(tmp_path / "state" / "outbox.db", setup.collector)
    report = capture_inventory(box, scope, provider, max_records=1)
    assert report.completed and report.records == 2 and report.batches == 2
    capture_heartbeat(box)
    with serving_ingest(setup.client.app, tmp_path / "tls") as (origin, ca):
        transport = Transport(origin, ca, setup.token, collector_id=setup.collector)
        assert replay_and_drain(box, transport, datetime.now(UTC)) == 2
    assert counts(setup.engine) == (3, 1, 1, 1, 1)
    with setup.engine.connect() as connection:
        row = connection.execute(select(collector_heartbeats)).mappings().one()
        assert row["version"] == "0.1.0" and row["cursor"] is None and row["lag_seconds"] is None


def test_error_only_capture_heartbeat_is_unknown_until_successful_recovery(
    inventory_setup, tmp_path
):
    setup = inventory_setup
    box = Outbox(tmp_path / "state" / "outbox.db", setup.collector)
    report = capture_inventory(
        box, Scope(("C:\\synthetic",)), iter([Observation(error_code="ACCESS_DENIED")])
    )
    assert not report.completed and not report.records
    capture_heartbeat(box, error_code=report.errors[0])
    with serving_ingest(setup.client.app, tmp_path / "tls") as (origin, ca):
        delivery = Delivery(box, Transport(origin, ca, setup.token, collector_id=setup.collector))
        assert delivery.run_once().state == "accepted"
        with setup.engine.connect() as connection:
            from apps.api.read.sources import source_data

            failed = connection.execute(select(source_data())).mappings().one()
            assert failed["freshness_state"] == "UNKNOWN"
            assert failed["freshness_reason"] == "COLLECTION_ERROR"
            assert failed["unknown_collector_count"] == 1
        capture_heartbeat(box)
        assert delivery.run_once().state == "accepted"
    with setup.engine.connect() as connection:
        recovered = connection.execute(select(source_data())).mappings().one()
        assert recovered["freshness_state"] == "HEALTHY"
        assert recovered["freshness_reason"] == "CURRENT"


@pytest.mark.skipif(os.name != "nt", reason="Actual native Windows capture")
def test_multilink_scans_preserve_paths_and_unlink_one_closes_only_that_alias(
    inventory_setup, tmp_path
):
    setup = inventory_setup
    root = tmp_path / "capture"
    root.mkdir()
    first = root / "first.txt"
    first.write_bytes(b"synthetic")
    second = root / "second.txt"
    os.link(first, second)
    scope = Scope((str(root),))
    box = Outbox(tmp_path / "state" / "outbox.db", setup.collector)
    with serving_ingest(setup.client.app, tmp_path / "tls") as (origin, ca):
        delivery = Delivery(box, Transport(origin, ca, setup.token, collector_id=setup.collector))
        for _ in range(2):
            report = capture_inventory(box, scope, NativeInventory().scan(scope))
            assert report.completed and not report.errors
            assert report.records == 4
            capture_heartbeat(box)
            while box.status().pending_count:
                assert delivery.run_once().state == "accepted"
        assert counts(setup.engine) == (4, 1, 2, 3, 2)
        with setup.engine.connect() as connection:
            before = (
                connection.execute(
                    select(object_path_history)
                    .join(filesystem_objects)
                    .where(filesystem_objects.c.object_type == "FILE")
                )
                .mappings()
                .all()
            )
            assert len(before) == 2 and all(row["valid_until_at"] is None for row in before)
            file_id = connection.scalar(
                select(filesystem_objects.c.file_id).where(
                    filesystem_objects.c.object_type == "FILE"
                )
            )
        second.unlink()
        report = capture_inventory(box, scope, NativeInventory().scan(scope))
        assert report.completed and report.records == 3 and not report.errors
        capture_heartbeat(box)
        while box.status().pending_count:
            assert delivery.run_once().state == "accepted"
    assert counts(setup.engine) == (6, 1, 2, 3, 3)
    with setup.engine.connect() as connection:
        after = (
            connection.execute(
                select(object_path_history)
                .join(filesystem_objects)
                .where(filesystem_objects.c.object_type == "FILE")
            )
            .mappings()
            .all()
        )
        active = [row for row in after if row["valid_until_at"] is None]
        assert len(active) == 1 and active[0]["relative_path"].endswith("\\first.txt")
        obj = (
            connection.execute(
                select(filesystem_objects).where(filesystem_objects.c.object_type == "FILE")
            )
            .mappings()
            .one()
        )
        assert obj["file_id"] == file_id and obj["link_count"] == 1
        assert obj["deleted_at"] is None


@pytest.mark.skipif(os.name != "nt", reason="Actual native Windows capture")
def test_native_capture_real_ingest_and_rename_preserve_object_identity(inventory_setup, tmp_path):
    setup = inventory_setup
    root = tmp_path / "capture"
    root.mkdir()
    folder = root / "folder"
    folder.mkdir()
    leaf = root / "Отчёт😀.txt"
    leaf.write_bytes(b"synthetic")
    (folder / "nested.txt").write_bytes(b"other-synthetic")
    scope = Scope((str(root),))
    box = Outbox(tmp_path / "state" / "outbox.db", setup.collector)
    report = capture_inventory(box, scope, NativeInventory().scan(scope), max_records=2)
    assert report.completed and report.records == 5 and report.batches == 3 and not report.errors
    capture_heartbeat(box)
    with serving_ingest(setup.client.app, tmp_path / "tls") as (origin, ca):
        transport = Transport(origin, ca, setup.token, collector_id=setup.collector)
        assert replay_and_drain(box, transport, datetime.now(UTC)) == 3
        assert counts(setup.engine) == (4, 1, 4, 4, 1)
        with setup.engine.connect() as connection:
            old = connection.execute(
                select(filesystem_objects.c.id, filesystem_objects.c.file_id).where(
                    filesystem_objects.c.current_name == leaf.name
                )
            ).one()
        renamed = leaf.with_name("renamed.txt")
        leaf.rename(renamed)
        second = capture_inventory(box, scope, NativeInventory().scan(scope), max_records=2)
        assert second.completed and second.records == 5 and second.batches == 3
        capture_heartbeat(box)
        assert replay_and_drain(box, transport, datetime.now(UTC)) == 3
    assert counts(setup.engine) == (8, 1, 4, 5, 2)
    with setup.engine.connect() as connection:
        new = connection.execute(
            select(
                filesystem_objects.c.id,
                filesystem_objects.c.file_id,
                filesystem_objects.c.size_bytes,
            ).where(filesystem_objects.c.current_name == "renamed.txt")
        ).one()
        assert new[:2] == old and new.size_bytes == 9


@pytest.mark.skipif(os.name != "nt", reason="Actual native Windows capture")
def test_link_created_before_old_metadata_publication_survives_real_https_ingest(
    inventory_setup, tmp_path, monkeypatch
):
    setup = inventory_setup
    root = tmp_path / "capture"
    root.mkdir()
    first, second = root / "first.txt", root / "second.txt"
    first.write_bytes(b"synthetic")
    real_record = NativeInventory._record
    peer = None

    def record(path, metadata, parent):
        nonlocal peer
        if not metadata.directory and metadata.link_count == 1 and peer is None:
            os.link(first, second)
            newer = list(NativeInventory().scan(Scope((str(root),))))
            assert not [value.error_code for value in newer if value.error_code]
            peer = next(
                value.record
                for value in newer
                if value.record
                and value.record.kind == "object"
                and value.record.name == second.name
            )
        return real_record(path, metadata, parent)

    monkeypatch.setattr(NativeInventory, "_record", staticmethod(record))
    scope = Scope((str(root),))
    captured = list(NativeInventory().scan(scope))
    assert not [value.error_code for value in captured if value.error_code]
    volume = next(value.record for value in captured if value.record.kind == "volume")
    older = next(
        value.record
        for value in captured
        if value.record.kind == "object" and value.record.name == first.name
    )
    assert peer is not None
    assert older.link_count == 1 and peer.link_count == 2
    assert older.occurred_at < peer.occurred_at
    box = Outbox(tmp_path / "state" / "outbox.db", setup.collector)
    # Deliver the independently observed newer alias before the older single-link proof.
    report = capture_inventory(
        box,
        scope,
        iter([Observation(record=volume), Observation(record=peer), Observation(record=older)]),
    )
    assert report.completed and report.records == 3
    with serving_ingest(setup.client.app, tmp_path / "tls") as (origin, ca):
        assert (
            replay_and_drain(
                box,
                Transport(origin, ca, setup.token, collector_id=setup.collector),
                datetime.now(UTC),
            )
            == 0
        )
    assert counts(setup.engine) == (1, 1, 1, 2, 0)
    with setup.engine.connect() as connection:
        rows = connection.execute(select(object_path_history)).mappings().all()
        assert len(rows) == 2 and all(row["valid_until_at"] is None for row in rows)
        obj = connection.execute(select(filesystem_objects)).mappings().one()
        assert obj["file_id"] == older.file_id == peer.file_id
        assert obj["link_count"] == 2 and obj["link_count_at"] == peer.occurred_at
