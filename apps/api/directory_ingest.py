"""Authorized append-only directory pages; partial enumeration never replaces history."""

import hmac
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import Connection, Engine, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from apps.api.auth import collector_token, token_hash
from apps.api.ingest import ApiError, Receipt
from packages.contracts.directory import (
    ClientNameObservation,
    DirectoryPage,
    DirectoryScope,
    normalized_ip,
)
from packages.shared.models.core import collectors, source_nodes
from packages.shared.models.directory import (
    audit_client_ips,
    client_name_observations,
    directory_pages,
    directory_snapshots,
    directory_users,
)
from packages.shared.models.jobs import ingest_batches


def authorize(conn: Connection, collector_id: UUID, token: str, scope: DirectoryScope) -> UUID:
    row = (
        conn.execute(select(collectors).where(collectors.c.id == collector_id).with_for_update())
        .mappings()
        .one_or_none()
    )
    if (
        row is None
        or not row["enabled"]
        or not hmac.compare_digest(row["token_hash"], token_hash(token))
    ):
        raise HTTPException(401, detail="COLLECTOR_AUTH_REQUIRED")
    if row["collector_type"] != "AUDIT_WINDOWS" or row["directory_scope"] != scope.model_dump():
        raise HTTPException(403, detail="DIRECTORY_CAPABILITY_REQUIRED")
    source = cast(UUID, row["source_node_id"])
    if (
        conn.scalar(
            select(source_nodes.c.source_type).where(source_nodes.c.id == source).with_for_update()
        )
        != "FILESERVER"
    ):
        raise HTTPException(403, detail="DIRECTORY_SOURCE_REQUIRED")
    return source


