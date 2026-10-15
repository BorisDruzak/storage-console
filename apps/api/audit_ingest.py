"""Source-bound immutable audit ingestion, accepting retained Stage A envelopes."""

import hmac
from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from starlette.concurrency import run_in_threadpool

from apps.api.auth import collector_token, token_hash
from apps.api.ingest import ApiError, Receipt
from packages.contracts.audit import AuditBatch
from packages.contracts.directory import normalized_ip
from packages.contracts.storage_identity import canonical_volume_identity
from packages.shared.jobs import enqueue
from packages.shared.models.audit import audit_evidence, audit_streams
from packages.shared.models.core import collectors, source_nodes, volumes
from packages.shared.models.directory import audit_client_ips
from packages.shared.models.jobs import ingest_batches


def path_key(path: str | None) -> str | None:
    if path is None:
        return None
    # Conservative ordinal key: never perform Unicode expansion such as ß -> SS.
    value = "".join(c.upper() if len(c.upper()) == 1 else c for c in path.replace("/", "\\"))
    return sha256(value.encode()).hexdigest()


def router(engine: Engine) -> APIRouter:
    result = APIRouter(
        prefix="/api/v1/ingest",
        tags=["collector-audit"],
        responses={code: {"model": ApiError} for code in (401, 403, 409, 413, 422, 503)},
    )

    @result.post("/audit-events", status_code=202)
    async def ingest(
        batch: AuditBatch,
        request: Request,
        token: Annotated[str, Depends(collector_token)],
    ) -> Receipt:
        digest = sha256(await request.body()).hexdigest()
        return await run_in_threadpool(accept_audit, engine, batch, token, digest)

    return result


def accept_audit(engine: Engine, batch: AuditBatch, token: str, digest: str) -> Receipt:
    with engine.begin() as conn:
        collector = (
            conn.execute(
                select(collectors).where(collectors.c.id == batch.collector_id).with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if (
            collector is None
            or not collector["enabled"]
            or not hmac.compare_digest(collector["token_hash"], token_hash(token))
        ):
            raise HTTPException(401, detail="COLLECTOR_AUTH_REQUIRED")
        if collector["collector_type"] != "AUDIT_WINDOWS":
            raise HTTPException(403, detail="AUDIT_COLLECTOR_REQUIRED")
        source = collector["source_node_id"]
        source_type = conn.scalar(
            select(source_nodes.c.source_type).where(source_nodes.c.id == source).with_for_update()
        )
        if source_type != "FILESERVER":
            raise HTTPException(403, detail="AUDIT_SOURCE_REQUIRED")
        previous = (
            conn.execute(
                select(ingest_batches).where(
                    ingest_batches.c.collector_id == batch.collector_id,
                    ingest_batches.c.batch_id == batch.batch_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if previous:
            if previous["payload_sha256"] != digest:
                raise HTTPException(409, detail="BATCH_ID_CONFLICT")
            return Receipt(duplicate=True)
        hosts = {r.host_id for r in batch.records}
        if len(hosts) != 1:
            raise HTTPException(409, detail="AUDIT_HOST_CONFLICT")
        host = next(iter(hosts))
        old_host = conn.scalar(
            select(audit_streams.c.host_id).where(
                audit_streams.c.collector_id == batch.collector_id
            )
        )
        if old_host is not None and old_host != host:
            raise HTTPException(409, detail="AUDIT_HOST_CONFLICT")
        statement = pg_insert(audit_streams).values(
            collector_id=batch.collector_id, host_id=host, health={}, accepted_at=func.now()
        )
        conn.execute(
            statement.on_conflict_do_update(
                constraint="uq_audit_stream_collector", set_={"accepted_at": func.now()}
            )
        )
        for wire in batch.records:
            try:
                volume_identity = (
                    canonical_volume_identity(wire.volume_id)
                    if wire.volume_id is not None else None
                )
            except ValueError:
                raise HTTPException(403, detail="AUDIT_VOLUME_REQUIRED") from None
            if (
                volume_identity is not None
                and conn.scalar(
                    select(volumes.c.id).where(
                        volumes.c.source_node_id == source,
                        volumes.c.unique_identity == volume_identity,
                    )
                )
                is None
            ):
                raise HTTPException(403, detail="AUDIT_VOLUME_REQUIRED")
            record = wire.event()
            values = dict(
                source_node_id=source,
                audit_collector_id=batch.collector_id,
                host_id=record.host_id,
                generation=record.generation,
                channel=record.channel,
                record_id=record.record_id,
                event_id=record.event_id,
                occurred_at=record.occurred_at,
                volume_id=volume_identity,
                path_key=path_key(record.path),
                sid=record.sid,
                logon_id=str(record.logon_id) if record.logon_id else None,
                payload=record.model_dump(mode="json"),
                digest=record.digest(),
            )
            inserted = conn.scalar(
                pg_insert(audit_evidence)
                .values(**values)
                .on_conflict_do_nothing(constraint="uq_audit_event_identity")
                .returning(audit_evidence.c.id)
            )
            if inserted is None:
                old = (
                    conn.execute(
                        select(audit_evidence.c.id, audit_evidence.c.digest).where(
                            audit_evidence.c.source_node_id == source,
                            audit_evidence.c.host_id == record.host_id,
                            audit_evidence.c.channel == record.channel,
                            audit_evidence.c.generation == record.generation,
                            audit_evidence.c.record_id == record.record_id,
                        )
                    )
                    .mappings()
                    .one()
                )
                if old["digest"] != record.digest():
                    raise HTTPException(409, detail="AUDIT_EVENT_CONFLICT")
                inserted = old["id"]
            if record.event_id == 4624 and record.client_ip is not None:
                try:
                    client_key = normalized_ip(record.client_ip)
                except ValueError:
                    pass  # Keep even malformed native text; it is not a lookup target.
                else:
                    conn.execute(
                        pg_insert(audit_client_ips)
                        .values(
                            audit_evidence_id=inserted,
                            source_node_id=source,
                            client_ip_key=client_key,
                        )
                        .on_conflict_do_nothing(constraint="uq_audit_client_ip_evidence")
                    )
        times = [r.occurred_at for r in batch.records]
        receipt_id = conn.scalar(
            insert(ingest_batches)
            .values(
                collector_id=batch.collector_id,
                batch_id=batch.batch_id,
                kind="audit-events",
                schema_version=1,
                sent_at=batch.sent_at,
                first_event_at=min(times),
                last_event_at=max(times),
                record_count=len(times),
                payload_sha256=digest,
                processed_at=func.now(),
            )
            .returning(ingest_batches.c.id)
        )
        enqueue(
            conn, "audit_correlate", {"receipt_id": str(receipt_id)}, "audit:" + str(receipt_id)
        )
        conn.execute(
            update(collectors)
            .where(collectors.c.id == batch.collector_id)
            .values(last_seen_at=func.now())
        )
    return Receipt(duplicate=False)
