import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import Connection, Engine, RowMapping, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from packages.shared.auth.configuration import ROLES
from packages.shared.auth.passwords import password_version
from packages.shared.auth.retention import GLOBAL_LOGIN_KEY, lock_rate_rows
from packages.shared.models.security import (
    audit_log,
    login_rate_buckets,
    roles,
    user_roles,
    user_sessions,
    users,
)

_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
_PERMISSIONS = {
    "read": ROLES,
    "manage_sources": frozenset({"storage_admin"}),
    "manage_policy": frozenset({"storage_admin"}),
    "run_diagnostics": frozenset({"storage_admin", "storage_operator"}),
}


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _valid_token(token: str) -> bool:
    return _TOKEN.fullmatch(token) is not None


@dataclass(frozen=True)
class Actor:
    id: UUID
    username: str
    roles: frozenset[str]

    def can(self, permission: str) -> bool:
        return (
            bool(self.roles)
            and self.roles <= ROLES
            and bool(self.roles & _PERMISSIONS.get(permission, frozenset()))
        )


@dataclass(frozen=True)
class IssuedSession:
    actor: Actor
    token: str = field(repr=False)
    csrf: str = field(repr=False)


@dataclass(frozen=True)
class CurrentSession:
    actor: Actor
    csrf_hash: str = field(repr=False)

    def csrf_matches(self, cookie: str, header: str) -> bool:
        return (
            _valid_token(cookie)
            and _valid_token(header)
            and hmac.compare_digest(cookie, header)
            and hmac.compare_digest(token_hash(cookie), self.csrf_hash)
        )


def _time(connection: Connection) -> datetime:
    # Sample after row locks; transaction-start time may be stale after waiting.
    return cast(datetime, connection.scalar(select(func.clock_timestamp())))


def _actor(connection: Connection, user: RowMapping) -> Actor | None:
    assigned = frozenset(
        connection.scalars(
            select(roles.c.code)
            .join(user_roles, user_roles.c.role_id == roles.c.id)
            .where(user_roles.c.user_id == user["id"])
        )
    )
    if not user["enabled"] or not assigned or not assigned <= ROLES:
        return None
    return Actor(cast(UUID, user["id"]), cast(str, user["username"]), assigned)


def _audit(connection: Connection, action: str, result: str, user: UUID | None = None) -> None:
    connection.execute(
        insert(audit_log).values(
            user_id=user, action=action, resource_type="user_session", result=result, details={}
        )
    )


