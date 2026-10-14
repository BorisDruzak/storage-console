"""Real additive DDL preserves native witnesses and freezes new observations."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from packages.shared.models.audit import audit_evidence
from packages.shared.models.core import collectors, source_nodes
from packages.shared.models.directory import audit_client_ips


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Own PostgreSQL required")
def test_directory_revision_is_additive_and_observations_are_immutable(monkeypatch):
    base = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "directory_migration_" + uuid4().hex
    with base.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(os.environ["TEST_DATABASE_URL"]).update_query_dict(
        {"options": "-csearch_path=" + schema}
    )
    engine = create_engine(url)
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    config = Config("alembic.ini")
    try:
        command.upgrade(config, "0008")
        source, collector, evidence = uuid4(), uuid4(), uuid4()
        payload = {"client_ip": "::ffff:192.0.2.10", "account": "old-native", "workstation": None}
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
                    collector_type="AUDIT_WINDOWS",
                    token_hash="a" * 64,
                )
            )
            conn.execute(
                insert(audit_evidence).values(
                    id=evidence,
                    source_node_id=source,
                    audit_collector_id=collector,
                    host_id=uuid4(),
                    generation=uuid4(),
                    channel="Security",
                    record_id=1,
                    event_id=4624,
                    occurred_at=datetime.now(UTC),
                    payload=payload,
                    digest="b" * 64,
                )
            )
        command.upgrade(config, "0009")
        command.check(config)
        with engine.connect() as conn:
            row = conn.execute(select(audit_evidence)).mappings().one()
            assert row["payload"] == payload and row["digest"] == "b" * 64 and row["id"] == evidence
            assert conn.scalar(select(audit_client_ips.c.client_ip_key)) == "192.0.2.10"
            assert conn.scalar(select(collectors.c.directory_scope)) is None
        for statement in (
            "UPDATE windows_audit_evidence SET digest=repeat('c',64)",
            "DELETE FROM audit_client_ip_observations",
            "TRUNCATE audit_client_ip_observations",
        ):
            with pytest.raises(DBAPIError), engine.begin() as conn:
                conn.execute(text(statement))
        command.downgrade(config, "0008")
        with engine.connect() as conn:
            assert conn.scalar(select(audit_evidence.c.payload)) == payload
        command.upgrade(config, "0009")
        command.check(config)
    finally:
        engine.dispose()
        with base.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()
