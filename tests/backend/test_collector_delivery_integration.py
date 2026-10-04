import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from collectors.common.delivery import Delivery
from collectors.common.outbox import Outbox
from collectors.common.transport import Transport
from packages.contracts.common import BatchEnvelope
from packages.contracts.diagnostics import DiagnosticRecord
from packages.contracts.inventory import FileObjectRecord, InventoryRecord, VolumeRecord
from packages.shared.models.core import filesystem_objects, object_path_history, volumes
from packages.shared.models.jobs import ingest_batches
from packages.shared.models.telemetry import diagnostic_bundles
from tests.deployment.collector_delivery import serving_ingest

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL required")


@dataclass
class Setup:
    client: object
    engine: object
    collector: object
    token: str = field(repr=False)


@pytest.fixture
def delivery_setup(authenticated_setup):
    client, engine, collector, token, _ = authenticated_setup
    return Setup(client, engine, collector, token)


def capture(tmp_path, setup):
    now = datetime.now(UTC)
    batch = BatchEnvelope[InventoryRecord](
        collector_id=setup.collector,
        batch_id=str(uuid4()),
        schema_version=1,
        sent_at=now,
        first_event_at=now,
        last_event_at=now,
        record_count=2,
        records=[
            VolumeRecord(occurred_at=now, unique_identity="synthetic-volume", filesystem="NTFS"),
            FileObjectRecord(
                occurred_at=now,
                volume_identity="synthetic-volume",
                file_id="42",
                object_type="FILE",
                name="Report",
                relative_path="Report",
            ),
        ],
    )
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", setup.collector)
    box.enqueue("inventory", batch, "inventory", 0, {"cursor": 1})
    return box, batch, now


def count_effects(engine):
    with engine.connect() as connection:
        return tuple(
            connection.scalar(select(func.count()).select_from(table))
            for table in [ingest_batches, volumes, filesystem_objects, object_path_history]
        )


def mutation_headers(client):
    return {
        "Origin": "https://storage.example.test",
        "X-CSRF-Token": client.cookies.get("__Host-storage_csrf"),
    }


def test_server_acceptance_then_client_process_crash_replays_once(delivery_setup, tmp_path):
    setup = delivery_setup
    box, batch, _ = capture(tmp_path, setup)
    with serving_ingest(setup.client.app, tmp_path / "tls") as (origin, ca):
        config = {
            "origin": origin,
            "ca": str(ca),
            "token": setup.token,
            "collector_id": str(setup.collector),
            "outbox": str(box.path),
        }
        crashed = subprocess.run(
            [sys.executable, "-m", "tests.deployment.collector_delivery", "--crash-after-accept"],
            input=json.dumps(config).encode(),
            capture_output=True,
            timeout=25,
        )
        assert crashed.returncode == 29 and not crashed.stdout and not crashed.stderr
        assert count_effects(setup.engine) == (1, 1, 1, 1)
        restored = Outbox(box.path, setup.collector)
        assert restored.status().pending_count == restored.checkpoint("inventory").revision == 1
        transport = Transport(origin, ca, setup.token, collector_id=setup.collector)

        class ReceiptObserver:
            collector_id = setup.collector

            def send(self, claim):
                assert claim.body == batch.model_dump_json().encode()
                receipt = transport.send(claim)
                assert receipt.kind == "accepted" and receipt.duplicate is True
                return receipt

        replay_at = datetime.now(UTC) + timedelta(seconds=60)
        delivery = Delivery(restored, ReceiptObserver(), clock=lambda: replay_at)
        assert delivery.run_once().state == "accepted"
        assert restored.status().pending_count == 0
        assert count_effects(setup.engine) == (1, 1, 1, 1)


@pytest.mark.parametrize("change", ["rotate", "disable"])
def test_real_credential_revocation_preserves_queue_until_explicit_refresh(
    delivery_setup, tmp_path, change
):
    setup = delivery_setup
    box, _, now = capture(tmp_path, setup)
    headers = mutation_headers(setup.client)
    route = f"/api/v1/collectors/{setup.collector}"
    if change == "rotate":
        response = setup.client.post(route + "/rotate-token", json={}, headers=headers)
        assert response.status_code == 200
        current_token = response.json()["token"]
    else:
        assert (
            setup.client.patch(route, json={"enabled": False}, headers=headers).status_code == 200
        )
        current_token = setup.token
    with serving_ingest(setup.client.app, tmp_path / "tls") as (origin, ca):
        delivery = Delivery(
            box, Transport(origin, ca, setup.token, collector_id=setup.collector), clock=lambda: now
        )
        assert delivery.run_once().state == "suspended"
        assert count_effects(setup.engine) == (0, 0, 0, 0)
        restored = Outbox(box.path, setup.collector)
        current = Transport(origin, ca, current_token, collector_id=setup.collector)
        restarted = Delivery(restored, current, clock=lambda: now)
        assert restarted.run_once().state == "suspended"
        assert restored.status().pending_count == restored.checkpoint("inventory").revision == 1
        if change == "disable":
            assert (
                setup.client.patch(route, json={"enabled": True}, headers=headers).status_code
                == 200
            )
        restarted.refresh_credentials(current)
        assert restarted.run_once().state == "accepted"
        assert restored.status().pending_count == 0 and count_effects(setup.engine) == (1, 1, 1, 1)


def test_diagnostic_domain_uses_published_ingest_route(delivery_setup, tmp_path):
    setup = delivery_setup
    now = datetime.now(UTC)
    batch = BatchEnvelope[DiagnosticRecord](
        collector_id=setup.collector,
        batch_id=str(uuid4()),
        schema_version=1,
        sent_at=now,
        first_event_at=now,
        last_event_at=now,
        record_count=1,
        records=[
            DiagnosticRecord(
                occurred_at=now,
                trigger_type="SYNTHETIC",
                first_event_at=now,
                last_event_at=now,
                sha256="a" * 64,
                status="METADATA_ONLY",
            )
        ],
    )
    box = Outbox(tmp_path / "private" / "outbox.sqlite3", setup.collector)
    box.enqueue("diagnostics", batch, "diagnostics", 0, {"cursor": 1})
    with serving_ingest(setup.client.app, tmp_path / "tls") as (origin, ca):
        delivery = Delivery(box, Transport(origin, ca, setup.token, collector_id=setup.collector))
        assert delivery.run_once().state == "accepted" and box.status().pending_count == 0
    with setup.engine.connect() as connection:
        assert connection.scalar(select(ingest_batches.c.kind)) == "diagnostic-bundles"
        assert connection.scalar(select(func.count()).select_from(diagnostic_bundles)) == 1
