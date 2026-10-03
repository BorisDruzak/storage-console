from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Table, insert
from sqlalchemy.engine import Connection

from packages.contracts.common import Contract
from packages.contracts.hygiene import HygieneRecord
from packages.shared.models.hygiene import (
    hygiene_snapshots,
    large_file_samples,
    long_path_samples,
    scope_stats,
    temp_artifact_stats,
)


def hygiene(connection: Connection, source: UUID, record: HygieneRecord) -> None:
    snapshot = connection.scalar(
        insert(hygiene_snapshots)
        .values(
            source_node_id=source,
            scope_identity=record.scope_identity,
            observed_at=record.occurred_at,
            quality=record.quality,
        )
        .returning(hygiene_snapshots.c.id)
    )
    connection.execute(
        insert(scope_stats).values(
            snapshot_id=snapshot,
            file_count=record.file_count,
            directory_count=record.directory_count,
            total_bytes=record.total_bytes,
            zero_byte_count=record.zero_byte_count,
        )
    )
    def samples(table: Table, records: Sequence[Contract]) -> None:
        for sample in records:
            connection.execute(insert(table).values(snapshot_id=snapshot, **sample.model_dump()))

    samples(long_path_samples, record.long_paths)
    samples(large_file_samples, record.large_files)
    samples(temp_artifact_stats, record.temp_artifacts)
