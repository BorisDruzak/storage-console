"""USN and Audit have independent identities and health; admin-only sensitive reads."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import insert, update

from apps.api.user_auth.sessions import Actor
from packages.shared.models.core import collectors, source_nodes


def heartbeat(collector, now):
    return {
        "collector_id": str(collector),
        "batch_id": uuid4().hex,
        "schema_version": 1,
        "sent_at": now.isoformat(),
        "first_event_at": now.isoformat(),
        "last_event_at": now.isoformat(),
        "record_count": 1,
        "records": [
            {
                "occurred_at": now.isoformat(),
                "version": "synthetic",
                "cursor": f"ntfs-usn:continuous:{int(now.timestamp() * 1000)}:" + "a" * 64,
            }
        ],
    }


@pytest.mark.parametrize("audit_enabled", [True, False])
def test_two_collectors_do_not_destroy_healthy_usn_proof(authenticated_setup, audit_enabled):
    client, engine, usn, token, source = authenticated_setup
    now = datetime.now(UTC)
    assert (
        client.post(
            "/api/v1/ingest/heartbeat",
            json=heartbeat(usn, now),
            headers={"Authorization": "Bearer " + token},
        ).status_code
        == 202
    )
    with engine.begin() as conn:
        conn.execute(
            insert(collectors).values(
                id=uuid4(),
                source_node_id=source,
                collector_type="AUDIT_WINDOWS",
                token_hash=uuid4().hex * 2,
                enabled=audit_enabled,
            )
        )
    response = client.get("/api/v1/activity")
    assert (
        response.status_code == 200 and response.json()["continuity"] == "CONTINUOUS_SINCE_BASELINE"
    )


def test_audit_freshness_cannot_promote_stopped_usn(authenticated_setup):
    client, engine, usn, token, source = authenticated_setup
    now = datetime.now(UTC)
    assert (
        client.post(
            "/api/v1/ingest/heartbeat",
            json=heartbeat(usn, now),
            headers={"Authorization": "Bearer " + token},
        ).status_code
        == 202
    )
    with engine.begin() as conn:
        conn.execute(
            update(collectors)
            .where(collectors.c.id == usn)
            .values(last_seen_at=now - timedelta(hours=2))
        )
        conn.execute(
            insert(collectors).values(
                id=uuid4(),
                source_node_id=source,
                collector_type="AUDIT_WINDOWS",
                token_hash=uuid4().hex * 2,
                last_seen_at=now,
            )
        )
        conn.execute(
            update(source_nodes).where(source_nodes.c.id == source).values(last_success_at=now)
        )
    assert client.get("/api/v1/activity").json()["continuity"] == "UNKNOWN"


@pytest.mark.parametrize("role", ["viewer", "analyst", "storage_operator", "auditor"])
def test_sensitive_activity_permission_is_admin_only(role):
    assert not Actor(uuid4(), "synthetic", frozenset({role})).can("read_sensitive_activity")
    assert Actor(uuid4(), "synthetic", frozenset({"storage_admin"})).can("read_sensitive_activity")


@pytest.mark.parametrize("usn_count", [0, 1, 2])
@pytest.mark.parametrize("audit_enabled", [True, False])
def test_zero_one_two_operational_collectors_are_independent_of_audit(
    authenticated_setup, usn_count, audit_enabled
):
    import secrets

    from apps.api.auth import token_hash

    client, engine, usn, token, source = authenticated_setup
    now = datetime.now(UTC)
    response = client.post(
        "/api/v1/ingest/heartbeat",
        json=heartbeat(usn, now),
        headers={"Authorization": "Bearer " + token},
    )
    assert response.status_code == 202
    with engine.begin() as conn:
        if usn_count == 0:
            conn.execute(update(collectors).where(collectors.c.id == usn).values(enabled=False))
        conn.execute(
            insert(collectors).values(
                source_node_id=source,
                collector_type="AUDIT_WINDOWS",
                token_hash=uuid4().hex * 2,
                enabled=audit_enabled,
            )
        )
        if usn_count == 2:
            second = uuid4()
            second_token = secrets.token_urlsafe(32)
            conn.execute(
                insert(collectors).values(
                    id=second,
                    source_node_id=source,
                    collector_type="WINDOWS",
                    token_hash=token_hash(second_token),
                )
            )
    if usn_count == 2:
        response = client.post(
            "/api/v1/ingest/heartbeat",
            json=heartbeat(second, now),
            headers={"Authorization": "Bearer " + second_token},
        )
        assert response.status_code == 202
    assert client.get("/api/v1/activity").json()["continuity"] == (
        "CONTINUOUS_SINCE_BASELINE" if usn_count == 1 else "UNKNOWN"
    )


def test_enrollment_retains_old_usn_identity_and_credential(authenticated_setup):
    client, _, usn, token, source = authenticated_setup
    response = client.post(
        f"/api/v1/sources/{source}/collectors",
        json={"collector_type": "AUDIT_WINDOWS"},
        headers={
            "Origin": "https://storage.example.test",
            "X-CSRF-Token": client.cookies["__Host-storage_csrf"],
        },
    )
    assert response.status_code == 201
    issued = response.json()
    assert issued["id"] != str(usn) and issued["source_node_id"] == str(source)
    assert issued["collector_type"] == "AUDIT_WINDOWS"
    response = client.post(
        "/api/v1/ingest/heartbeat",
        json=heartbeat(usn, datetime.now(UTC)),
        headers={"Authorization": "Bearer " + token},
    )
    assert response.status_code == 202
