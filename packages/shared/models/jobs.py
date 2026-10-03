from sqlalchemy import CheckConstraint, Column, Index, Integer, String, Table
from sqlalchemy.dialects.postgresql import JSONB

from .base import identity, metadata, reference, timestamp

ingest_batches = Table(
    "ingest_batches",
    metadata,
    identity(),
    reference("collector_id", "collectors.id"),
    Column("batch_id", String(255), nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("kind", String(32), nullable=False),
    Column("payload_sha256", String(64), nullable=False),
    Column("record_count", Integer, nullable=False),
    timestamp("sent_at"),
    timestamp("first_event_at"),
    timestamp("last_event_at"),
    timestamp("received_at", default_now=True),
    timestamp("processed_at", nullable=True),
    Index("uq_collector_batch_id", "collector_id", "batch_id", unique=True),
    CheckConstraint("record_count >= 0 AND schema_version = 1", name="ck_batch_schema_count"),
    CheckConstraint("last_event_at >= first_event_at", name="ck_batch_time_range"),
)
jobs = Table(
    "jobs",
    metadata,
    identity(),
    Column("kind", String(64), nullable=False),
    Column("idempotency_key", String(255), nullable=False, unique=True),
    Column("payload", JSONB, nullable=False),
    Column("status", String(16), nullable=False),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("max_attempts", Integer, nullable=False, server_default="5"),
    Column("error_code", String(64)),
    timestamp("next_attempt_at", default_now=True),
    timestamp("created_at", default_now=True),
    timestamp("completed_at", nullable=True),
    CheckConstraint("status IN ('PENDING','RETRY','COMPLETE','FAILED')", name="ck_job_status"),
    CheckConstraint("attempts >= 0 AND max_attempts > 0", name="ck_job_attempts"),
    Index("ix_jobs_status_due", "status", "next_attempt_at"),
)
