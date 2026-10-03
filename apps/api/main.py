import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from packages.shared.database import make_engine
from packages.shared.logging import configure_logging
from packages.shared.observability import configure_sentry
from packages.shared.settings import Settings

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    # Uvicorn configures its handlers before importing this factory.
    configure_logging()
    config = settings or Settings()
    database = engine if engine is not None else make_engine(config.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        configure_sentry(config)
        logger.info('runtime', extra={'event': 'api_started'})
        yield
        database.dispose()

    application = FastAPI(title='Storage Console API', version='0.1.0', lifespan=lifespan)

    @application.get('/health')
    def health() -> dict[str, str]:
        return {'status': 'ok'}

    @application.get('/ready', responses={503: {'description': 'Database unavailable'}})
    def readiness() -> JSONResponse:
        try:
            with database.connect() as connection:
                connection.execute(text('SELECT 1'))
        except SQLAlchemyError:
            logger.warning('runtime', extra={'event': 'database_unavailable'})
            return JSONResponse({'status': 'unavailable'}, status_code=503)
        return JSONResponse({'status': 'ok'})

    return application


app = create_app()
