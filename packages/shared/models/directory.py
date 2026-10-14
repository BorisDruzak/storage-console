"""Append-only directory pages and observations; no Web user/role relationship."""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

from .base import identity, metadata, reference, timestamp

# A separate derived index avoids updating the immutable native-evidence table.
audit_client_ips = Table(
    "audit_client_ip_observations",
    metadata,
    reference("audit_evidence_id", "windows_audit_evidence.id"),
    reference("source_node_id", "source_nodes.id"),
    Column("client_ip_key", String(45), nullable=False),
    UniqueConstraint("audit_evidence_id", name="uq_audit_client_ip_evidence"),
    Index("ix_audit_client_ip_source", "source_node_id", "client_ip_key"),
)

directory_snapshots = Table(
    "directory_snapshots",
    metadata,
    identity(),
    reference("source_node_id", "source_nodes.id"),
    reference("collector_id", "collectors.id"),
    Column("dns_domain", String(253), nullable=False),
    Column("domain_sid", String(64), nullable=False),
    timestamp("observed_at"),
    timestamp("received_at", default_now=True),
    Column("state", String(16), nullable=False),
    Column("next_page", Integer, nullable=False),
    Column("record_count", Integer, nullable=False),
    Column("payload_bytes", BigInteger, nullable=False),
    Column("error_code", String(64)),
    CheckConstraint(
        "state IN ('COLLECTING','COMPLETE','ERROR')", name="ck_directory_snapshot_state"
    ),
    CheckConstraint(
        "next_page BETWEEN 1 AND 512 AND record_count BETWEEN 0 AND 100000 "
        "AND payload_bytes BETWEEN 1 AND 33554432",
        name="ck_directory_snapshot_bounds",
    ),
    Index(
        "ix_directory_latest",
        "source_node_id",
        "collector_id",
        "dns_domain",
        "domain_sid",
        "observed_at",
        "id",
    ),
    Index(
        "ix_directory_complete",
        "source_node_id",
        "collector_id",
        "dns_domain",
        "domain_sid",
        "state",
        "observed_at",
        "id",
    ),
)
directory_pages = Table(
    "directory_pages",
    metadata,
    reference("snapshot_id", "directory_snapshots.id"),
    reference("receipt_id", "ingest_batches.id"),
    Column("page_index", Integer, nullable=False),
    Column("record_count", Integer, nullable=False),
    Column("payload_sha256", String(64), nullable=False),
    UniqueConstraint("snapshot_id", "page_index", name="uq_directory_page"),
    UniqueConstraint("receipt_id", name="uq_directory_page_receipt"),
)
directory_users = Table(
    "directory_user_observations",
    metadata,
    reference("snapshot_id", "directory_snapshots.id"),
    Column("sid", String(64), nullable=False),
    Column("object_guid", Uuid, nullable=False),
    Column("payload", JSONB, nullable=False),
    UniqueConstraint("snapshot_id", "sid", name="uq_directory_user_sid"),
    UniqueConstraint("snapshot_id", "object_guid", name="uq_directory_user_guid"),
)
client_name_observations = Table(
    "client_name_observations",
    metadata,
    identity(),
    reference("source_node_id", "source_nodes.id"),
    reference("collector_id", "collectors.id"),
    reference("receipt_id", "ingest_batches.id"),
    Column("dns_domain", String(253), nullable=False),
    Column("domain_sid", String(64), nullable=False),
    Column("client_ip_key", String(45), nullable=False),
    timestamp("observed_at"),
    timestamp("expires_at"),
    timestamp("received_at", default_now=True),
    Column("payload", JSONB, nullable=False),
    UniqueConstraint("receipt_id", name="uq_client_name_receipt"),
    Index(
        "ix_client_name_latest",
        "source_node_id",
        "collector_id",
        "dns_domain",
        "domain_sid",
        "client_ip_key",
        "observed_at",
        "id",
    ),
)
