import json
import logging
import logging.config
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from uvicorn.config import LOGGING_CONFIG

from apps.api.main import create_app
from apps.worker.health import is_fresh
from packages.shared.logging import JsonFormatter, configure_logging
from packages.shared.settings import Settings


def test_health_runs_without_sentry_dsn():
    settings = Settings(database_url='sqlite://', sentry_dsn='')
    engine = create_engine(
        'sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool
    )
    with TestClient(create_app(settings, engine)) as client:
        assert client.get('/health').json() == {'status': 'ok'}
        assert client.get('/ready').status_code == 200


def test_database_unavailable_is_not_healthy_or_secret_leaking():
    settings = Settings(database_url='postgresql+psycopg://user:private@127.0.0.1:1/missing')
    engine = create_engine(settings.database_url, connect_args={'connect_timeout': 1})
    with TestClient(create_app(settings, engine)) as client:
        response = client.get('/ready')
        assert response.status_code == 503
        assert response.json() == {'status': 'unavailable'}
        assert 'private' not in response.text
        assert client.get('/health').status_code == 200


def test_logs_omit_exception_details_and_untrusted_messages():
    record = logging.LogRecord('storage', logging.ERROR, '', 1,
                               'password=private', (), None)
    record.event = 'database_unavailable'
    record.secret = 'private'
    payload = JsonFormatter().format(record)
    assert 'private' not in payload
    parsed = json.loads(payload)
    assert parsed['event'] == 'database_unavailable'
    assert datetime.fromisoformat(parsed['timestamp']).tzinfo is not None


def test_worker_health_rejects_missing_stale_and_future_heartbeats():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert is_fresh(now - timedelta(seconds=5), now, 30)
    assert not is_fresh(None, now, 30)
    assert not is_fresh(now - timedelta(seconds=31), now, 30)
    assert not is_fresh(now + timedelta(seconds=1), now, 30)


def test_worker_interval_must_fit_health_window():
    with pytest.raises(ValueError):
        Settings(worker_interval_seconds=60, worker_stale_seconds=30)


def test_uvicorn_messages_are_json_and_omit_exception_values(capsys):
    logging.config.dictConfig(LOGGING_CONFIG)
    configure_logging()
    logging.getLogger('uvicorn.error').error('password=private', exc_info=RuntimeError('private'))
    output = capsys.readouterr().err
    assert 'private' not in output
    assert json.loads(output)['logger'] == 'uvicorn.error'
