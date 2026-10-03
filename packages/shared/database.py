from sqlalchemy import Column, DateTime, MetaData, String, Table, create_engine
from sqlalchemy.engine import Engine

metadata = MetaData()
service_heartbeats = Table(
    'service_heartbeats', metadata,
    Column('service', String(64), primary_key=True),
    Column('last_seen_at', DateTime(timezone=True), nullable=False),
)


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, connect_args={'connect_timeout': 3})
