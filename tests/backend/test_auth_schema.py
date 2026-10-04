from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError


def test_persistent_auth_domains_exist():
    from packages.shared.models import metadata

    assert {"user_sessions", "login_rate_buckets"} <= metadata.tables.keys()
    assert "enabled" in metadata.tables["users"].c


def test_session_identity_and_time_bounds_are_enforced(ingest_setup):
    from packages.shared.models.security import user_sessions, users

    _, engine, *_ = ingest_setup
    now, user = datetime.now(UTC), uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(users).values(id=user, username="synthetic-admin", auth_provider="local")
        )
        assert connection.scalar(select(users.c.enabled).where(users.c.id == user)) is True
        session = dict(
            user_id=user,
            token_hash="a" * 64,
            csrf_hash="b" * 64,
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(hours=8),
        )
        connection.execute(insert(user_sessions).values(**session))
        for invalid in (
            session,
            session | {"token_hash": "c" * 64, "user_id": uuid4()},
            session | {"token_hash": "c" * 64, "expires_at": now},
            session | {"token_hash": "c" * 64, "last_used_at": now - timedelta(seconds=1)},
            session | {"token_hash": "invalid-token"},
        ):
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(insert(user_sessions).values(**invalid))


def test_rate_counters_cannot_be_negative(ingest_setup):
    from packages.shared.models.security import login_rate_buckets

    _, engine, *_ = ingest_setup
    with engine.begin() as connection:
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                insert(login_rate_buckets).values(
                    key="a" * 64, window_started_at=datetime.now(UTC), attempts=-1
                )
            )
