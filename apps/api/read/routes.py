from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from apps.api.ingest import ApiError
from packages.contracts.read import (
    Counts,
    Domains,
    Freshness,
    Overview,
    Page,
    Share,
    Source,
    Volume,
)
from packages.shared.models.core import (
    filesystem_objects,
    shares,
    source_nodes,
    volume_aliases,
    volumes,
)

from .overview import domain_health
from .sources import database_time, freshness, require_source, snapshot, source, source_data
from .storage import share, volume

Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=1000000)]


def router(engine: Engine) -> APIRouter:
    result = APIRouter(
        prefix="/api/v1",
        tags=["read"],
        responses={code: {"model": ApiError} for code in (404, 422, 503)},
    )

    @result.get("/overview")
    def overview() -> Overview:
        with snapshot(engine) as connection:
            counts = {
                table.name: connection.scalar(select(func.count()).select_from(table)) or 0
                for table in (source_nodes, volumes, shares, filesystem_objects)
            }
            return Overview(
                counts=Counts(
                    sources=counts["source_nodes"],
                    volumes=counts["volumes"],
                    shares=counts["shares"],
                    filesystem_objects=counts["filesystem_objects"],
                ),
                domains=domain_health(connection),
                evaluated_at=database_time(connection),
            )

    @result.get("/health/domains")
    def health_domains() -> Domains:
        with snapshot(engine) as connection:
            return Domains(
                domains=domain_health(connection), evaluated_at=database_time(connection)
            )

    @result.get("/sources")
    def sources(limit: Limit = 50, offset: Offset = 0) -> Page[Source]:
        with snapshot(engine) as connection:
            data = source_data()
            rows = (
                connection.execute(
                    select(data).order_by(data.c.created_at, data.c.id).limit(limit).offset(offset)
                )
                .mappings()
                .all()
            )
            total = connection.scalar(select(func.count()).select_from(source_nodes)) or 0
            return Page[Source](
                items=[source(row) for row in rows], total=total, limit=limit, offset=offset
            )

    @result.get("/sources/{source_id}")
    def source_detail(source_id: UUID) -> Source:
        with snapshot(engine) as connection:
            return source(require_source(connection, source_id))

    @result.get("/sources/{source_id}/freshness")
    def source_freshness(source_id: UUID) -> Freshness:
        with snapshot(engine) as connection:
            return freshness(require_source(connection, source_id))

    @result.get("/volumes")
    def volume_list(
        limit: Limit = 50, offset: Offset = 0, source_id: UUID | None = None
    ) -> Page[Volume]:
        with snapshot(engine) as connection:
            query = select(volumes, source_nodes.c.expected_cadence_seconds).join(source_nodes)
            count = select(func.count()).select_from(volumes)
            if source_id is not None:
                require_source(connection, source_id)
                query = query.where(volumes.c.source_node_id == source_id)
                count = count.where(volumes.c.source_node_id == source_id)
            rows = (
                connection.execute(
                    query.order_by(volumes.c.first_seen_at, volumes.c.id)
                    .limit(limit)
                    .offset(offset)
                )
                .mappings()
                .all()
            )
            now = database_time(connection)
            aliases: dict[UUID, list[str]] = {}
            if rows:
                for volume_id, alias in connection.execute(
                    select(volume_aliases.c.volume_id, volume_aliases.c.alias)
                    .where(
                        volume_aliases.c.volume_id.in_([row["id"] for row in rows]),
                        volume_aliases.c.ended_at.is_(None),
                    )
                    .order_by(volume_aliases.c.volume_id, volume_aliases.c.alias)
                ):
                    aliases.setdefault(volume_id, []).append(alias)
            return Page[Volume](
                items=[volume(row, now, aliases.get(row["id"], [])) for row in rows],
                total=connection.scalar(count) or 0,
                limit=limit,
                offset=offset,
            )

    @result.get("/shares")
    def share_list(
        limit: Limit = 50, offset: Offset = 0, source_id: UUID | None = None
    ) -> Page[Share]:
        with snapshot(engine) as connection:
            query = select(shares, source_nodes.c.expected_cadence_seconds).join(source_nodes)
            count = select(func.count()).select_from(shares)
            if source_id is not None:
                require_source(connection, source_id)
                query = query.where(shares.c.source_node_id == source_id)
                count = count.where(shares.c.source_node_id == source_id)
            rows = (
                connection.execute(
                    query.order_by(shares.c.last_seen_at, shares.c.id).limit(limit).offset(offset)
                )
                .mappings()
                .all()
            )
            now = database_time(connection)
            return Page[Share](
                items=[share(row, now) for row in rows],
                total=connection.scalar(count) or 0,
                limit=limit,
                offset=offset,
            )

    return result
