from sqlalchemy import CheckConstraint, Column, Float, Index, String, Table, Text

from .base import identity, metadata, reference, timestamp

change_events = Table(
    "change_events",
    metadata,
    identity(),
    reference("source_node_id", "source_nodes.id"),
    reference("object_id", "filesystem_objects.id", nullable=True),
    Column("volume_identity", String(255), nullable=False),
    Column("event_type", String(32), nullable=False),
    timestamp("occurred_at"),
    Column("old_relative_path", Text),
    Column("new_relative_path", Text),
    Column("file_id", String(255)),
    Column("parent_file_id", String(255)),
    Column("reason_mask", String(64)),
    Column("source_event_id", String(255)),
    CheckConstraint(
        "event_type IN ('CREATE','WRITE','RENAME','DELETE','METADATA_CHANGE','SECURITY_CHANGE')",
        name="ck_change_event_type",
    ),
    Index("ix_changes_source_time", "source_node_id", "occurred_at"),
    Index(
        "ix_changes_object_identity_time",
        "source_node_id",
        "volume_identity",
        "file_id",
        "occurred_at",
    ),
)
event_attributions = Table(
    "event_attributions",
    metadata,
    identity(),
    reference("change_event_id", "change_events.id"),
    reference("principal_id", "principals.id", nullable=True),
    Column("client_identity", String(255)),
    Column("confidence", Float, nullable=False),
    Column("method", String(64), nullable=False),
    CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_attribution_confidence"),
)
event_evidence_links = Table(
    "event_evidence_links",
    metadata,
    identity(),
    reference("change_event_id", "change_events.id"),
    Column("evidence_type", String(32), nullable=False),
    Column("evidence_reference", String(255)),
    Column("source_event_id", String(255)),
    timestamp("occurred_at"),
)

collector_events = Table(
    "collector_events",
    metadata,
    identity(),
    reference("source_node_id", "source_nodes.id"),
    reference("change_event_id", "change_events.id", nullable=True),
    Column("source_event_id", String(255), nullable=False),
    Column("evidence_type", String(32), nullable=False),
    timestamp("occurred_at"),
    Column("actor_identity", String(255)),
    Column("client_identity", String(255)),
    Column("confidence", Float, nullable=False),
    CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_collector_event_confidence"),
    Index("ix_collector_events_source_time", "source_node_id", "occurred_at"),
)
