import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request

from apps.api.body_limit import IngestBodyLimit
from apps.api.ingest import router as ingest_router
from apps.api.read.routes import router as read_router
from apps.api.user_auth.dependencies import UserAuth
from apps.api.user_auth.routes import router as auth_router
from apps.api.user_auth.transport import AuthTransport
from packages.shared.database import make_engine
from packages.shared.logging import configure_logging
from packages.shared.observability import configure_sentry
from packages.shared.settings import Settings

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    *,
    user_auth: UserAuth | None = None,
) -> FastAPI:
    # Uvicorn configures its handlers before importing this factory.
    configure_logging()
    config = settings or Settings()
    database = engine if engine is not None else make_engine(config.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        configure_sentry(config)
        logger.info("runtime", extra={"event": "api_started"})
        yield
        database.dispose()

    application = FastAPI(title="Storage Console API", version="0.1.0", lifespan=lifespan)
    application.state.user_auth = user_auth
    application.include_router(auth_router())
    application.include_router(ingest_router(database))
    application.include_router(read_router(database))
    application.add_middleware(IngestBodyLimit, max_bytes=config.max_ingest_bytes)
    application.add_middleware(AuthTransport)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, __: RequestValidationError) -> JSONResponse:
        # Default validation errors echo input/ctx, potentially including forbidden content.
        return JSONResponse({"detail": "INVALID_REQUEST"}, status_code=422)

    @application.exception_handler(SQLAlchemyError)
    async def read_unavailable(_: Request, __: SQLAlchemyError) -> JSONResponse:
        logger.warning("runtime", extra={"event": "database_unavailable"})
        return JSONResponse({"detail": "READ_UNAVAILABLE"}, status_code=503)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/ready", responses={503: {"description": "Database unavailable"}})
    def readiness() -> JSONResponse:
        try:
            with database.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            logger.warning("runtime", extra={"event": "database_unavailable"})
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    return application


app = create_app()
