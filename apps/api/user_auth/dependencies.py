from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyCookie
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from apps.api.user_auth.identities import BindingRejected, bind_subject
from apps.api.user_auth.sessions import Actor, CurrentSession, IssuedSession, SessionStore
from packages.shared.auth.configuration import AuthConfig
from packages.shared.auth.ldap_provider import DirectoryProvider
from packages.shared.auth.providers import AuthProvider, LocalProvider, ProviderUnavailable

SESSION_COOKIE = "__Host-storage_session"
CSRF_COOKIE = "__Host-storage_csrf"
_SESSION_SECURITY = APIKeyCookie(name=SESSION_COOKIE, scheme_name="UserSession", auto_error=False)


def denied(status: int, detail: str) -> HTTPException:
    return HTTPException(status, detail, headers={"Cache-Control": "no-store"})


class UserAuth:
    def __init__(self, engine: Engine, config: AuthConfig) -> None:
        self.engine = engine
        self.config = config
        self.store = SessionStore(engine)
        self.providers: dict[str, AuthProvider] = {}
        if config.local_enabled:
            self.providers["local"] = LocalProvider(engine)
        if config.ldap is not None:
            self.providers["ldap"] = DirectoryProvider(config.ldap)

    def login(self, provider: str, username: str, password: str) -> IssuedSession:
        try:
            if not self.store.consume_ticket(provider, username):
                raise denied(429, "AUTH_RATE_LIMITED")
            selected = self.providers.get(provider)
            subject = selected.authenticate(username, password) if selected is not None else None
            if subject is None:
                self.store.login_failed()
                raise denied(401, "AUTH_FAILED")
            try:
                user = bind_subject(self.engine, subject)
            except BindingRejected:
                user = None
            issued = (
                self.store.issue(user, credential_tag=subject.credential_tag)
                if user is not None
                else None
            )
            if issued is None:
                self.store.login_failed()
                raise denied(401, "AUTH_FAILED")
            return issued
        except ProviderUnavailable:
            try:
                self.store.login_failed()
            except SQLAlchemyError:
                pass  # Database outage cannot be audited; never retry or leak its error.
            raise denied(503, "AUTH_UNAVAILABLE") from None
        except SQLAlchemyError:
            raise denied(503, "AUTH_UNAVAILABLE") from None


def require_auth(request: Request) -> UserAuth:
    auth = getattr(request.app.state, "user_auth", None)
    if not isinstance(auth, UserAuth):
        raise denied(503, "AUTH_UNAVAILABLE")
    return auth


def single_header(request: Request, name: str) -> str | None:
    values = request.headers.getlist(name)
    return values[0] if len(values) == 1 else None


def cookie(request: Request, name: str) -> str:
    # Reject ambiguous duplicate cookies instead of choosing a proxy/parser winner.
    values = [
        part.strip().split("=", 1)[1]
        for header in request.headers.getlist("cookie")
        for part in header.split(";")
        if "=" in part and part.strip().split("=", 1)[0] == name
    ]
    return values[0] if len(values) == 1 else ""


def require_origin(request: Request) -> None:
    if single_header(request, "origin") != require_auth(request).config.origin:
        audit_denial(request, "auth.origin_denied")
        raise denied(403, "AUTH_ORIGIN_DENIED")


def audit_denial(request: Request, action: str, user: UUID | None = None) -> None:
    try:
        require_auth(request).store.audit_denial(action, user)
    except SQLAlchemyError:
        raise denied(503, "AUTH_UNAVAILABLE") from None


def require_session(
    request: Request, _token: Annotated[str | None, Security(_SESSION_SECURITY)]
) -> CurrentSession:
    try:
        current = require_auth(request).store.resolve(cookie(request, SESSION_COOKIE))
    except SQLAlchemyError:
        raise denied(503, "AUTH_UNAVAILABLE") from None
    if current is None:
        raise denied(401, "AUTH_REQUIRED")
    return current


def require_actor(current: Annotated[CurrentSession, Depends(require_session)]) -> Actor:
    return current.actor


def require_permission(permission: str) -> Callable[..., Actor]:
    def check(request: Request, actor: Annotated[Actor, Depends(require_actor)]) -> Actor:
        if not actor.can(permission):
            audit_denial(request, "auth.permission_denied", actor.id)
            raise denied(403, "AUTH_FORBIDDEN")
        return actor

    return check


def require_csrf(
    request: Request, current: Annotated[CurrentSession, Depends(require_session)]
) -> CurrentSession:
    require_origin(request)
    if not current.csrf_matches(
        cookie(request, CSRF_COOKIE), single_header(request, "x-csrf-token") or ""
    ):
        audit_denial(request, "auth.csrf_denied", current.actor.id)
        raise denied(403, "AUTH_CSRF_DENIED")
    return current
