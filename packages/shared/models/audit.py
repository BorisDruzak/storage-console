"""Minimal immutable normalized Security evidence, independent of USN history."""

from sqlalchemy import BigInteger, Column, Index, Integer, String, Table, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from .base import identity, metadata, reference, timestamp

audit_evidence = Table(
    "windows_audit_evidence",
    metadata,
    identity(),
    reference("source_node_id", "source_nodes.id"),
    reference("audit_collector_id", "collectors.id"),
    Column("host_id", Uuid, nullable=False),
    Column("generation", Uuid, nullable=False),
    Column("channel", String(32), nullable=False),
    Column("record_id", BigInteger, nullable=False),
    Column("event_id", Integer, nullable=False),
    timestamp("occurred_at"),
    Column("volume_id", String(255)),
    Column("path_key", String(64)),
    Column("sid", String(255)),
    Column("logon_id", String(20)),
    Column("payload", JSONB, nullable=False),
    Column("digest", String(64), nullable=False),
    timestamp("first_received_at", default_now=True),
    UniqueConstraint(
        "source_node_id",
        "host_id",
        "channel",
        "generation",
        "record_id",
        name="uq_audit_event_identity",
    ),
    Index("ix_audit_source_time", "source_node_id", "occurred_at"),
    Index(
        "ix_audit_source_volume_path_time", "source_node_id", "volume_id", "path_key", "occurred_at"
    ),
    Index("ix_audit_source_logon_time", "source_node_id", "logon_id", "occurred_at"),
    Index("ix_audit_source_sid_time", "source_node_id", "sid", "occurred_at"),
)

audit_streams = Table(
    "windows_audit_streams",
    metadata,
    reference("collector_id", "collectors.id"),
    Column("host_id", Uuid),
    Column("health", JSONB, nullable=False),
    timestamp("reported_at", nullable=True),
    timestamp("accepted_at", nullable=True),
    UniqueConstraint("collector_id", name="uq_audit_stream_collector"),
)

audit_correlations = Table(
    "windows_audit_correlations",
    metadata,
    reference("change_event_id", "change_events.id"),
    Column("rule_version", String(64), nullable=False),
    Column("class", String(32), nullable=False),
    Column("reason", String(64), nullable=False),
    Column("actor", JSONB),
    timestamp("evaluated_at", default_now=True),
    UniqueConstraint("change_event_id", name="uq_audit_correlation_change"),
)

audit_candidates = Table(
    "windows_audit_candidates",
    metadata,
    identity(),
    reference("change_event_id", "change_events.id"),
    reference("audit_evidence_id", "windows_audit_evidence.id"),
    Column("rule_version", String(64), nullable=False),
    Column("method", String(64), nullable=False),
    Column("class", String(32), nullable=False),
    Column("reason", String(64), nullable=False),
    UniqueConstraint(
        "change_event_id", "audit_evidence_id", "rule_version", name="uq_audit_candidate"
    ),
    Index("ix_audit_candidate_evidence", "audit_evidence_id"),
)

# Independent inventory and continuity witnesses; never reconstructed from a
# target USN change or from mutable current-path fields.
audit_identity_observations = Table(
    "windows_audit_identity_observations",
    metadata,
    identity(),
    reference("source_node_id", "source_nodes.id"),
    reference("collector_id", "collectors.id"),
    reference("receipt_id", "ingest_batches.id"),
    Column("volume_id", String(255), nullable=False),
    Column("file_id", String(255), nullable=False),
    Column("path_key", String(64), nullable=False),
    Column("payload", JSONB, nullable=False),
    timestamp("occurred_at"),
    Index("ix_audit_identity_file_time", "source_node_id", "volume_id", "file_id", "occurred_at"),
    Index("ix_audit_identity_path_time", "source_node_id", "volume_id", "path_key", "occurred_at"),
)

audit_health_observations = Table(
    "windows_audit_health_observations",
    metadata,
    identity(),
    reference("collector_id", "collectors.id"),
    reference("receipt_id", "ingest_batches.id"),
    timestamp("occurred_at"),
    Column("payload", JSONB, nullable=False),
    Index("ix_audit_health_collector_time", "collector_id", "occurred_at"),
)
