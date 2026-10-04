"""Bind verified provider subjects without merging or re-enabling identities."""

import hmac
import re
from typing import cast
from uuid import UUID

from sqlalchemy import Connection, Engine, delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from packages.shared.auth.configuration import ROLES
from packages.shared.auth.passwords import password_version
from packages.shared.auth.providers import Subject, credentials_valid
from packages.shared.models.security import audit_log, roles, user_roles, users


class BindingRejected(ValueError):
    def __init__(self) -> None:
        super().__init__("AUTH_SUBJECT_REJECTED")


def set_roles(connection: Connection, user_id: UUID, assigned: frozenset[str]) -> None:
    """Caller must hold the user row lock; replacement is inside its transaction."""
    available: dict[str, UUID] = {
        cast(str, row.code): cast(UUID, row.id)
        for row in connection.execute(
            select(roles.c.code, roles.c.id).where(roles.c.code.in_(assigned))
        )
    }
    if not assigned or not assigned <= ROLES or available.keys() != assigned:
        raise BindingRejected()
    current = {
        cast(UUID, role_id)
        for role_id in connection.scalars(
            select(user_roles.c.role_id).where(user_roles.c.user_id == user_id)
        )
    }
    wanted = set(available.values())
    if current == wanted:
        return
    connection.execute(
        delete(user_roles).where(
            user_roles.c.user_id == user_id, user_roles.c.role_id.not_in(wanted)
        )
    )
    for role_id in wanted - current:
        connection.execute(insert(user_roles).values(user_id=user_id, role_id=role_id))
    connection.execute(
        insert(audit_log).values(
            user_id=user_id,
            action="auth.roles_refreshed",
            resource_type="user",
            result="SUCCESS",
            details={"roles": sorted(assigned)},
        )
    )


def bind_subject(engine: Engine, subject: Subject) -> UUID | None:
    if (
        not credentials_valid(subject.username, "x")
        or not subject.roles
        or not subject.roles <= ROLES
    ):
        return None
    try:
        identity = UUID(subject.subject)
    except ValueError:
        return None
    try:
        with engine.begin() as connection:
            if subject.provider == "local":
                user = (
                    connection.execute(
                        select(users).where(users.c.id == identity).with_for_update()
                    )
                    .mappings()
                    .one_or_none()
                )
                if (
                    user is None
                    or user["auth_provider"] != "local"
                    or not user["enabled"]
                    or user["username"] != subject.username.lower()
                    or not user["password_hash"]
                    or subject.roles != frozenset({"storage_admin"})
                    or subject.credential_tag is None
                    or re.fullmatch(r"[0-9a-f]{64}", subject.credential_tag) is None
                    or not hmac.compare_digest(
                        subject.credential_tag, password_version(user["password_hash"])
                    )
                ):
                    return None
                assigned = frozenset(
                    connection.scalars(
                        select(roles.c.code)
                        .join(user_roles, user_roles.c.role_id == roles.c.id)
                        .where(user_roles.c.user_id == identity)
                    )
                )
                return identity if assigned == subject.roles else None
            if subject.provider != "ldap" or subject.credential_tag is not None:
                return None
            canonical = str(identity)
            # All unique conflicts fail closed; never attach to a username alone.
            connection.execute(
                pg_insert(users)
                .values(
                    username=subject.username.lower(),
                    auth_provider="ldap",
                    provider_subject=canonical,
                )
                .on_conflict_do_nothing()
            )
            user = (
                connection.execute(
                    select(users)
                    .where(users.c.auth_provider == "ldap", users.c.provider_subject == canonical)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if user is None or not user["enabled"]:
                return None
            user_id = cast(UUID, user["id"])
            connection.execute(
                update(users).where(users.c.id == user_id).values(username=subject.username.lower())
            )
            set_roles(connection, user_id, subject.roles)
            return user_id
    except (IntegrityError, BindingRejected):
        return None
