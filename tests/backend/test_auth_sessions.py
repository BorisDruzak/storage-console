import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, insert, select, update

from apps.api.user_auth.sessions import Actor, SessionStore
from packages.shared.models.security import (
    audit_log,
    login_rate_buckets,
    roles,
    user_roles,
    user_sessions,
    users,
)


@pytest.fixture
def session_setup(ingest_setup):
    _, engine, *_ = ingest_setup
    user, role = uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(users).values(id=user, username="synthetic", auth_provider="local")
        )
        connection.execute(insert(roles).values(id=role, code="storage_admin"))
        connection.execute(insert(user_roles).values(user_id=user, role_id=role))
    return SessionStore(engine), engine, user, role


def test_opaque_session_rotation_hashes_and_server_logout(session_setup):
    store, engine, user, _ = session_setup
    first, second = store.issue(user), store.issue(user)
    assert first.token != second.token and first.csrf != second.csrf
    assert first.token not in repr(first) and first.csrf not in repr(first)
    with engine.connect() as connection:
        row = connection.execute(
            select(user_sessions).where(
                user_sessions.c.token_hash == hashlib.sha256(first.token.encode()).hexdigest()
            )
        ).one()
        assert row.expires_at - row.created_at == timedelta(hours=8)
        assert row.csrf_hash == hashlib.sha256(first.csrf.encode()).hexdigest()
    current = store.resolve(first.token)
    assert current.actor.id == user and current.actor.can("manage_sources")
    assert current.csrf_matches(first.csrf, first.csrf)
    assert not current.csrf_matches(first.csrf, second.csrf)
    assert store.revoke(first.token)
    assert store.resolve(first.token) is None
    assert not store.revoke(first.token)
    assert store.resolve(second.token) is not None
    with engine.connect() as connection:
        assert connection.scalars(select(audit_log.c.action)).all() == [
            "auth.login",
            "auth.login",
            "auth.logout",
        ]


@pytest.mark.parametrize("reason", ["expired", "idle", "disabled", "role_removed", "unknown_role"])
def test_current_state_revokes_access_without_relogin(session_setup, reason):
    store, engine, user, role = session_setup
    issued = store.issue(user)
    with engine.begin() as connection:
        if reason in {"expired", "idle"}:
            row = connection.execute(select(user_sessions)).one()
            old = row.created_at - timedelta(hours=9)
            connection.execute(
                update(user_sessions).values(
                    created_at=old,
                    last_used_at=old,
                    expires_at=row.created_at - timedelta(seconds=1)
                    if reason == "expired"
                    else row.expires_at,
                )
            )
        elif reason == "disabled":
            connection.execute(update(users).where(users.c.id == user).values(enabled=False))
        elif reason == "role_removed":
            connection.execute(delete(user_roles).where(user_roles.c.user_id == user))
        else:
            connection.execute(update(roles).where(roles.c.id == role).values(code="unknown"))
    assert store.resolve(issued.token) is None
    assert store.resolve("invalid-token") is None
    if reason in {"disabled", "role_removed", "unknown_role"}:
        assert store.issue(user) is None


def test_idle_touch_keeps_absolute_expiry(session_setup):
    store, engine, user, _ = session_setup
    issued = store.issue(user)
    with engine.begin() as connection:
        row = connection.execute(select(user_sessions)).one()
        old = row.created_at - timedelta(minutes=20)
        connection.execute(update(user_sessions).values(created_at=old, last_used_at=old))
    assert store.resolve(issued.token) is not None
    with engine.connect() as connection:
        touched = connection.execute(select(user_sessions)).one()
        assert touched.expires_at == row.expires_at
        assert touched.last_used_at > old


def test_session_clock_is_database_clock_not_application_clock(session_setup, monkeypatch):
    from datetime import datetime

    from sqlalchemy import func

    class ClockGuard(datetime):
        @classmethod
        def now(cls, tz=None):
            raise AssertionError("Application clock used for authentication")

    store, engine, user, _ = session_setup
    monkeypatch.setattr("apps.api.user_auth.sessions.datetime", ClockGuard)
    with engine.connect() as connection:
        before = connection.scalar(select(func.clock_timestamp()))
    issued = store.issue(user)
    assert store.resolve(issued.token) is not None
    with engine.connect() as connection:
        row = connection.execute(select(user_sessions)).one()
        after = connection.scalar(select(func.clock_timestamp()))
    assert before <= row.created_at <= row.last_used_at <= after


def test_parallel_resolve_and_logout_cannot_resurrect_revoked_token(session_setup):
    store, _, user, _ = session_setup
    issued = store.issue(user)
    with ThreadPoolExecutor(max_workers=4) as pool:
        readers = [pool.submit(store.resolve, issued.token) for _ in range(10)]
        logout = pool.submit(store.revoke, issued.token)
        assert logout.result(timeout=10)
        for reader in readers:
            reader.result(timeout=10)
    assert store.resolve(issued.token) is None


def test_parallel_login_budget_and_database_window_reset(session_setup):
    store, engine, *_ = session_setup
    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted = list(pool.map(lambda _: store.consume_ticket("local", "SYNTHETIC"), range(20)))
    assert sum(accepted) == 5
    with engine.begin() as connection:
        from sqlalchemy import func

        connection.execute(
            update(login_rate_buckets).values(
                window_started_at=func.clock_timestamp() - timedelta(minutes=11)
            )
        )
    assert store.consume_ticket("local", "synthetic")


def test_global_budget_applies_across_accounts_and_bounds_denial_audit(session_setup):
    store, engine, *_ = session_setup
    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted = list(
            pool.map(lambda index: store.consume_ticket("local", f"user-{index}"), range(120))
        )
    assert sum(accepted) == 100
    assert not store.consume_ticket("local", "new-account")
    assert not store.consume_ticket("local", "another-new-account")
    with engine.connect() as connection:
        assert len(connection.execute(select(login_rate_buckets)).all()) == 101
        assert connection.scalars(select(audit_log.c.action)).all() == ["auth.rate_denied"]


@pytest.mark.parametrize(
    "role,manage,diagnose",
    [
        ("storage_admin", True, True),
        ("storage_operator", False, True),
        ("auditor", False, False),
        ("analyst", False, False),
        ("viewer", False, False),
    ],
)
def test_permissions_are_explicit_and_unknown_permissions_deny(role, manage, diagnose):
    actor = Actor(uuid4(), "synthetic", frozenset({role}))
    assert actor.can("read")
    assert actor.can("manage_sources") is manage
    assert actor.can("manage_policy") is manage
    assert actor.can("run_diagnostics") is diagnose
    assert not actor.can("unknown_permission")
    assert not Actor(actor.id, actor.username, actor.roles | {"unknown_role"}).can("read")
