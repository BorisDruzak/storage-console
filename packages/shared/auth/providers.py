from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import Engine, select

from packages.shared.models.security import roles, user_roles, users

from .passwords import verify_password


@dataclass(frozen=True)
class Subject:
    provider: str
    subject: str
    username: str
    roles: frozenset[str]


class AuthProvider(Protocol):
    def authenticate(self, username: str, password: str) -> Subject | None: ...


class ProviderUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("AUTH_PROVIDER_UNAVAILABLE")


def credentials_valid(username: str, password: str) -> bool:
    try:
        return (
            1 <= len(username) <= 64
            and len(username.encode("utf-8")) <= 255
            and username.isprintable()
            and username.strip() == username
            and bool(password)
            and len(password.encode("utf-8")) <= 1024
            and "\x00" not in password
        )
    except UnicodeError:
        return False


class LocalProvider:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def authenticate(self, username: str, password: str) -> Subject | None:
        if not credentials_valid(username, password):
            return None
        with self.engine.connect() as connection:
            user = (
                connection.execute(
                    select(users).where(
                        users.c.username == username.lower(),
                        users.c.auth_provider == "local",
                        users.c.enabled.is_(True),
                    )
                )
                .mappings()
                .one_or_none()
            )
            if user is None:
                return None
            assigned = frozenset(
                connection.scalars(
                    select(roles.c.code)
                    .join(user_roles, user_roles.c.role_id == roles.c.id)
                    .where(user_roles.c.user_id == user["id"])
                )
            )
        if assigned != frozenset({"storage_admin"}) or not user["password_hash"]:
            return None
        if not verify_password(user["password_hash"], password):
            return None
        return Subject("local", str(user["id"]), user["username"], assigned)
