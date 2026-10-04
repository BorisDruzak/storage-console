from typing import Annotated
from uuid import uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import delete, insert, select
from sqlalchemy.exc import SQLAlchemyError

from apps.api.main import create_app
from apps.api.user_auth.bootstrap import bootstrap_admin
from apps.api.user_auth.dependencies import UserAuth, require_actor, require_permission
from apps.api.user_auth.sessions import Actor
from packages.shared.auth.configuration import AuthConfig
from packages.shared.auth.providers import ProviderUnavailable
from packages.shared.models.security import audit_log, roles, user_roles, users
from packages.shared.settings import Settings

ORIGIN = "https://storage.example.test"
PASSWORD = "synthetic-long-password"


@pytest.fixture
def auth_client(ingest_setup):
    _, engine, _, bearer, _ = ingest_setup
    bootstrap_admin(engine, "emergency", PASSWORD)
    auth = UserAuth(engine, AuthConfig(ORIGIN, True))
    app = create_app(Settings(), engine, user_auth=auth)

    @app.get("/session-probe")
    def probe(actor: Annotated[Actor, Depends(require_actor)]):
        return {"username": actor.username}

    @app.get("/admin-probe")
    def admin(actor: Annotated[Actor, Depends(require_permission("manage_sources"))]):
        return {"username": actor.username}

    with TestClient(app, base_url=ORIGIN) as client:
        yield client, auth, engine, bearer


def login(client, password=PASSWORD, **kwargs):
    return client.post(
        "/api/v1/auth/login",
        json={"provider": "local", "username": "emergency", "password": password},
        headers={"Origin": ORIGIN},
        **kwargs,
    )


def test_login_me_logout_secure_cookies_and_no_secret_response(auth_client):
    client, *_ = auth_client
    assert client.get("/api/v1/auth/me").status_code == 401
    response = login(client)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"id", "username", "roles"}
    assert response.json()["roles"] == ["storage_admin"]
    headers = response.headers.get_list("set-cookie")
    assert all(
        "Secure" in header
        and "Path=/" in header
        and "SameSite=lax" in header
        and "Domain=" not in header
        for header in headers
    )
    assert "HttpOnly" in next(
        header for header in headers if header.startswith("__Host-storage_session=")
    )
    assert "HttpOnly" not in next(
        header for header in headers if header.startswith("__Host-storage_csrf=")
    )
    token, csrf = client.cookies["__Host-storage_session"], client.cookies["__Host-storage_csrf"]
    assert (
        token not in response.text and csrf not in response.text and PASSWORD not in response.text
    )
    assert client.get("/api/v1/auth/me").json() == response.json()
    assert client.get("/session-probe").status_code == 200
    assert client.get("/admin-probe").status_code == 200
    out = client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})
    assert out.status_code == 204 and not out.content
    assert all(
        "Max-Age=0" in header and "Secure" in header
        for header in out.headers.get_list("set-cookie")
    )
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.set("__Host-storage_session", token)
    assert client.get("/session-probe").status_code == 401


def test_relogin_rotates_and_revokes_previous_browser_session(auth_client):
    client, auth, *_ = auth_client
    assert login(client).status_code == 200
    old = client.cookies["__Host-storage_session"]
    assert login(client).status_code == 200
    assert client.cookies["__Host-storage_session"] != old
    assert auth.store.resolve(old) is None


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://evil.example.test"},
        {"Origin": "null"},
        {"Origin": ORIGIN + "/"},
        [("Origin", ORIGIN), ("Origin", ORIGIN)],
    ],
)
def test_login_rejects_missing_wrong_or_duplicate_origin(auth_client, headers):
    client, *_ = auth_client
    response = client.post(
        "/api/v1/auth/login",
        json={"provider": "local", "username": "emergency", "password": PASSWORD},
        headers=headers,
    )
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert PASSWORD not in response.text


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": ORIGIN},
        {"Origin": ORIGIN, "X-CSRF-Token": "wrong"},
        {"Origin": "https://evil.example.test"},
    ],
)
def test_logout_csrf_failure_preserves_session(auth_client, headers):
    client, *_ = auth_client
    assert login(client).status_code == 200
    response = client.post("/api/v1/auth/logout", headers=headers)
    assert response.status_code == 403
    assert client.get("/api/v1/auth/me").status_code == 200


def test_anonymous_and_collector_cannot_use_user_session_dependencies(auth_client):
    client, _, _, bearer = auth_client
    for path in ("/api/v1/auth/me", "/session-probe", "/admin-probe"):
        assert client.get(path, headers={"Authorization": "Bearer " + bearer}).status_code == 401


