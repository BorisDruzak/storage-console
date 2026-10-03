from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from packages.contracts.events import EvidenceRecord
from packages.shared.models.activity import change_events, collector_events, event_evidence_links

from .core import IngestConflict


def evidence(connection: Connection, source: UUID, record: EvidenceRecord) -> None:
    if record.change_event_id is not None:
        target = connection.scalar(
            select(change_events.c.id).where(
                change_events.c.id == record.change_event_id,
                change_events.c.source_node_id == source,
            )
        )
        if target is None:
            raise IngestConflict("UNKNOWN_CHANGE_EVENT")
    raw_id = connection.scalar(
        insert(collector_events)
        .values(source_node_id=source, **record.model_dump())
        .returning(collector_events.c.id)
    )
    if record.change_event_id is not None:
        connection.execute(
            insert(event_evidence_links).values(
                change_event_id=record.change_event_id,
                evidence_type=record.evidence_type,
                evidence_reference=str(raw_id),
                source_event_id=record.source_event_id,
                occurred_at=record.occurred_at,
            )
        )
    # Collector confidence is evidence, not independently verified attribution or a health finding.
