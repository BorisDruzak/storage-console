"""Bounded database-clock cleanup; retain the shared rate-lock row permanently."""

import hashlib
from datetime import datetime, timedelta
from typing import cast

from sqlalchemy import Connection, Engine, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert

from packages.shared.models.security import login_rate_buckets, user_sessions

GLOBAL_LOGIN_KEY = hashlib.sha256(b"login:global").hexdigest()


def lock_rate_rows(connection: Connection) -> None:
    connection.execute(
        insert(login_rate_buckets)
        .values(key=GLOBAL_LOGIN_KEY, window_started_at=func.clock_timestamp(), attempts=0)
        .on_conflict_do_nothing(index_elements=["key"])
    )
    connection.execute(
        select(login_rate_buckets.c.key)
        .where(login_rate_buckets.c.key == GLOBAL_LOGIN_KEY)
        .with_for_update()
    ).one()


def collect_auth_rows(engine: Engine, *, batch_size: int = 1000) -> tuple[int, int]:
    if type(batch_size) is not int or not 1 <= batch_size <= 1000:
        raise ValueError("AUTH_RETENTION_BATCH_INVALID")
    with engine.begin() as connection:
        now = cast(datetime, connection.scalar(select(func.clock_timestamp())))
        stale = or_(
            user_sessions.c.expires_at <= now,
            user_sessions.c.revoked_at.is_not(None),
            user_sessions.c.last_used_at <= now - timedelta(minutes=30),
        )
        ids = (
            select(user_sessions.c.id)
            .where(stale)
            .order_by(user_sessions.c.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        sessions = len(
            connection.execute(
                delete(user_sessions)
                .where(user_sessions.c.id.in_(ids))
                .returning(user_sessions.c.id)
            ).all()
        )
    with engine.begin() as connection:
        # Ticket consumers lock global→account. Keep the global row and follow the same
        # order so cleanup cannot delete an account between its upsert and locked read.
        lock_rate_rows(connection)
        now = cast(datetime, connection.scalar(select(func.clock_timestamp())))
        keys = (
            select(login_rate_buckets.c.key)
            .where(
                login_rate_buckets.c.key != GLOBAL_LOGIN_KEY,
                login_rate_buckets.c.window_started_at <= now - timedelta(minutes=10),
            )
            .order_by(login_rate_buckets.c.key)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        rates = len(
            connection.execute(
                delete(login_rate_buckets)
                .where(login_rate_buckets.c.key.in_(keys))
                .returning(login_rate_buckets.c.key)
            ).all()
        )
    return sessions, rates
