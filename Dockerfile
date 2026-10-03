FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt -c requirements.lock
COPY apps/api apps/api
COPY apps/worker apps/worker
COPY packages packages
COPY migrations migrations
COPY alembic.ini ./
RUN useradd --uid 10001 --create-home app
ARG APP_RELEASE=0.1.0
LABEL org.opencontainers.image.revision=$APP_RELEASE
USER app
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

FROM runtime AS test
USER root
RUN pip install --no-cache-dir -r requirements.lock
COPY pyproject.toml ./
COPY tests/backend tests/backend
USER app
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