def replay(conn: Connection, collector_id: UUID, batch_id: str, digest: str, kind: str) -> bool:
    prior = (
        conn.execute(
            select(ingest_batches).where(
                ingest_batches.c.collector_id == collector_id,
                ingest_batches.c.batch_id == batch_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if prior is None:
        return False
    if prior["payload_sha256"] != digest or prior["kind"] != kind:
        raise HTTPException(409, detail="BATCH_ID_CONFLICT")
    return True


def receipt(conn: Connection, page: DirectoryPage, digest: str) -> UUID:
    return cast(
        UUID,
        conn.scalar(
            insert(ingest_batches)
            .values(
                collector_id=page.collector_id,
                batch_id=page.batch_id,
                schema_version=1,
                kind="directory",
                payload_sha256=digest,
                record_count=len(page.records),
                sent_at=page.sent_at,
                first_event_at=page.observed_at,
                last_event_at=page.observed_at,
                processed_at=func.now(),
            )
            .returning(ingest_batches.c.id)
        ),
    )


def accept_directory(
    engine: Engine, page: DirectoryPage, token: str, digest: str, payload_bytes: int
) -> Receipt:
    try:
        with engine.begin() as conn:
            source = authorize(conn, page.collector_id, token, page.scope)
            if replay(conn, page.collector_id, page.batch_id, digest, "directory"):
                return Receipt(duplicate=True)
            now = cast(datetime, conn.scalar(select(func.clock_timestamp())))
            if page.observed_at > now + timedelta(seconds=5) or page.sent_at > now + timedelta(
                seconds=5
            ):
                raise HTTPException(422, detail="DIRECTORY_TIME_INVALID")
            old = (
                conn.execute(
                    select(directory_snapshots)
                    .where(
                        directory_snapshots.c.id == page.snapshot_id,
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            count, size = len(page.records), payload_bytes
            if old:
                if old["source_node_id"] != source or old["collector_id"] != page.collector_id:
                    raise HTTPException(403, detail="DIRECTORY_SOURCE_REQUIRED")
                if (
                    old["observed_at"] != page.observed_at
                    or old["dns_domain"] != page.scope.dns_domain
                    or old["domain_sid"] != page.scope.domain_sid
                    or old["state"] != "COLLECTING"
                    or old["next_page"] != page.page_index
                ):
                    raise HTTPException(409, detail="DIRECTORY_PAGE_CONFLICT")
                count += old["record_count"]
                size += old["payload_bytes"]
            elif page.page_index != 0:
                raise HTTPException(409, detail="DIRECTORY_PAGE_CONFLICT")
            if count > 100000 or not 0 < size <= 32 * 1024**2:
                raise HTTPException(409, detail="DIRECTORY_LIMIT")
            if page.finished and count != page.total_records:
                raise HTTPException(409, detail="DIRECTORY_COUNT_CONFLICT")
            state = "COMPLETE" if page.complete else "ERROR" if page.finished else "COLLECTING"
            values = dict(
                state=state,
                record_count=count,
                payload_bytes=size,
                next_page=page.page_index + 1,
                error_code=page.error_code,
            )
            if old:
                conn.execute(
                    update(directory_snapshots)
                    .where(directory_snapshots.c.id == page.snapshot_id)
                    .values(**values)
                )
            else:
                conn.execute(
                    insert(directory_snapshots).values(
                        id=page.snapshot_id,
                        source_node_id=source,
                        collector_id=page.collector_id,
                        dns_domain=page.scope.dns_domain,
                        domain_sid=page.scope.domain_sid,
                        observed_at=page.observed_at,
                        **values,
                    )
                )
            for record in page.records:
                conn.execute(
                    insert(directory_users).values(
                        snapshot_id=page.snapshot_id,
                        sid=record.sid,
                        object_guid=record.object_guid,
                        payload=record.model_dump(mode="json"),
                    )
                )
            identity = receipt(conn, page, digest)
            conn.execute(
                insert(directory_pages).values(
                    snapshot_id=page.snapshot_id,
                    receipt_id=identity,
                    page_index=page.page_index,
                    record_count=len(page.records),
                    payload_sha256=digest,
                )
            )
            conn.execute(
                update(collectors)
                .where(collectors.c.id == page.collector_id)
                .values(last_seen_at=func.now())
            )
        return Receipt(duplicate=False)
    except IntegrityError:
        raise HTTPException(409, detail="DIRECTORY_IDENTITY_CONFLICT") from None


def accept_client_name(
    engine: Engine, observation: ClientNameObservation, token: str, digest: str
) -> Receipt:
    with engine.begin() as conn:
        source = authorize(conn, observation.collector_id, token, observation.scope)
        if replay(conn, observation.collector_id, observation.batch_id, digest, "client-names"):
            return Receipt(duplicate=True)
        now = cast(datetime, conn.scalar(select(func.clock_timestamp())))
        if observation.observed_at > now + timedelta(
            seconds=5
        ) or observation.sent_at > now + timedelta(seconds=5):
            raise HTTPException(422, detail="DIRECTORY_TIME_INVALID")
        key = normalized_ip(observation.client_ip)
        witnessed = conn.scalar(
            select(audit_client_ips.c.audit_evidence_id)
            .where(
                audit_client_ips.c.source_node_id == source,
                audit_client_ips.c.client_ip_key == key,
            )
            .limit(1)
        )
        if witnessed is None:
            raise HTTPException(403, detail="DIRECTORY_CLIENT_WITNESS_REQUIRED")
        identity = conn.scalar(
            insert(ingest_batches)
            .values(
                collector_id=observation.collector_id,
                batch_id=observation.batch_id,
                schema_version=1,
                kind="client-names",
                payload_sha256=digest,
                record_count=1,
                sent_at=observation.sent_at,
                first_event_at=observation.observed_at,
                last_event_at=observation.observed_at,
                processed_at=func.now(),
            )
            .returning(ingest_batches.c.id)
        )
        conn.execute(
            insert(client_name_observations).values(
                source_node_id=source,
                collector_id=observation.collector_id,
                receipt_id=identity,
                dns_domain=observation.scope.dns_domain,
                domain_sid=observation.scope.domain_sid,
                client_ip_key=key,
                observed_at=observation.observed_at,
                expires_at=observation.expires_at,
                payload=observation.model_dump(mode="json"),
            )
        )
        conn.execute(
            update(collectors)
            .where(collectors.c.id == observation.collector_id)
            .values(last_seen_at=func.now())
        )
    return Receipt(duplicate=False)


def router(engine: Engine) -> APIRouter:
    result = APIRouter(
        prefix="/api/v1/ingest",
        tags=["collector-directory"],
        responses={code: {"model": ApiError} for code in (401, 403, 409, 413, 422, 503)},
    )

    @result.post("/directory", status_code=202)
    async def directory(
        page: DirectoryPage, request: Request, token: Annotated[str, Depends(collector_token)]
    ) -> Receipt:
        body = await request.body()
        return await run_in_threadpool(
            accept_directory, engine, page, token, sha256(body).hexdigest(), len(body)
        )

    @result.post("/client-names", status_code=202)
    async def client_name(
        observation: ClientNameObservation,
        request: Request,
        token: Annotated[str, Depends(collector_token)],
    ) -> Receipt:
        return await run_in_threadpool(
            accept_client_name, engine, observation, token, sha256(await request.body()).hexdigest()
        )

    return result
