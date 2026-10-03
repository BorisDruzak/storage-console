from sqlalchemy import BigInteger, CheckConstraint, Column, Float, Integer, String, Table, Text
from sqlalchemy.dialects.postgresql import JSONB

from .base import identity, metadata, reference, timestamp

discovery_jobs = Table(
    "discovery_jobs",
    metadata,
    identity(),
    reference("source_node_id", "source_nodes.id"),
    Column("scope_identity", Text, nullable=False),
    Column("extensions", JSONB, nullable=False),
    Column("max_files", Integer, nullable=False),
    Column("max_bytes", BigInteger, nullable=False),
    Column("parser", String(64), nullable=False),
    Column("purpose", Text, nullable=False),
    Column("state", String(32), nullable=False),
    timestamp("approved_at", nullable=True),
    timestamp("created_at", default_now=True),
    timestamp("finished_at", nullable=True),
    CheckConstraint("max_files > 0 AND max_bytes > 0", name="ck_discovery_limits"),
)
discovery_schema_families = Table(
    "discovery_schema_families",
    metadata,
    identity(),
    reference("job_id", "discovery_jobs.id"),
    Column("fingerprint", String(64), nullable=False),
    Column("schema_description", JSONB, nullable=False),
    Column("file_count", Integer, nullable=False),
)
discovery_series = Table(
    "discovery_series",
    metadata,
    identity(),
    reference("job_id", "discovery_jobs.id"),
    reference("schema_family_id", "discovery_schema_families.id", nullable=True),
    Column("name_pattern", Text, nullable=False),
    Column("cadence", String(64)),
    Column("confidence", Float, nullable=False),
    CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_series_confidence"),
)
digitization_candidates = Table(
    "digitization_candidates",
    metadata,
    identity(),
    reference("series_id", "discovery_series.id"),
    Column("workflow_state", String(32), nullable=False),
    Column("confidence", Float, nullable=False),
    Column("reason_code", String(64), nullable=False),
    timestamp("created_at", default_now=True),
    CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_digitization_confidence"),
)
