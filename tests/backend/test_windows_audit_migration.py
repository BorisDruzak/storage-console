"""Additive revision and immutable witnesses on actual PostgreSQL DDL."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from packages.shared.models.activity import change_events
from packages.shared.models.audit import audit_evidence
from packages.shared.models.core import collectors, source_nodes


def test_revision_preserves_usn_and_blocks_evidence_mutation(monkeypatch):
    base = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "audit_migration_" + uuid4().hex
    with base.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(os.environ["TEST_DATABASE_URL"]).update_query_dict(
        {"options": "-csearch_path=" + schema}
    )
    engine = create_engine(url)
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    config = Config("alembic.ini")
    try:
        command.upgrade(config, "0006")
        source, collector, change = uuid4(), uuid4(), uuid4()
        now = datetime.now(UTC)
        with engine.begin() as conn:
            conn.execute(
                insert(source_nodes).values(
                    id=source,
                    source_type="FILESERVER",
                    hostname="synthetic",
                    instance_id=str(source),
                )
            )
            conn.execute(
                insert(collectors).values(
                    id=collector,
                    source_node_id=source,
                    collector_type="WINDOWS",
                    token_hash="a" * 64,
                )
            )
            conn.execute(
                insert(change_events).values(
                    id=change,
                    source_node_id=source,
                    volume_identity="volume-a",
                    file_id="file-a",
                    event_type="WRITE",
                    occurred_at=now,
                )
            )
        command.upgrade(config, "head")
        command.check(config)
        with engine.begin() as conn:
            conn.execute(
                insert(audit_evidence).values(
                    source_node_id=source,
                    audit_collector_id=collector,
                    host_id=uuid4(),
                    generation=uuid4(),
                    channel="Security",
                    record_id=1,
                    event_id=4663,
                    occurred_at=now,
                    payload={},
                    digest="b" * 64,
                )
            )
        command.downgrade(config, "0007")
        with engine.connect() as conn:
            assert conn.execute(select(change_events.c.id)).scalar_one() == change
            assert len(conn.execute(select(audit_evidence)).all()) == 1
            assert not conn.scalar(
                text("""SELECT count(*) FROM pg_indexes
                WHERE schemaname=current_schema()
                AND indexname='ix_changes_source_volume_time_id'""")
            )
        command.upgrade(config, "head")
        command.check(config)
        for statement in (
            "UPDATE windows_audit_evidence SET digest=repeat('c',64)",
            "DELETE FROM windows_audit_evidence",
            "TRUNCATE windows_audit_evidence CASCADE",
        ):
            with pytest.raises(DBAPIError), engine.begin() as conn:
                conn.execute(text(statement))
        command.downgrade(config, "0006")
        with engine.connect() as conn:
            assert conn.execute(select(change_events.c.id)).scalar_one() == change
        command.upgrade(config, "head")
        command.check(config)
    finally:
        engine.dispose()
        with base.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()
