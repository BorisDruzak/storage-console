import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import insert, inspect, select, update
from sqlalchemy.exc import IntegrityError

REQUIRED_TABLES = {
    "source_nodes",
    "collectors",
    "collector_heartbeats",
    "volumes",
    "shares",
    "filesystem_objects",
    "object_path_history",
    "change_events",
    "event_attributions",
    "event_evidence_links",
    "metric_samples_1m",
    "metric_samples_1h",
    "metric_samples_1d",
    "diagnostic_bundles",
    "health_signals",
    "health_findings",
    "incidents",
    "incident_events",
    "health_policies",
    "policy_exceptions",
    "principals",
    "ad_groups",
    "group_memberships",
    "acl_templates",
    "acl_snapshots",
    "acl_aces",
    "acl_findings",
    "vss_snapshots",
    "backup_jobs",
    "backup_snapshots",
    "backup_verifications",
    "restore_tests",
    "recovery_policies",
    "hygiene_snapshots",
    "scope_stats",
    "long_path_samples",
    "large_file_samples",
    "temp_artifact_stats",
    "duplicate_candidates",
    "discovery_jobs",
    "discovery_series",
    "discovery_schema_families",
    "digitization_candidates",
    "users",
    "roles",
    "user_roles",
    "audit_log",
}


def test_schema_covers_required_domains_and_aware_timestamps():
    from packages.shared.models import metadata

    assert REQUIRED_TABLES <= metadata.tables.keys()
    for table in metadata.tables.values():
        for column in table.columns:
            if column.name.endswith("_at"):
                assert getattr(column.type, "timezone", False), f"{table.name}.{column.name}"


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required")
def test_canonical_identity_constraints_and_deleted_last_known_path():
    from packages.shared.database import make_engine
    from packages.shared.models.activity import change_events
    from packages.shared.models.core import (
        filesystem_objects,
        source_nodes,
        volume_aliases,
        volumes,
    )

    engine = make_engine(os.environ["TEST_DATABASE_URL"])
    source, volume, object_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(
            insert(source_nodes).values(
                id=source, source_type="FILESERVER", hostname="synthetic", instance_id=str(source)
            )
        )
        connection.execute(
            insert(volumes).values(
                id=volume,
                source_node_id=source,
                unique_identity="synthetic-volume",
                filesystem="NTFS",
            )
        )
        for alias in ["X:", "Y:"]:
            connection.execute(
                insert(volume_aliases).values(
                    volume_id=volume, alias=alias, first_seen_at=now, last_seen_at=now
                )
            )
        assert connection.scalar(select(volumes.c.id).where(volumes.c.id == volume)) == volume
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                insert(volumes).values(
                    source_node_id=source, unique_identity="synthetic-volume", filesystem="NTFS"
                )
            )
        connection.execute(
            insert(filesystem_objects).values(
                id=object_id,
                volume_id=volume,
                file_id="42",
                object_type="FILE",
                current_name="Отчёт.txt",
                current_relative_path="Отдел/Отчёт.txt",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                insert(filesystem_objects).values(
                    volume_id=volume,
                    file_id="42",
                    object_type="FILE",
                    current_name="Duplicate",
                    current_relative_path="Duplicate",
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        connection.execute(
            update(filesystem_objects)
            .where(filesystem_objects.c.id == object_id)
            .values(deleted_at=now)
        )
        row = connection.execute(
            select(filesystem_objects).where(filesystem_objects.c.id == object_id)
        ).one()
        assert row.current_relative_path == "Отдел/Отчёт.txt"
        assert row.deleted_at.tzinfo is not None
        for volume_identity in ["unresolved-volume-a", "unresolved-volume-b"]:
            connection.execute(
                insert(change_events).values(
                    source_node_id=source,
                    volume_identity=volume_identity,
                    file_id="42",
                    event_type="WRITE",
                    occurred_at=now,
                )
            )
        pending = (
            connection.execute(
                select(change_events.c.volume_identity).where(
                    change_events.c.source_node_id == source,
                    change_events.c.object_id.is_(None),
                )
            )
            .scalars()
            .all()
        )
        assert set(pending) == {"unresolved-volume-a", "unresolved-volume-b"}
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                insert(volumes).values(
                    source_node_id=uuid4(),
                    unique_identity="orphan",
                    filesystem="NTFS",
                )
            )
        assert REQUIRED_TABLES <= set(inspect(connection).get_table_names())
        transaction.rollback()
    engine.dispose()
