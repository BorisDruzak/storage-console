import hashlib
import threading
from datetime import timedelta

from sqlalchemy import func, insert, select, update

from packages.shared.auth.retention import collect_auth_rows
from packages.shared.models.security import login_rate_buckets, user_sessions
from packages.shared.settings import Settings


def test_cleanup_preserves_active_sessions_and_current_budgets(session_setup):
    store, engine, user, _ = session_setup
    active, idle, expired, revoked = [store.issue(user) for _ in range(4)]
    assert all((active, idle, expired, revoked))
    store.revoke(revoked.token)
    with engine.begin() as connection:
        connection.execute(
            update(user_sessions)
            .where(user_sessions.c.token_hash == hashlib.sha256(idle.token.encode()).hexdigest())
            .values(
                created_at=func.clock_timestamp() - timedelta(hours=1),
                last_used_at=func.clock_timestamp() - timedelta(minutes=31),
            )
        )
        connection.execute(
            update(user_sessions)
            .where(user_sessions.c.token_hash == hashlib.sha256(expired.token.encode()).hexdigest())
            .values(
                created_at=func.clock_timestamp() - timedelta(hours=9),
                last_used_at=func.clock_timestamp() - timedelta(hours=9),
                expires_at=func.clock_timestamp() - timedelta(hours=1),
            )
        )
        connection.execute(
            insert(login_rate_buckets),
            [
                {
                    "key": "a" * 64,
                    "window_started_at": connection.scalar(select(func.clock_timestamp()))
                    - timedelta(minutes=11),
                    "attempts": 1,
                },
                {
                    "key": "b" * 64,
                    "window_started_at": connection.scalar(select(func.clock_timestamp())),
                    "attempts": 5,
                },
            ],
        )
    assert collect_auth_rows(engine) == (3, 1)
    assert store.resolve(active.token) is not None
    for session in (idle, expired, revoked):
        assert store.resolve(session.token) is None
    with engine.connect() as connection:
        assert (
            connection.scalar(
                select(login_rate_buckets.c.attempts).where(login_rate_buckets.c.key == "b" * 64)
            )
            == 5
        )


def test_cleanup_batches_skip_locked_sessions(session_setup):
    store, engine, user, _ = session_setup
    tokens = [store.issue(user).token for _ in range(4)]
    for token in tokens:
        store.revoke(token)
    with engine.begin() as connection:
        connection.execute(
            select(user_sessions)
            .where(user_sessions.c.token_hash == hashlib.sha256(tokens[0].encode()).hexdigest())
            .with_for_update()
        ).one()
        assert collect_auth_rows(engine, batch_size=2)[0] == 2
        assert collect_auth_rows(engine, batch_size=2)[0] == 1
    assert collect_auth_rows(engine, batch_size=2)[0] == 1


def test_worker_runs_cleanup_at_bounded_interval_without_provider_secrets(
    session_setup, monkeypatch
):
    from apps.worker import main as worker

    store, engine, user, _ = session_setup
    store.revoke(store.issue(user).token)
    stop = threading.Event()
    cleanups, cycles = [], []
    timestamps = iter([0, 10, 61, 61])
    monkeypatch.setattr(worker.time, "monotonic", lambda: next(timestamps))

    def cleanup(database):
        result = collect_auth_rows(database)
        cleanups.append(result)
        return result

    def process(*args):
        cycles.append(True)
        if len(cycles) == 3:
            stop.set()
        return True

    monkeypatch.setattr(worker, "collect_auth_rows", cleanup)
    monkeypatch.setattr(worker, "process_one", process)
    worker.run(Settings(), engine, stop)
    assert cleanups == [(1, 0), (0, 0)]
    assert len(cycles) == 3
