import hmac
import json
from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from apps.api.auth import collector_token, token_hash
from packages.contracts.changes import ChangeRecord
from packages.contracts.common import BatchEnvelope, Contract, Record
from packages.contracts.heartbeat import HeartbeatRecord
from packages.contracts.inventory import (
    FileObjectRecord,
    InventoryRecord,
    ShareRecord,
    VolumeRecord,
)
from packages.shared.ingest.core import IngestConflict, change, inventory
from packages.shared.models.core import collector_heartbeats, collectors, source_nodes
from packages.shared.models.jobs import ingest_batches
from packages.shared.models.security import audit_log

Token = Annotated[str, Depends(collector_token)]


class Receipt(Contract):
    accepted: bool = True
    duplicate: bool


class ApiError(Contract):
    detail: str


def accept[T: Record](engine: Engine, kind: str, batch: BatchEnvelope[T], token: str) -> Receipt:
    digest = sha256(
        json.dumps(
            dict(kind=kind, batch=batch.model_dump(mode="json")),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    try:
        with engine.begin() as connection:
            collector = (
                connection.execute(
                    select(collectors)
                    .where(
                        collectors.c.id == batch.collector_id,
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if (
                collector is None
                or not collector["enabled"]
                or not hmac.compare_digest(
                    collector["token_hash"],
                    token_hash(token),
                )
            ):
                raise HTTPException(401, detail="COLLECTOR_AUTH_REQUIRED")
            source = collector["source_node_id"]
            connection.execute(
                select(source_nodes.c.id).where(source_nodes.c.id == source).with_for_update()
            ).one()
            previous = (
                connection.execute(
                    select(ingest_batches).where(
                        ingest_batches.c.collector_id == batch.collector_id,
                        ingest_batches.c.batch_id == batch.batch_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if previous is not None:
                if not hmac.compare_digest(previous["payload_sha256"], digest):
                    raise HTTPException(409, detail="BATCH_ID_CONFLICT")
                return Receipt(duplicate=True)
            receipt_id = connection.scalar(
                insert(ingest_batches)
                .values(
                    **batch.model_dump(exclude={"records"}),
                    kind=kind,
                    payload_sha256=digest,
                )
                .returning(ingest_batches.c.id)
            )
            for record in batch.records:
                if isinstance(record, HeartbeatRecord):
                    connection.execute(
                        insert(collector_heartbeats).values(
                            collector_id=batch.collector_id, **record.model_dump()
                        )
                    )
                elif isinstance(record, VolumeRecord | ShareRecord | FileObjectRecord):
                    inventory(connection, source, record)
                elif isinstance(record, ChangeRecord):
                    change(connection, source, record)
                else:
                    raise IngestConflict("UNSUPPORTED_RECORD")
            connection.execute(
                update(ingest_batches)
                .where(ingest_batches.c.id == receipt_id)
                .values(processed_at=func.now())
            )
            connection.execute(
                update(collectors)
                .where(collectors.c.id == batch.collector_id)
                .values(last_seen_at=func.now())
            )
            connection.execute(
                update(source_nodes)
                .where(source_nodes.c.id == source)
                .values(last_success_at=func.now())
            )
            connection.execute(
                insert(audit_log).values(
                    collector_id=batch.collector_id,
                    action="INGEST",
                    resource_type=kind,
                    resource_identity=batch.batch_id,
                    result="ACCEPTED",
                    details={"record_count": batch.record_count},
                )
            )
    except IngestConflict as error:
        raise HTTPException(409, detail=str(error)) from None
    except SQLAlchemyError:
        raise HTTPException(503, detail="INGEST_UNAVAILABLE") from None
    return Receipt(duplicate=False)


def router(engine: Engine) -> APIRouter:
    result = APIRouter(
        prefix="/api/v1/ingest",
        tags=["collector-ingest"],
        responses={status: {"model": ApiError} for status in (401, 409, 413, 422, 503)},
    )

    @result.post("/heartbeat", status_code=202)
    def heartbeat(batch: BatchEnvelope[HeartbeatRecord], token: Token) -> Receipt:
        return accept(engine, "heartbeat", batch, token)

    @result.post("/inventory", status_code=202)
    def inventory_batch(batch: BatchEnvelope[InventoryRecord], token: Token) -> Receipt:
        return accept(engine, "inventory", batch, token)

    @result.post("/changes", status_code=202)
    def changes_batch(batch: BatchEnvelope[ChangeRecord], token: Token) -> Receipt:
        return accept(engine, "changes", batch, token)

    return result
