from sqlalchemy import Column, Index, String, Table, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from .base import identity, metadata, reference, timestamp

health_policies = Table(
    "health_policies",
    metadata,
    identity(),
    Column("name", String(128), nullable=False, unique=True),
    Column("domain", String(32), nullable=False),
    Column("policy_type", String(64), nullable=False),
    Column("parameters", JSONB, nullable=False),
    timestamp("created_at", default_now=True),
)
policy_exceptions = Table(
    "policy_exceptions",
    metadata,
    identity(),
    reference("policy_id", "health_policies.id"),
    reference("source_node_id", "source_nodes.id"),
    Column("scope_identity", String(255)),
    Column("reason", Text, nullable=False),
    timestamp("expires_at", nullable=True),
)
health_signals = Table(
    "health_signals",
    metadata,
    identity(),
    reference("source_node_id", "source_nodes.id"),
    Column("domain", String(32), nullable=False),
    Column("signal_type", String(64), nullable=False),
    Column("scope_identity", String(255)),
    timestamp("occurred_at"),
    Column("measurement", JSONB, nullable=False),
    Index("ix_signals_source_domain_time", "source_node_id", "domain", "occurred_at"),
)
health_findings = Table(
    "health_findings",
    metadata,
    identity(),
    reference("signal_id", "health_signals.id"),
    reference("policy_id", "health_policies.id"),
    Column("state", String(32), nullable=False),
    Column("cause_class", String(64), nullable=False),
    Column("fingerprint", String(64), nullable=False),
    timestamp("evaluated_at"),
)
incidents = Table(
    "incidents",
    metadata,
    identity(),
    reference("source_node_id", "source_nodes.id"),
    Column("domain", String(32), nullable=False),
    Column("fingerprint", String(64), nullable=False),
    Column("state", String(32), nullable=False),
    timestamp("opened_at"),
    timestamp("last_seen_at"),
    timestamp("resolved_at", nullable=True),
    UniqueConstraint("source_node_id", "fingerprint", name="uq_incident_fingerprint"),
)
incident_events = Table(
    "incident_events",
    metadata,
    identity(),
    reference("incident_id", "incidents.id"),
    reference("finding_id", "health_findings.id", nullable=True),
    Column("event_type", String(32), nullable=False),
    timestamp("occurred_at"),
)
