from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from packages.shared.database import make_engine, service_heartbeats
from packages.shared.settings import Settings


def is_fresh(last_seen: datetime | None, now: datetime, max_age_seconds: int) -> bool:
    if last_seen is None:
        return False
    age = (now - last_seen).total_seconds()
    return 0 <= age <= max_age_seconds


def check_health(engine: Engine, max_age_seconds: int) -> bool:
    try:
        with engine.connect() as connection:
            row = connection.execute(
                select(service_heartbeats.c.last_seen_at, func.now())
                .where(service_heartbeats.c.service == 'worker')
            ).first()
        return bool(row and is_fresh(row[0], row[1], max_age_seconds))
    except SQLAlchemyError:
        return False


def main() -> int:
    settings = Settings()
    engine = make_engine(settings.database_url)
    try:
        return 0 if check_health(engine, settings.worker_stale_seconds) else 1
    finally:
        engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
