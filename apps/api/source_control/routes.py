from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from apps.api.ingest import ApiError
from apps.api.user_auth.dependencies import require_csrf, require_permission
from apps.api.user_auth.sessions import Actor
from packages.contracts.read import Page
from packages.contracts.sources import (
    CollectorCredential,
    CollectorView,
    CreateCollector,
    CreateSource,
    RotateCollector,
    SetCollectorEnabled,
    SourceRegistration,
)

from . import registry

Admin = Annotated[Actor, Depends(require_permission("manage_sources"))]
Reader = Annotated[Actor, Depends(require_permission("read"))]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=1000000)]


def _control[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except registry.RegistryError as error:
        raise HTTPException(
            error.status, error.detail, headers={"Cache-Control": "no-store"}
        ) from None
    except SQLAlchemyError:
        raise HTTPException(
            503, "CONTROL_UNAVAILABLE", headers={"Cache-Control": "no-store"}
        ) from None


def router(engine: Engine) -> APIRouter:
    result = APIRouter(
        prefix="/api/v1",
        tags=["source-management"],
        responses={code: {"model": ApiError} for code in (401, 403, 404, 409, 413, 415, 422, 503)},
    )
    write = [Depends(require_csrf)]

    @result.post("/sources", status_code=201, dependencies=write)
    def register(data: CreateSource, actor: Admin) -> SourceRegistration:
        return _control(lambda: registry.register_source(engine, actor, data))

    @result.post("/sources/{source_id}/collectors", status_code=201, dependencies=write)
    def enroll(source_id: UUID, data: CreateCollector, actor: Admin) -> CollectorCredential:
        return _control(lambda: registry.enroll_collector(engine, actor, source_id, data))

    @result.get("/sources/{source_id}/collectors")
    def list_collectors(
        source_id: UUID, _actor: Reader, limit: Limit = 50, offset: Offset = 0
    ) -> Page[CollectorView]:
        return _control(lambda: registry.list_collectors(engine, source_id, limit, offset))

    @result.post("/collectors/{collector_id}/rotate-token", dependencies=write)
    def rotate(collector_id: UUID, _data: RotateCollector, actor: Admin) -> CollectorCredential:
        return _control(lambda: registry.rotate_collector(engine, actor, collector_id))

    @result.patch("/collectors/{collector_id}", dependencies=write)
    def enable(collector_id: UUID, data: SetCollectorEnabled, actor: Admin) -> CollectorView:
        return _control(lambda: registry.set_collector_enabled(engine, actor, collector_id, data))

    return result
