import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, insert, select, text

from packages.shared.models.core import source_nodes
from packages.shared.models.security import roles, user_roles, users

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL required")
ORIGIN = "https://storage.example.test"


def headers(client):
    return {"Origin": ORIGIN, "X-CSRF-Token": client.cookies.get("__Host-storage_csrf")}


def source_data():
    return dict(source_type="FILESERVER", hostname="synthetic", instance_id=str(uuid4()))


def set_role(engine, role):
    with engine.begin() as conn:
        user = conn.scalar(select(users.c.id).where(users.c.username == "synthetic-read-admin"))
        role_id = conn.scalar(select(roles.c.id).where(roles.c.code == role))
        if role_id is None:
            role_id = conn.scalar(insert(roles).values(code=role).returning(roles.c.id))
        conn.execute(delete(user_roles).where(user_roles.c.user_id == user))
        conn.execute(insert(user_roles).values(user_id=user, role_id=role_id))


def test_source_and_collector_lifecycle_requires_user_session_and_has_no_store(authenticated_setup):
    client, _, _, _, _ = authenticated_setup
    created = client.post("/api/v1/sources", json=source_data(), headers=headers(client))
    assert created.status_code == 201
    assert created.headers["cache-control"] == "no-store"
    identity = created.json()["id"]
    assert client.get("/api/v1/sources/" + identity).json()["freshness"]["state"] == "UNKNOWN"
    path = "/api/v1/sources/" + identity + "/collectors"
    enrolled = client.post(path, json={"collector_type": "WINDOWS"}, headers=headers(client))
    assert enrolled.status_code == 201
    assert enrolled.headers["cache-control"] == "no-store"
    credential = enrolled.json()
    assert len(credential["token"]) == 43
    collector_path = "/api/v1/collectors/" + credential["id"]
    listing = client.get(path)
    assert listing.status_code == 200 and listing.headers["cache-control"] == "no-store"
    assert "token" not in listing.json()["items"][0]
    assert "token_hash" not in listing.json()["items"][0]
    rotated = client.post(collector_path + "/rotate-token", json={}, headers=headers(client))
    assert rotated.status_code == 200 and rotated.json()["token"] != credential["token"]
    disabled = client.patch(collector_path, json={"enabled": False}, headers=headers(client))
    assert disabled.status_code == 200 and disabled.json()["enabled"] is False
    assert "token" not in disabled.json()


@pytest.mark.parametrize("role", ["viewer", "analyst", "auditor", "storage_operator"])
def test_read_roles_may_list_collectors_but_cannot_mutate_current_role(authenticated_setup, role):
    client, engine, collector, _, source = authenticated_setup
    set_role(engine, role)
    assert client.get(f"/api/v1/sources/{source}/collectors").status_code == 200
    for method, path, data in (
        ("POST", "/api/v1/sources", source_data()),
        ("POST", f"/api/v1/sources/{source}/collectors", {"collector_type": "WINDOWS"}),
        ("POST", f"/api/v1/collectors/{collector}/rotate-token", {}),
        ("PATCH", f"/api/v1/collectors/{collector}", {"enabled": False}),
    ):
        response = client.request(method, path, json=data, headers=headers(client))
        assert response.status_code == 403
        assert response.json() == {"detail": "AUTH_FORBIDDEN"}
        assert response.headers["cache-control"] == "no-store"


def test_anonymous_and_collector_bearer_cannot_manage_sources(authenticated_setup):
    client, _, collector, bearer, source = authenticated_setup
    client.cookies.clear()
    for supplied in ({}, {"Authorization": "Bearer " + bearer}):
        response = client.post(
            "/api/v1/sources", json=source_data(), headers=supplied | {"Origin": ORIGIN}
        )
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
        assert (
            client.get(f"/api/v1/sources/{source}/collectors", headers=supplied).status_code == 401
        )
        assert (
            client.post(
                f"/api/v1/collectors/{collector}/rotate-token", json={}, headers=supplied
            ).status_code
            == 401
        )


@pytest.mark.parametrize(
    "change",
    [{"Origin": "https://wrong.example.test"}, {"X-CSRF-Token": "wrong"}, {"Origin": "null"}],
)
def test_mutations_require_exact_origin_and_csrf(authenticated_setup, change):
    client, *_ = authenticated_setup
    response = client.post("/api/v1/sources", json=source_data(), headers=headers(client) | change)
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


