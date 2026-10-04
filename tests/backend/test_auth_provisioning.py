from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, update

from apps.api.user_auth.identities import bind_subject
from apps.api.user_auth.sessions import SessionStore
from packages.shared.auth.providers import Subject
from packages.shared.models.security import audit_log, roles, user_roles, users


def seed_roles(engine):
    with engine.begin() as connection:
        for code in ("storage_admin", "viewer"):
            connection.execute(insert(roles).values(id=uuid4(), code=code))


def test_guid_binding_is_stable_refreshes_roles_and_never_enables_disabled_user(ingest_setup):
    _, engine, *_ = ingest_setup
    seed_roles(engine)
    guid = str(uuid4())
    subject = Subject("ldap", guid, "alice", frozenset({"storage_admin"}))
    user = bind_subject(engine, subject)
    assert user is not None
    store = SessionStore(engine)
    issued = store.issue(user)
    renamed = Subject("ldap", guid, "renamed", frozenset({"viewer"}))
    assert bind_subject(engine, renamed) == user
    assert store.resolve(issued.token).actor.roles == frozenset({"viewer"})
    with engine.begin() as connection:
        connection.execute(update(users).where(users.c.id == user).values(enabled=False))
    assert bind_subject(engine, subject) is None
    assert store.resolve(issued.token) is None
    with engine.connect() as connection:
        row = connection.execute(select(users).where(users.c.id == user)).one()
        assert row.enabled is False and row.provider_subject == guid and row.password_hash is None


def test_parallel_same_guid_provisions_one_user(ingest_setup):
    _, engine, *_ = ingest_setup
    seed_roles(engine)
    subject = Subject("ldap", str(uuid4()), "alice", frozenset({"viewer"}))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: bind_subject(engine, subject), range(8)))
    assert results[0] is not None and len(set(results)) == 1
    with engine.connect() as connection:
        assert len(connection.execute(select(users)).all()) == 1


def test_role_refresh_preserves_unchanged_assignments_and_audits_changes(ingest_setup):
    _, engine, *_ = ingest_setup
    seed_roles(engine)
    subject = Subject("ldap", str(uuid4()), "alice", frozenset({"viewer"}))
    user = bind_subject(engine, subject)
    with engine.connect() as connection:
        assignment = connection.scalar(select(user_roles.c.id).where(user_roles.c.user_id == user))
    assert bind_subject(engine, subject) == user
    with engine.connect() as connection:
        assert (
            connection.scalar(select(user_roles.c.id).where(user_roles.c.user_id == user))
            == assignment
        )
        assert connection.scalars(select(audit_log.c.action)).all() == ["auth.roles_refreshed"]


@pytest.mark.parametrize(
    "case",
    [
        "local_collision",
        "recreated_guid",
        "unknown_role",
        "empty_role",
        "unknown_provider",
        "invalid_guid",
        "missing_seed",
    ],
)
def test_untrusted_or_conflicting_subjects_cannot_take_over_identity(ingest_setup, case):
    _, engine, *_ = ingest_setup
    if case != "missing_seed":
        seed_roles(engine)
    provider, guid, assigned = "ldap", str(uuid4()), frozenset({"viewer"})
    if case in {"local_collision", "recreated_guid"}:
        with engine.begin() as connection:
            connection.execute(
                insert(users).values(
                    id=uuid4(),
                    username="alice",
                    auth_provider="local" if case == "local_collision" else "ldap",
                    provider_subject=str(uuid4()),
                )
            )
    if case == "unknown_role":
        assigned = frozenset({"unknown"})
    if case == "empty_role":
        assigned = frozenset()
    if case == "unknown_provider":
        provider = "unknown"
    if case == "invalid_guid":
        guid = "invalid"
    assert bind_subject(engine, Subject(provider, guid, "alice", assigned)) is None
    if case == "missing_seed":
        with engine.connect() as connection:
            assert connection.execute(select(users)).all() == []
