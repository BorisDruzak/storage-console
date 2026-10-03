from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from packages.contracts.recovery import BackupRecord, VSSRecord
from packages.shared.models.recovery import (
    backup_jobs,
    backup_snapshots,
    backup_verifications,
    restore_tests,
    vss_snapshots,
)

from .core import IngestConflict, volume_id


def recovery(connection: Connection, source: UUID, record: BackupRecord | VSSRecord) -> None:
    if isinstance(record, VSSRecord):
        volume = volume_id(connection, source, record.volume_identity)
        existing = (
            connection.execute(
                select(vss_snapshots).where(
                    vss_snapshots.c.volume_id == volume,
                    vss_snapshots.c.snapshot_identity == record.snapshot_identity,
                )
            )
            .mappings()
            .one_or_none()
        )
        values: dict[str, object] = dict(
            created_at=record.created_at, state=record.state, observed_at=record.occurred_at
        )
        if existing is None:
            connection.execute(
                insert(vss_snapshots).values(
                    volume_id=volume, snapshot_identity=record.snapshot_identity, **values
                )
            )
        elif record.occurred_at >= existing["observed_at"]:
            connection.execute(
                update(vss_snapshots).where(vss_snapshots.c.id == existing["id"]).values(**values)
            )
        return
    job = (
        connection.execute(
            select(backup_jobs).where(
                backup_jobs.c.source_node_id == source,
                backup_jobs.c.job_identity == record.job_identity,
            )
        )
        .mappings()
        .one_or_none()
    )
    values = dict(
        workload_identity=record.workload_identity,
        state=record.state,
        started_at=record.started_at,
        finished_at=record.finished_at,
        observed_at=record.occurred_at,
        error_code=record.error_code,
    )
    current = job is None or record.occurred_at >= job["observed_at"]
    if job is None:
        job_id = connection.scalar(
            insert(backup_jobs)
            .values(source_node_id=source, job_identity=record.job_identity, **values)
            .returning(backup_jobs.c.id)
        )
    else:
        if job["workload_identity"] != record.workload_identity:
            raise IngestConflict("BACKUP_WORKLOAD_CONFLICT")
        job_id = job["id"]
        if current:
            connection.execute(
                update(backup_jobs).where(backup_jobs.c.id == job_id).values(**values)
            )
    if record.snapshot_identity is None:
        return
    snapshot = (
        connection.execute(
            select(backup_snapshots).where(
                backup_snapshots.c.backup_job_id == job_id,
                backup_snapshots.c.snapshot_identity == record.snapshot_identity,
            )
        )
        .mappings()
        .one_or_none()
    )
    snapshot_values = dict(
        created_at=record.snapshot_created_at,
        consistency=record.consistency,
        observed_at=record.occurred_at,
    )
    if snapshot is None:
        snapshot_id = connection.scalar(
            insert(backup_snapshots)
            .values(
                backup_job_id=job_id, snapshot_identity=record.snapshot_identity, **snapshot_values
            )
            .returning(backup_snapshots.c.id)
        )
    else:
        snapshot_id = snapshot["id"]
        if record.occurred_at >= snapshot["observed_at"]:
            connection.execute(
                update(backup_snapshots)
                .where(backup_snapshots.c.id == snapshot_id)
                .values(**snapshot_values)
            )
    if record.verification_state is not None:
        connection.execute(
            insert(backup_verifications).values(
                snapshot_id=snapshot_id,
                verified_at=record.verified_at,
                state=record.verification_state,
            )
        )
    if record.restore_test_state is not None:
        connection.execute(
            insert(restore_tests).values(
                snapshot_id=snapshot_id,
                tested_at=record.tested_at,
                state=record.restore_test_state,
                measured_rto_seconds=record.measured_rto_seconds,
            )
        )
