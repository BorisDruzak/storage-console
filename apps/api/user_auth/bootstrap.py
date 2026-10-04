"""Operator-only interactive local administrator bootstrap and rotation."""

import argparse
import os
import sys
from getpass import getpass
from typing import NoReturn, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from argon2.exceptions import HashingError
from sqlalchemy import Engine, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from packages.shared.auth.passwords import hash_password
from packages.shared.auth.providers import credentials_valid
from packages.shared.database import make_engine
from packages.shared.models.security import audit_log, roles, user_sessions, users
from packages.shared.settings import Settings

from .identities import set_roles


class BootstrapError(ValueError):
    def __init__(self) -> None:
        super().__init__("AUTH_BOOTSTRAP_FAILED")


def bootstrap_admin(engine: Engine, username: str, password: str) -> UUID:
    username = username.lower()
    if not credentials_valid(username, password):
        raise BootstrapError()
    encoded = hash_password(password)
    with engine.begin() as connection:
        created = connection.scalar(
            pg_insert(users)
            .values(username=username, auth_provider="local", password_hash=encoded)
            .on_conflict_do_nothing()
            .returning(users.c.id)
        )
        user = (
            connection.execute(select(users).where(users.c.username == username).with_for_update())
            .mappings()
            .one_or_none()
        )
        if user is None or user["auth_provider"] != "local":
            raise BootstrapError()
        user_id = cast(UUID, user["id"])
        connection.execute(
            pg_insert(roles)
            .values(
                id=uuid5(NAMESPACE_URL, "urn:storage-console:role:storage_admin"),
                code="storage_admin",
            )
            .on_conflict_do_nothing(index_elements=["code"])
        )
        connection.execute(update(users).where(users.c.id == user_id).values(password_hash=encoded))
        set_roles(connection, user_id, frozenset({"storage_admin"}))
        connection.execute(
            update(user_sessions)
            .where(user_sessions.c.user_id == user_id, user_sessions.c.revoked_at.is_(None))
            .values(revoked_at=func.clock_timestamp())
        )
        connection.execute(
            insert(audit_log).values(
                user_id=user_id,
                action="auth.bootstrap_create" if created is not None else "auth.bootstrap_rotate",
                resource_type="user",
                result="SUCCESS",
                details={},
            )
        )
    return user_id


def _interactive_operator() -> bool:
    return os.name == "posix" and os.geteuid() in {0, 10001} and sys.stdin.isatty()


class _PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse's default error echoes unknown arguments, possibly passwords.
        print("AUTH_BOOTSTRAP_ARGUMENTS_INVALID", file=sys.stderr)
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = _PrivateArgumentParser(
        description="Bootstrap or rotate an explicit local storage_admin"
    )
    parser.add_argument("--username", required=True)
    args = parser.parse_args(argv)
    if not _interactive_operator():
        print("AUTH_BOOTSTRAP_INTERACTIVE_OPERATOR_REQUIRED", file=sys.stderr)
        return 1
    engine = None
    try:
        password = getpass("New password (minimum 16 characters): ")
        confirmation = getpass("Confirm password: ")
        if password != confirmation:
            raise BootstrapError()
        # Policy checks before opening the database; never accept argv/env passwords.
        if not credentials_valid(args.username, password):
            raise BootstrapError()
        hash_password(password)
        engine = make_engine(Settings().database_url)
        bootstrap_admin(engine, args.username, password)
    except (ValueError, SQLAlchemyError, HashingError, OSError, EOFError, KeyboardInterrupt):
        print("AUTH_BOOTSTRAP_FAILED", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print("AUTH_BOOTSTRAPPED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