def _locked_session(connection: Connection, digest: str) -> tuple[RowMapping, RowMapping] | None:
    user_id = connection.scalar(
        select(user_sessions.c.user_id).where(user_sessions.c.token_hash == digest)
    )
    if user_id is None:
        return None
    # All session writes use user→session lock order, including password rotation.
    user = (
        connection.execute(select(users).where(users.c.id == user_id).with_for_update())
        .mappings()
        .one_or_none()
    )
    session = (
        connection.execute(
            select(user_sessions).where(user_sessions.c.token_hash == digest).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    return (user, session) if user is not None and session is not None else None


def _ticket(connection: Connection, key: str, maximum: int) -> tuple[bool, bool]:
    connection.execute(
        pg_insert(login_rate_buckets)
        .values(key=key, window_started_at=func.clock_timestamp(), attempts=0)
        .on_conflict_do_nothing(index_elements=["key"])
    )
    row = connection.execute(
        select(login_rate_buckets).where(login_rate_buckets.c.key == key).with_for_update()
    ).one()
    now = _time(connection)
    started, count = row.window_started_at, row.attempts
    if now - started >= timedelta(minutes=10):
        started, count = now, 0
    first_denial = count == maximum
    count = min(count + 1, maximum + 1)
    connection.execute(
        update(login_rate_buckets)
        .where(login_rate_buckets.c.key == key)
        .values(window_started_at=started, attempts=count)
    )
    return count <= maximum, first_denial


class SessionStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def login_failed(self) -> None:
        # Caller must first consume a login ticket; global budget bounds audit volume.
        with self.engine.begin() as connection:
            _audit(connection, "auth.failure", "DENIED")

    def audit_denial(self, action: str, user: UUID | None = None) -> None:
        if action not in {"auth.origin_denied", "auth.csrf_denied", "auth.permission_denied"}:
            raise ValueError("AUTH_AUDIT_ACTION_INVALID")
        key = hashlib.sha256(("denial:" + action + ":" + str(user)).encode()).hexdigest()
        with self.engine.begin() as connection:
            lock_rate_rows(connection)
            _, first = _ticket(connection, key, 0)
            if first:
                _audit(connection, action, "DENIED", user)

    def issue(self, user_id: UUID, *, credential_tag: str | None = None) -> IssuedSession | None:
        with self.engine.begin() as connection:
            user = (
                connection.execute(select(users).where(users.c.id == user_id).with_for_update())
                .mappings()
                .one_or_none()
            )
            actor = _actor(connection, user) if user is not None else None
            if actor is None:
                return None
            if (
                user is not None
                and user["auth_provider"] == "local"
                and user["password_hash"]
                and credential_tag is None
            ):
                return None
            if credential_tag is not None and (
                re.fullmatch(r"[0-9a-f]{64}", credential_tag) is None
                or user is None
                or user["auth_provider"] != "local"
                or not user["password_hash"]
                or not hmac.compare_digest(credential_tag, password_version(user["password_hash"]))
            ):
                return None
            now = _time(connection)
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            connection.execute(
                insert(user_sessions).values(
                    user_id=user_id,
                    token_hash=token_hash(token),
                    csrf_hash=token_hash(csrf),
                    created_at=now,
                    last_used_at=now,
                    expires_at=now + timedelta(hours=8),
                )
            )
            _audit(connection, "auth.login", "SUCCESS", user_id)
        return IssuedSession(actor, token, csrf)

    def resolve(self, token: str) -> CurrentSession | None:
        if not _valid_token(token):
            return None
        with self.engine.begin() as connection:
            locked = _locked_session(connection, token_hash(token))
            if locked is None:
                return None
            user, session = locked
            now = _time(connection)
            if (
                session["revoked_at"] is not None
                or session["expires_at"] <= now
                or now - session["last_used_at"] >= timedelta(minutes=30)
            ):
                return None
            actor = _actor(connection, user)
            if actor is None:
                return None
            connection.execute(
                update(user_sessions)
                .where(user_sessions.c.id == session["id"])
                .values(last_used_at=now)
            )
            return CurrentSession(actor, cast(str, session["csrf_hash"]))

    def revoke(self, token: str, *, rotation: bool = False) -> bool:
        if not _valid_token(token):
            return False
        with self.engine.begin() as connection:
            locked = _locked_session(connection, token_hash(token))
            if locked is None or locked[1]["revoked_at"] is not None:
                return False
            user, session = locked
            connection.execute(
                update(user_sessions)
                .where(user_sessions.c.id == session["id"])
                .values(revoked_at=_time(connection))
            )
            _audit(
                connection,
                "auth.session_rotated" if rotation else "auth.logout",
                "SUCCESS",
                cast(UUID, user["id"]),
            )
        return True

    def consume_ticket(self, provider: str, username: str) -> bool:
        try:
            if (
                provider not in {"local", "ldap"}
                or not 1 <= len(username) <= 64
                or len(username.encode("utf-8")) > 255
                or not username.isprintable()
            ):
                return False
        except UnicodeError:
            return False
        account = hashlib.sha256(
            ("login:account:" + provider + ":" + username.lower()).encode()
        ).hexdigest()
        global_key = GLOBAL_LOGIN_KEY
        with self.engine.begin() as connection:
            # Always global→account: serialize shared budget without deadlocks.
            allowed, first_denial = _ticket(connection, global_key, 100)
            if allowed:
                allowed, first_denial = _ticket(connection, account, 5)
            if first_denial:
                _audit(connection, "auth.rate_denied", "DENIED")
            return allowed
