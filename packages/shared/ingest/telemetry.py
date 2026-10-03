from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.engine import Connection

from packages.contracts.diagnostics import DiagnosticRecord
from packages.contracts.telemetry import TelemetryRecord
from packages.shared.models.telemetry import diagnostic_bundles, metric_samples_1m


def telemetry(connection: Connection, source: UUID, record: TelemetryRecord) -> None:
    connection.execute(
        insert(metric_samples_1m).values(source_node_id=source, **record.model_dump())
    )


def diagnostic(connection: Connection, source: UUID, record: DiagnosticRecord) -> None:
    values = record.model_dump(exclude={"occurred_at"})
    connection.execute(
        insert(diagnostic_bundles).values(
            source_node_id=source, triggered_at=record.occurred_at, **values
        )
    )
