from typing import cast
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from packages.contracts.acl import ACLRecord
from packages.shared.models.authorization import acl_aces, acl_snapshots, principals
from packages.shared.models.core import filesystem_objects

from .core import IngestConflict, volume_id


def principal(connection: Connection, source: UUID, identity: str | None) -> UUID | None:
    if identity is None:
        return None
    namespace = "source:" + str(source)
    existing = connection.scalar(
        select(principals.c.id).where(
            principals.c.identity_namespace == namespace,
            principals.c.sid == identity,
        )
    )
    if existing is not None:
        return cast(UUID, existing)
    return cast(
        UUID,
        connection.scalar(
            insert(principals)
            .values(identity_namespace=namespace, sid=identity, principal_type="UNKNOWN")
            .returning(principals.c.id)
        ),
    )


def acl(connection: Connection, source: UUID, record: ACLRecord) -> None:
    target = None
    if record.volume_identity is not None and record.file_id is not None:
        volume = volume_id(connection, source, record.volume_identity)
        target = connection.scalar(
            select(filesystem_objects.c.id).where(
                filesystem_objects.c.volume_id == volume,
                filesystem_objects.c.file_id == record.file_id,
            )
        )
        if target is None:
            raise IngestConflict("UNKNOWN_OBJECT")
    snapshot = connection.scalar(
        insert(acl_snapshots)
        .values(
            source_node_id=source,
            object_id=target,
            scope_identity=record.scope_identity,
            dacl_fingerprint=record.dacl_fingerprint,
            owner_principal_id=principal(connection, source, record.owner_identity),
            inheritance_enabled=record.inheritance_enabled,
            observed_at=record.occurred_at,
        )
        .returning(acl_snapshots.c.id)
    )
    for ordinal, ace in enumerate(record.aces):
        connection.execute(
            insert(acl_aces).values(
                snapshot_id=snapshot,
                ordinal=ordinal,
                principal_id=principal(connection, source, ace.principal_identity),
                **ace.model_dump(exclude={"principal_identity"}),
            )
        )
