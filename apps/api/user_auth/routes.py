from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import SQLAlchemyError

from apps.api.ingest import ApiError
from apps.api.user_auth.dependencies import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    cookie,
    denied,
    require_actor,
    require_auth,
    require_csrf,
    require_origin,
)
from apps.api.user_auth.sessions import Actor, CurrentSession
from packages.contracts.auth import LoginRequest, UserResponse


def user_response(actor: Actor) -> UserResponse:
    return UserResponse.model_validate(
        {"id": actor.id, "username": actor.username, "roles": sorted(actor.roles)}
    )


def router() -> APIRouter:
    routes = APIRouter(prefix="/api/v1/auth", tags=["authentication"])

    @routes.post(
        "/login",
        response_model=UserResponse,
        responses={code: {"model": ApiError} for code in (401, 403, 413, 415, 422, 429, 503)},
    )
    def login(body: LoginRequest, request: Request, response: Response) -> UserResponse:
        require_origin(request)
        auth = require_auth(request)
        issued = auth.login(body.provider, body.username, body.password.get_secret_value())
        previous = cookie(request, SESSION_COOKIE)
        try:
            if previous:
                auth.store.revoke(previous, rotation=True)
        except SQLAlchemyError:
            raise denied(503, "AUTH_UNAVAILABLE") from None
        for name, value, http_only in (
            (SESSION_COOKIE, issued.token, True),
            (CSRF_COOKIE, issued.csrf, False),
        ):
            response.set_cookie(
                name,
                value,
                max_age=28800,
                path="/",
                secure=True,
                httponly=http_only,
                samesite="lax",
            )
        return user_response(issued.actor)

    @routes.get(
        "/me",
        response_model=UserResponse,
        responses={code: {"model": ApiError} for code in (401, 503)},
    )
    def me(actor: Annotated[Actor, Depends(require_actor)]) -> UserResponse:
        return user_response(actor)

    @routes.post(
        "/logout",
        status_code=204,
        responses={code: {"model": ApiError} for code in (401, 403, 503)},
    )
    def logout(
        request: Request, _current: Annotated[CurrentSession, Depends(require_csrf)]
    ) -> Response:
        try:
            require_auth(request).store.revoke(cookie(request, SESSION_COOKIE))
        except SQLAlchemyError:
            raise denied(503, "AUTH_UNAVAILABLE") from None
        response = Response(status_code=204)
        for name, http_only in ((SESSION_COOKIE, True), (CSRF_COOKIE, False)):
            response.delete_cookie(name, path="/", secure=True, httponly=http_only, samesite="lax")
        return response

    return routes
