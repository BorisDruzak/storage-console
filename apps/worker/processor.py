from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection, RowMapping

from packages.shared.jobs import Handler
from packages.shared.models.jobs import ingest_batches
from packages.shared.models.security import audit_log


def ingest_postprocess(connection: Connection, job: RowMapping) -> None:
    payload = job["payload"]
    if set(payload) != {"receipt_id"}:
        raise ValueError("INVALID_POSTPROCESS_PAYLOAD")
    receipt = (
        connection.execute(
            select(ingest_batches).where(
                ingest_batches.c.id == UUID(payload["receipt_id"]),
            )
        )
        .mappings()
        .one()
    )
    if receipt["processed_at"] is None:
        raise ValueError("INGEST_NOT_APPLIED")
    # Foundation dispatch acknowledgement. Operational policies are later waves.
    connection.execute(
        insert(audit_log).values(
            collector_id=receipt["collector_id"],
            action="INGEST_POSTPROCESSED",
            resource_type=receipt["kind"],
            resource_identity=receipt["batch_id"],
            result="COMPLETE",
            details={"receipt_id": str(receipt["id"])},
        )
    )


HANDLERS: dict[str, Handler] = {"ingest_postprocess": ingest_postprocess}
