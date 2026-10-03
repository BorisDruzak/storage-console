from sqlalchemy import CheckConstraint, Column, Integer, String, Table, Text, UniqueConstraint

from .base import identity, metadata, reference, timestamp

vss_snapshots = Table(
    "vss_snapshots",
    metadata,
    identity(),
    reference("volume_id", "volumes.id"),
    Column("snapshot_identity", String(255), nullable=False),
    timestamp("created_at"),
    Column("state", String(32), nullable=False),
    UniqueConstraint("volume_id", "snapshot_identity", name="uq_vss_identity"),
)
recovery_policies = Table(
    "recovery_policies",
    metadata,
    identity(),
    reference("source_node_id", "source_nodes.id"),
    Column("workload_identity", String(255), nullable=False),
    Column("rpo_seconds", Integer, nullable=False),
    Column("rto_seconds", Integer, nullable=False),
    Column("retention_days", Integer, nullable=False),
    CheckConstraint(
        "rpo_seconds > 0 AND rto_seconds > 0 AND retention_days > 0",
        name="ck_recovery_policy_intervals",
    ),
    UniqueConstraint("source_node_id", "workload_identity", name="uq_recovery_policy_workload"),
)
backup_jobs = Table(
    "backup_jobs",
    metadata,
    identity(),
    reference("source_node_id", "source_nodes.id"),
    Column("job_identity", String(255), nullable=False),
    Column("workload_identity", String(255), nullable=False),
    Column("state", String(32), nullable=False),
    timestamp("started_at"),
    timestamp("finished_at", nullable=True),
    Column("error_code", String(64)),
    UniqueConstraint("source_node_id", "job_identity", name="uq_backup_job_identity"),
)
backup_snapshots = Table(
    "backup_snapshots",
    metadata,
    identity(),
    reference("backup_job_id", "backup_jobs.id"),
    Column("snapshot_identity", String(255), nullable=False),
    timestamp("created_at"),
    Column("consistency", String(32), nullable=False),
    Column("storage_reference", Text),
    UniqueConstraint("backup_job_id", "snapshot_identity", name="uq_backup_snapshot_identity"),
)
backup_verifications = Table(
    "backup_verifications",
    metadata,
    identity(),
    reference("snapshot_id", "backup_snapshots.id"),
    timestamp("verified_at"),
    Column("state", String(32), nullable=False),
    Column("error_code", String(64)),
)
restore_tests = Table(
    "restore_tests",
    metadata,
    identity(),
    reference("snapshot_id", "backup_snapshots.id"),
    timestamp("tested_at"),
    Column("state", String(32), nullable=False),
    Column("measured_rto_seconds", Integer),
    Column("evidence_reference", Text),
    CheckConstraint("measured_rto_seconds >= 0", name="ck_restore_duration"),
)
