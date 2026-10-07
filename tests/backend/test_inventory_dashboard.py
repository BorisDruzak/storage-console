import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import Response
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import insert, update

from apps.api.main import create_app
from apps.api.read.storage import share, volume
from apps.api.read.validity import storage_validity
from packages.shared.models.core import shares, source_nodes, volumes
from packages.shared.settings import Settings


def volume_row(age=300, total=1000, free=400):
    now = datetime.now(UTC)
    return dict(
        id=uuid4(),
        source_node_id=uuid4(),
        unique_identity="synthetic-volume-" + uuid4().hex,
        filesystem="NTFS",
        label=None,
        total_bytes=total,
        free_bytes=free,
        first_seen_at=now - timedelta(days=1),
        last_seen_at=now - timedelta(seconds=age),
        expected_cadence_seconds=60,
    )


@pytest.mark.parametrize(
    "age,total,expected",
    [
        (300, 1000, "COMPLETE"),
        (7201, 1000, "STALE"),
        (-60, 1000, "UNAVAILABLE"),
        (300, None, "PARTIAL"),
    ],
)
def test_volume_inventory_window_is_independent_of_heartbeat(age, total, expected):
    row = volume_row(age, total)
    assert volume(row, datetime.now(UTC), [], 7200).quality == expected


def test_storage_validity_uses_inventory_window_for_volume_and_share():
    now = datetime.now(UTC)
    for age, expected_max in [(300, 35000), (7199, 1000), (-1, 1000)]:
        row = volume_row(age)
        row["last_seen_at"] = now - timedelta(seconds=age)
        response = Response()
        storage_validity(response, [row], now, 7200)
        assert 0 < int(response.headers["X-Evidence-Valid-For-Ms"]) <= expected_max
    row = dict(
        id=uuid4(),
        source_node_id=uuid4(),
        volume_id=None,
        name="synthetic",
        relative_path="reports",
        protocol="SMB",
        last_seen_at=now - timedelta(seconds=300),
    )
    assert share(row, now, 7200).quality == "COMPLETE"


def test_inventory_setting_is_bounded():
    assert Settings(_env_file=None).inventory_stale_seconds == 7200
    for value in [0, -1, 604801]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, inventory_stale_seconds=value)


def test_capacity_missing_free_is_partial_and_window_boundary_is_inclusive():
    now = datetime.now(UTC)
    row = volume_row()
    row["free_bytes"] = None
    assert volume(row, now, [], 7200).quality == "PARTIAL"
    row["free_bytes"] = 400
    row["last_seen_at"] = now - timedelta(seconds=7200)
    assert volume(row, now, [], 7200).quality == "COMPLETE"
    assert volume(row, now + timedelta(microseconds=1), [], 7200).quality == "STALE"


pg = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL required")


def seed_volume(engine, source, *, age=300, total=1000, free=400):
    row = volume_row(age, total, free)
    row.pop("expected_cadence_seconds")
    row["source_node_id"] = source
    with engine.begin() as connection:
        connection.execute(insert(volumes).values(**row))
    return row["id"]


@pg
@pytest.mark.parametrize(
    "free,state", [(301, "HEALTHY"), (300, "OBSERVE"), (200, "WARNING"), (100, "CRITICAL")]
)
def test_capacity_thresholds_and_truthful_overall(authenticated_setup, free, state):
    client, engine, _, _, source = authenticated_setup
    seed_volume(engine, source, free=free)
    response = client.get("/api/v1/overview")
    assert response.status_code == 200
    data = response.json()
    capacity = data["capacity"]
    assert capacity["state"] == state
    assert capacity["total_bytes"] == 1000
    assert capacity["free_bytes"] == free
    assert capacity["used_bytes"] == 1000 - free
    assert capacity["used_percent"] == pytest.approx((1000 - free) / 10)
    assert capacity["current_volume_count"] == 1
    assert data["inventory"]["filesystem_types"] == ["NTFS"]
    assert data["overall_state"] == "UNKNOWN"
    assert all(d["state"] == "UNKNOWN" for d in data["domains"])
    assert "synthetic-volume" not in str(data)


