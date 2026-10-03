from sqlalchemy import BigInteger, CheckConstraint, Column, Integer, String, Table, Text

from .base import identity, metadata, reference, timestamp

hygiene_snapshots = Table(
    "hygiene_snapshots",
    metadata,
    identity(),
    reference("source_node_id", "source_nodes.id"),
    Column("scope_identity", Text, nullable=False),
    timestamp("observed_at"),
    Column("quality", String(16), nullable=False),
)
scope_stats = Table(
    "scope_stats",
    metadata,
    identity(),
    reference("snapshot_id", "hygiene_snapshots.id"),
    Column("file_count", BigInteger, nullable=False),
    Column("directory_count", BigInteger, nullable=False),
    Column("total_bytes", BigInteger, nullable=False),
    Column("zero_byte_count", BigInteger, nullable=False),
    CheckConstraint(
        "file_count >= 0 AND directory_count >= 0 AND total_bytes >= 0 AND zero_byte_count >= 0",
        name="ck_scope_stats_counts",
    ),
)
long_path_samples = Table(
    "long_path_samples",
    metadata,
    identity(),
    reference("snapshot_id", "hygiene_snapshots.id"),
    Column("relative_path", Text, nullable=False),
    Column("path_length", Integer, nullable=False),
    Column("bucket", String(16), nullable=False),
    CheckConstraint("path_length >= 0", name="ck_long_path_length"),
)
large_file_samples = Table(
    "large_file_samples",
    metadata,
    identity(),
    reference("snapshot_id", "hygiene_snapshots.id"),
    Column("relative_path", Text, nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    timestamp("last_write_at"),
    CheckConstraint("size_bytes >= 0", name="ck_large_file_size"),
)
temp_artifact_stats = Table(
    "temp_artifact_stats",
    metadata,
    identity(),
    reference("snapshot_id", "hygiene_snapshots.id"),
    Column("classification", String(16), nullable=False),
    Column("file_count", BigInteger, nullable=False),
    Column("total_bytes", BigInteger, nullable=False),
    CheckConstraint("classification IN ('ACTIVE','RECENT','STALE')", name="ck_temp_classification"),
    CheckConstraint("file_count >= 0 AND total_bytes >= 0", name="ck_temp_counts"),
)
duplicate_candidates = Table(
    "duplicate_candidates",
    metadata,
    identity(),
    reference("snapshot_id", "hygiene_snapshots.id"),
    Column("normalized_name", Text, nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("state", String(32), nullable=False),
    Column("candidate_count", Integer, nullable=False),
    CheckConstraint("size_bytes >= 0 AND candidate_count >= 2", name="ck_duplicate_counts"),
    CheckConstraint(
        "state IN ('CANDIDATE','HASH_PENDING','CONFIRMED','DIFFERENT_CONTENT','EXCLUDED')",
        name="ck_duplicate_state",
    ),
)
