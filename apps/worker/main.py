import logging
import signal
import threading

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from packages.shared.database import make_engine, service_heartbeats
from packages.shared.logging import configure_logging
from packages.shared.observability import configure_sentry
from packages.shared.settings import Settings

logger = logging.getLogger(__name__)


def publish_heartbeat(engine: Engine) -> None:
    statement = insert(service_heartbeats).values(service='worker', last_seen_at=func.now())
    statement = statement.on_conflict_do_update(
        index_elements=['service'], set_={'last_seen_at': func.now()},
    )
    with engine.begin() as connection:
        connection.execute(statement)


def run(settings: Settings, engine: Engine, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            publish_heartbeat(engine)
        except SQLAlchemyError:
            logger.warning('runtime', extra={'event': 'worker_database_unavailable'})
        stop.wait(settings.worker_interval_seconds)


def main() -> None:
    configure_logging()
    settings = Settings()
    configure_sentry(settings)
    engine = make_engine(settings.database_url)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    logger.info('runtime', extra={'event': 'worker_started'})
    try:
        run(settings, engine, stop)
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