@pg
def test_capacity_worst_volume_and_excluded_evidence_counts(authenticated_setup):
    client, engine, _, _, source = authenticated_setup
    seed_volume(engine, source, total=10000, free=9000)
    seed_volume(engine, source, total=1000, free=100)
    seed_volume(engine, source, age=7201)
    seed_volume(engine, source, total=None)
    seed_volume(engine, source, age=-60)
    data = client.get("/api/v1/overview").json()
    summary = data["capacity"]
    assert summary["state"] == "CRITICAL"
    assert summary["total_bytes"] == 11000
    assert summary["free_bytes"] == 9100
    assert summary["used_bytes"] == 1900
    assert summary["used_percent"] == pytest.approx(1900 / 110)
    assert summary["volume_count"] == 5
    assert summary["current_volume_count"] == 2
    assert summary["unavailable_volume_count"] == 3
    assert summary["latest_inventory_at"] <= data["evaluated_at"]
    assert data["inventory"]["volume_count"] == 5


@pg
@pytest.mark.parametrize("mode", ["empty", "partial", "stale", "future", "zero"])
def test_no_usable_capacity_is_unknown_without_totals(authenticated_setup, mode):
    client, engine, _, _, source = authenticated_setup
    if mode != "empty":
        seed_volume(
            engine,
            source,
            age=7201 if mode == "stale" else -60 if mode == "future" else 300,
            total=None if mode == "partial" else 0 if mode == "zero" else 1000,
            free=0 if mode == "zero" else 400,
        )
    summary = client.get("/api/v1/overview").json()["capacity"]
    assert summary["state"] == "UNKNOWN"
    assert summary["current_volume_count"] == 0
    assert all(
        summary[key] is None for key in ["total_bytes", "free_bytes", "used_bytes", "used_percent"]
    )


@pg
def test_storage_and_overview_expiry_share_the_inventory_policy(authenticated_setup):
    client, engine, _, _, source = authenticated_setup
    volume_id = seed_volume(engine, source)
    with engine.begin() as connection:
        connection.execute(update(source_nodes).values(expected_cadence_seconds=60))
        connection.execute(
            insert(shares).values(
                source_node_id=source,
                volume_id=volume_id,
                name="synthetic-share",
                relative_path="reports",
                protocol="SMB",
                last_seen_at=datetime.now(UTC) - timedelta(seconds=300),
            )
        )
    for route in ["volumes", "shares"]:
        response = client.get("/api/v1/" + route)
        assert response.json()["items"][0]["quality"] == "COMPLETE"
        assert int(response.headers["X-Evidence-Valid-For-Ms"]) == 35000
    with engine.begin() as connection:
        connection.execute(
            update(volumes).values(last_seen_at=datetime.now(UTC) - timedelta(seconds=7198))
        )
    for route in ["overview", "volumes"]:
        response = client.get("/api/v1/" + route)
        assert 0 < int(response.headers["X-Evidence-Valid-For-Ms"]) <= 2000
    with engine.begin() as connection:
        connection.execute(
            update(volumes).values(last_seen_at=datetime.now(UTC) - timedelta(seconds=7201))
        )
    assert client.get("/api/v1/volumes").json()["items"][0]["quality"] == "STALE"
    assert client.get("/api/v1/overview").json()["capacity"]["state"] == "UNKNOWN"


@pg
def test_configured_inventory_window_reaches_read_routes(authenticated_setup):
    client, engine, _, _, source = authenticated_setup
    seed_volume(engine, source, age=300)
    assert client.get("/api/v1/overview").json()["capacity"]["state"] == "HEALTHY"
    app = create_app(
        Settings(inventory_stale_seconds=120), engine, user_auth=client.app.state.user_auth
    )
    with TestClient(app, base_url=str(client.base_url), cookies=client.cookies) as configured:
        assert configured.get("/api/v1/overview").json()["capacity"]["state"] == "UNKNOWN"
        assert configured.get("/api/v1/volumes").json()["items"][0]["quality"] == "STALE"
