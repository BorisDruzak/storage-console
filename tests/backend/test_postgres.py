import os
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from apps.worker.health import check_health
from apps.worker.main import publish_heartbeat
from packages.shared.database import make_engine, service_heartbeats


@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'), reason='Disposable PostgreSQL required')
def test_worker_heartbeat_upsert_and_freshness():
    engine = make_engine(os.environ['TEST_DATABASE_URL'])
    with engine.begin() as conn:
        conn.execute(service_heartbeats.delete())
    assert not check_health(engine, 30)
    publish_heartbeat(engine)
    publish_heartbeat(engine)
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(service_heartbeats)) == 1
    assert check_health(engine, 30)
    with engine.begin() as conn:
        conn.execute(
            update(service_heartbeats).values(last_seen_at=func.now() - timedelta(seconds=31))
        )
    assert not check_health(engine, 30)
    engine.dispose()