def test_generic_validation_media_body_limit_and_no_store(authenticated_setup):
    client, *_ = authenticated_setup
    sentinel = "synthetic-value-must-not-echo"
    response = client.post(
        "/api/v1/sources", json=source_data() | {"password": sentinel}, headers=headers(client)
    )
    assert response.status_code == 422 and sentinel not in response.text
    assert response.json() == {"detail": "INVALID_REQUEST"}
    assert response.headers["cache-control"] == "no-store"
    response = client.post(
        "/api/v1/sources", content="{}", headers=headers(client) | {"Content-Type": "text/plain"}
    )
    assert response.status_code == 415
    assert response.headers["cache-control"] == "no-store"
    response = client.post(
        "/api/v1/sources",
        content=iter([b"{" + b" " * 10000, b" " * 10000 + b"}"]),
        headers=headers(client) | {"Content-Type": "application/json", "Content-Length": "2"},
    )
    assert response.status_code == 413
    assert response.headers["cache-control"] == "no-store"


def test_conflict_missing_resources_and_pagination_are_bounded(authenticated_setup):
    client, _, collector, _, source = authenticated_setup
    data = source_data()
    assert client.post("/api/v1/sources", json=data, headers=headers(client)).status_code == 201
    assert client.post("/api/v1/sources", json=data, headers=headers(client)).status_code == 409
    unknown = uuid4()
    assert client.get(f"/api/v1/sources/{unknown}/collectors").status_code == 404
    assert (
        client.post(
            f"/api/v1/sources/{unknown}/collectors",
            json={"collector_type": "WINDOWS"},
            headers=headers(client),
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/collectors/{unknown}/rotate-token", json={}, headers=headers(client)
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/collectors/{collector}/rotate-token",
            json={"token": "forbidden"},
            headers=headers(client),
        ).status_code
        == 422
    )
    assert client.get(f"/api/v1/sources/{source}/collectors?limit=101").status_code == 422
    assert client.get(f"/api/v1/sources/{source}/collectors?offset=1000001").status_code == 422


def test_failed_audit_returns_generic_503_and_rolls_back_source(authenticated_setup):
    client, engine, *_ = authenticated_setup
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE audit_log ADD CONSTRAINT reject_source "
                "CHECK (action <> 'source.register') NOT VALID"
            )
        )
    data = source_data()
    response = client.post("/api/v1/sources", json=data, headers=headers(client))
    assert response.status_code == 503
    assert response.json() == {"detail": "CONTROL_UNAVAILABLE"}
    assert response.headers["cache-control"] == "no-store"
    with engine.connect() as conn:
        assert (
            conn.scalar(
                select(func.count())
                .select_from(source_nodes)
                .where(source_nodes.c.instance_id == data["instance_id"])
            )
            == 0
        )


def test_disabled_session_user_cannot_enroll(authenticated_setup):
    client, engine, _, _, source = authenticated_setup
    user = UUID(client.get("/api/v1/auth/me").json()["id"])
    with engine.begin() as conn:
        conn.execute(users.update().where(users.c.id == user).values(enabled=False))
    assert (
        client.post(
            f"/api/v1/sources/{source}/collectors",
            json={"collector_type": "WINDOWS"},
            headers=headers(client),
        ).status_code
        == 401
    )


def test_every_write_rejects_missing_csrf_and_duplicate_origin(authenticated_setup):
    client, _, collector, _, source = authenticated_setup
    for method, path, data in (
        ("POST", "/api/v1/sources", source_data()),
        ("POST", f"/api/v1/sources/{source}/collectors", {"collector_type": "WINDOWS"}),
        ("POST", f"/api/v1/collectors/{collector}/rotate-token", {}),
        ("PATCH", f"/api/v1/collectors/{collector}", {"enabled": False}),
    ):
        assert (
            client.request(method, path, json=data, headers={"Origin": ORIGIN}).status_code == 403
        )
        supplied = [
            ("Origin", ORIGIN),
            ("Origin", ORIGIN),
            ("X-CSRF-Token", client.cookies.get("__Host-storage_csrf")),
        ]
        assert client.request(method, path, json=data, headers=supplied).status_code == 403
