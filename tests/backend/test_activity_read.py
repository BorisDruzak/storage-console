import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import insert

from packages.shared.models.activity import change_events

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL required")


def seed(setup):
    _, engine, _, _, source = setup
    now = datetime.now(UTC) - timedelta(seconds=1)
    identities = [uuid4(), uuid4(), uuid4()]
    with engine.begin() as connection:
        for identity, kind in zip(identities, ["CREATE", "WRITE", "RENAME"], strict=True):
            connection.execute(insert(change_events).values(
                id=identity, source_node_id=source, volume_identity="volume:synthetic",
                file_id="42", parent_file_id="1", event_type=kind, occurred_at=now,
                old_relative_path="pilot\\До.txt" if kind == "RENAME" else None,
                new_relative_path="pilot\\После.txt", reason_mask="0x80002000",
                source_event_id="ntfs-usn:" + identity.hex,
            ))
    return identities, now


def test_activity_typed_projection_paging_ties_and_no_fake_attribution(authenticated_setup):
    client, _, _, _, source = authenticated_setup
    identities, _ = seed(authenticated_setup)
    first = client.get("/api/v1/activity?limit=2").json()
    second = client.get("/api/v1/activity?limit=2&offset=2").json()
    assert first["total"] == second["total"] == 3
    assert [row["id"] for row in first["items"] + second["items"]] == [
        str(i) for i in sorted(identities, reverse=True)
    ]
    assert first["quality"] == "UNAVAILABLE" and first["continuity"] == "UNKNOWN"
    for row in first["items"] + second["items"]:
        assert row["source_id"] == str(source)
        assert row["volume_identity"] == "volume:synthetic" and row["file_id"] == "42"
        assert row["actor"] is None and row["client"] is None and row["confidence"] is None
        assert row["provenance"] == "NTFS_USN" and row["reason_mask"] == "0x80002000"
        assert row["occurred_at"].endswith("Z")
    response = client.get(f"/api/v1/activity?source_id={source}&event_type=RENAME")
    assert response.status_code == 200 and response.json()["total"] == 1
    assert response.json()["items"][0]["old_relative_path"] == "pilot\\До.txt"
    assert response.headers["Cache-Control"] == "no-store"
    assert 0 <= int(response.headers["X-Evidence-Valid-For-Ms"]) <= 35000


@pytest.mark.parametrize("age,expected", [(0, "COMPLETE"), (20, "UNAVAILABLE")])
def test_continuity_requires_recent_usn_progress_not_only_fresh_heartbeat(
    authenticated_setup, age, expected,
):
    client, _, collector, token, source = authenticated_setup
    now = datetime.now(UTC)
    proof = int((now-timedelta(seconds=age)).timestamp()*1000)
    at = now.isoformat()
    heartbeat = dict(occurred_at=at, version="0.1.0",
                     cursor=f"ntfs-usn:continuous:{proof}:" + "0"*64)
    response = client.post("/api/v1/ingest/heartbeat", headers={"Authorization":"Bearer " + token},
                           json=dict(collector_id=str(collector), batch_id="usn-proof",
                                     schema_version=1, sent_at=at, first_event_at=at,
                                     last_event_at=at, record_count=1, records=[heartbeat]))
    assert response.status_code == 202
    activity = client.get("/api/v1/activity", params={"source_id":str(source)})
    assert activity.status_code == 200
    assert activity.json()["quality"] == expected
    if age == 0:
        assert 0 < int(activity.headers["X-Evidence-Valid-For-Ms"]) <= 15000
    else:
        assert activity.json()["continuity"] == "UNKNOWN"


@pytest.mark.parametrize("query", ["limit=101", "offset=10001", "event_type=FAKE",
    "start_at=2026-01-01T00:00:00", "start_at=2026-01-01T00:00:00Z&end_at=2026-03-01T00:00:00Z",
    "start_at=2026-02-01T00:00:00Z&end_at=2026-01-01T00:00:00Z"])
def test_activity_bounds(authenticated_setup, query):
    assert authenticated_setup[0].get("/api/v1/activity?" + query).status_code == 422


def test_activity_time_filter_and_unknown_source(authenticated_setup):
    client, *_ = authenticated_setup
    _, now = seed(authenticated_setup)
    response = client.get("/api/v1/activity", params={
        "start_at": (now + timedelta(seconds=1)).isoformat(),
        "end_at": (now + timedelta(seconds=2)).isoformat(),
    })
    assert response.status_code == 200 and response.json()["items"] == []
    assert client.get(f"/api/v1/activity?source_id={uuid4()}").status_code == 404


def test_activity_session_auth_and_collector_token_separation(authenticated_setup):
    client, _, _, token, _ = authenticated_setup
    client.cookies.clear()
    assert client.get("/api/v1/activity").status_code == 401
    response = client.get("/api/v1/activity", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 401
