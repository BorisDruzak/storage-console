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
