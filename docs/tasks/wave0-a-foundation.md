# Codex Task — Wave 0A: Repository Foundation

## Goal

Создать production-oriented monorepo foundation для Storage Control Plane без live collectors.

## Required

Структура:
- apps/api
- apps/web
- apps/worker
- collectors/windows
- collectors/pve
- collectors/pbs
- packages/contracts
- packages/i18n
- packages/shared
- migrations
- deploy
- tests
- docs

Backend:
- Python 3.13
- FastAPI
- Pydantic v2
- SQLAlchemy 2
- Alembic
- pytest
- Ruff
- mypy или pyright

Frontend:
- React
- TypeScript strict
- Vite
- TanStack Query
- TanStack Table
- react-i18next
- Vitest
- Playwright

Infrastructure:
- PostgreSQL 16+
- Nginx
- Docker Compose
- health checks
- structured JSON logs
- Sentry hooks
- SonarQube config
- .env.example
- Russian README

## Русификация

Default ru-RU, fallback en-US.

Запрещены hardcoded user-facing strings.

Минимальный catalog:
- navigation
- health states
- common actions
- loading
- empty
- error
- auth

## Constraints

Не:
- реализовывать production collectors;
- читать filesystem из backend/web;
- добавлять SSH/WinRM polling;
- добавлять Redis;
- добавлять remediation;
- коммитить production data/secrets.

## Acceptance

1. Fresh clone стартует через Docker Compose.
2. PostgreSQL healthy.
3. API /health healthy.
4. Web показывает русский shell.
5. Worker healthy.
6. Fresh DB мигрируется Alembic.
7. CI green.
8. Missing i18n key test есть.
9. Sentry не ломает startup без DSN.
10. README объясняет observe/diagnose/recommend boundary.