def test_failures_are_generic_bounded_and_rate_limited(auth_client):
    client, _, engine, _ = auth_client
    for _ in range(5):
        response = login(client, "synthetic-wrong-password")
        assert response.status_code == 401 and response.json() == {"detail": "AUTH_FAILED"}
    response = login(client)
    assert response.status_code == 429
    assert response.headers["cache-control"] == "no-store"
    assert PASSWORD not in response.text
    with engine.connect() as connection:
        failures = (
            connection.execute(select(audit_log).where(audit_log.c.action == "auth.failure"))
            .mappings()
            .all()
        )
        assert len(failures) == 5
        assert all(row["user_id"] is None and row["details"] == {} for row in failures)


def test_removed_roles_invalidate_http_session(auth_client):
    client, _, engine, _ = auth_client
    assert login(client).status_code == 200
    with engine.begin() as connection:
        user = connection.scalar(select(users.c.id).where(users.c.username == "emergency"))
        connection.execute(delete(user_roles).where(user_roles.c.user_id == user))
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_requires_json_and_limits_streamed_body(auth_client):
    client, *_ = auth_client
    response = client.post(
        "/api/v1/auth/login",
        content="password=" + PASSWORD,
        headers={"Origin": ORIGIN, "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 415 and PASSWORD not in response.text
    response = client.post(
        "/api/v1/auth/login",
        content=iter([b"x" * 9000, b"x" * 9000]),
        headers={"Origin": ORIGIN, "Content-Type": "application/json"},
    )
    assert response.status_code == 413 and response.headers["cache-control"] == "no-store"


def test_invalid_login_input_never_echoes_password(auth_client):
    client, *_ = auth_client
    response = client.post(
        "/api/v1/auth/login",
        json={"provider": "unknown", "username": "emergency", "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 422 and PASSWORD not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("failure", [ProviderUnavailable(), SQLAlchemyError("synthetic-secret")])
def test_provider_failures_are_generic_without_local_fallback(auth_client, monkeypatch, failure):
    client, auth, *_ = auth_client

    def unavailable(*args):
        raise failure

    monkeypatch.setattr(auth.providers["local"], "authenticate", unavailable)
    response = login(client)
    assert response.status_code == 503
    assert response.json() == {"detail": "AUTH_UNAVAILABLE"}
    assert not response.headers.get_list("set-cookie")
    assert response.headers["cache-control"] == "no-store"


def test_session_database_failure_is_generic(auth_client, monkeypatch):
    client, auth, *_ = auth_client

    def unavailable(*args):
        raise SQLAlchemyError("synthetic-secret")

    monkeypatch.setattr(auth.store, "resolve", unavailable)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 503 and response.json() == {"detail": "AUTH_UNAVAILABLE"}


def test_current_viewer_role_forbids_management(auth_client):
    client, _, engine, _ = auth_client
    assert login(client).status_code == 200
    with engine.begin() as connection:
        user = connection.scalar(select(users.c.id).where(users.c.username == "emergency"))
        role = uuid4()
        connection.execute(insert(roles).values(id=role, code="viewer"))
        connection.execute(delete(user_roles).where(user_roles.c.user_id == user))
        connection.execute(insert(user_roles).values(user_id=user, role_id=role))
    assert client.get("/session-probe").status_code == 200
    response = client.get("/admin-probe")
    assert response.status_code == 403 and response.json() == {"detail": "AUTH_FORBIDDEN"}
    assert client.get("/api/v1/auth/me").json()["roles"] == ["viewer"]


def test_duplicate_session_cookie_and_csrf_header_are_denied(auth_client):
    client, *_ = auth_client
    assert login(client).status_code == 200
    token = client.cookies["__Host-storage_session"]
    csrf = client.cookies["__Host-storage_csrf"]
    response = client.get(
        "/api/v1/auth/me",
        headers={"Cookie": f"__Host-storage_session={token}; __Host-storage_session={token}"},
    )
    assert response.status_code == 401
    response = client.post(
        "/api/v1/auth/logout",
        headers=[("Origin", ORIGIN), ("X-CSRF-Token", csrf), ("X-CSRF-Token", csrf)],
    )
    assert response.status_code == 403
    assert client.get("/api/v1/auth/me").status_code == 200


def test_missing_provider_configuration_has_no_default_account(ingest_setup):
    _, engine, *_ = ingest_setup
    with TestClient(create_app(Settings(), engine), base_url=ORIGIN) as client:
        response = login(client)
        assert response.status_code == 503 and response.json() == {"detail": "AUTH_UNAVAILABLE"}
        assert not response.headers.get_list("set-cookie")
