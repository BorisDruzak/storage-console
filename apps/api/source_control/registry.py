import secrets
from uuid import UUID

from sqlalchemy import Connection, Engine, RowMapping, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from apps.api.auth import token_hash
from apps.api.user_auth.sessions import Actor
from packages.contracts.read import Page
from packages.contracts.sources import (
    CollectorCredential,
    CollectorView,
    CreateCollector,
    CreateSource,
    SetCollectorEnabled,
    SourceRegistration,
)
from packages.shared.models.core import collectors, source_nodes
from packages.shared.models.security import audit_log

_PAIRING = {"FILESERVER": "WINDOWS", "PVE": "PVE", "PBS": "PBS"}
_SOURCE_COLUMNS = tuple(source_nodes.c[name] for name in SourceRegistration.model_fields)
_COLLECTOR_COLUMNS = tuple(collectors.c[name] for name in CollectorView.model_fields)


class RegistryError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status, self.detail = status, detail
        super().__init__(detail)


def _audit(conn: Connection, actor: Actor, action: str, resource: str, identity: UUID) -> None:
    conn.execute(
        insert(audit_log).values(
            user_id=actor.id,
            action=action,
            resource_type=resource,
            resource_identity=str(identity),
            result="SUCCESS",
            details={},
        )
    )


def register_source(engine: Engine, actor: Actor, data: CreateSource) -> SourceRegistration:
    with engine.begin() as conn:
        row = (
            conn.execute(
                pg_insert(source_nodes)
                .values(**data.model_dump())
                .on_conflict_do_nothing(constraint="uq_source_identity")
                .returning(*_SOURCE_COLUMNS)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise RegistryError(409, "SOURCE_IDENTITY_CONFLICT")
        result = SourceRegistration.model_validate(row)
        _audit(conn, actor, "source.register", "source", result.id)
    return result


def enroll_collector(
    engine: Engine, actor: Actor, source_id: UUID, data: CreateCollector
) -> CollectorCredential:
    secret = secrets.token_urlsafe(32)
    with engine.begin() as conn:
        source_type = conn.scalar(
            select(source_nodes.c.source_type)
            .where(source_nodes.c.id == source_id)
            .with_for_update()
        )
        if source_type is None:
            raise RegistryError(404, "SOURCE_NOT_FOUND")
        if _PAIRING.get(source_type) != data.collector_type:
            raise RegistryError(409, "COLLECTOR_TYPE_CONFLICT")
        row = (
            conn.execute(
                insert(collectors)
                .values(
                    source_node_id=source_id,
                    collector_type=data.collector_type,
                    token_hash=token_hash(secret),
                )
                .returning(*_COLLECTOR_COLUMNS)
            )
            .mappings()
            .one()
        )
        result = CollectorCredential.model_validate(dict(row, token=secret))
        _audit(conn, actor, "collector.enroll", "collector", result.id)
    return result


def _locked_collector(conn: Connection, identity: UUID) -> RowMapping:
    row = (
        conn.execute(
            select(*_COLLECTOR_COLUMNS).where(collectors.c.id == identity).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise RegistryError(404, "COLLECTOR_NOT_FOUND")
    return row


def rotate_collector(engine: Engine, actor: Actor, identity: UUID) -> CollectorCredential:
    secret = secrets.token_urlsafe(32)
    with engine.begin() as conn:
        row = _locked_collector(conn, identity)
        conn.execute(
            update(collectors)
            .where(collectors.c.id == identity)
            .values(token_hash=token_hash(secret))
        )
        result = CollectorCredential.model_validate(dict(row, token=secret))
        _audit(conn, actor, "collector.rotate", "collector", identity)
    return result


def set_collector_enabled(
    engine: Engine, actor: Actor, identity: UUID, data: SetCollectorEnabled
) -> CollectorView:
    with engine.begin() as conn:
        row = _locked_collector(conn, identity)
        if row["enabled"] != data.enabled:
            conn.execute(
                update(collectors).where(collectors.c.id == identity).values(enabled=data.enabled)
            )
            _audit(
                conn,
                actor,
                "collector.enable" if data.enabled else "collector.disable",
                "collector",
                identity,
            )
        result = CollectorView.model_validate(dict(row, enabled=data.enabled))
    return result


def list_collectors(
    engine: Engine, source_id: UUID, limit: int, offset: int
) -> Page[CollectorView]:
    if (
        type(limit) is not int
        or type(offset) is not int
        or not 1 <= limit <= 100
        or not 0 <= offset <= 1000000
    ):
        raise RegistryError(422, "INVALID_REQUEST")
    with (
        engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn,
        conn.begin(),
    ):
        if conn.scalar(select(source_nodes.c.id).where(source_nodes.c.id == source_id)) is None:
            raise RegistryError(404, "SOURCE_NOT_FOUND")
        where = collectors.c.source_node_id == source_id
        total = conn.scalar(select(func.count()).select_from(collectors).where(where))
        rows = conn.execute(
            select(*_COLLECTOR_COLUMNS)
            .where(where)
            .order_by(collectors.c.created_at, collectors.c.id)
            .limit(limit)
            .offset(offset)
        ).mappings()
        return Page[CollectorView](
            items=[CollectorView.model_validate(row) for row in rows],
            total=total or 0,
            limit=limit,
            offset=offset,
        )
