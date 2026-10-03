# AGENTS.md — Storage Console

## Source of truth

Основная спецификация:
- docs/spec/storage-control-plane-v0.1.md

Порядок задач:
- docs/tasks/README.md

Этот репозиторий публичный. Не копировать сюда production IP, реальные identities, SID, ACL dumps, security/event evidence, credentials или приватную топологию.

## Product boundary

Storage Console — Storage Control Plane с двумя равноправными контурами:

1. Storage Operations / Observability.
2. Data / Process Discovery.

Это не только аналитическая панель файлов.

v0.1 = observe / diagnose / recommend. Autonomous remediation запрещён.

## Mandatory architecture rules

- API-first.
- Web UI не читает filesystem напрямую.
- MCP/AI не читает filesystem или PostgreSQL напрямую.
- Collectors push data в API.
- Backend не использует регулярные SSH/WinRM-сеансы как нормальный механизм сбора.
- Metadata-first; содержимое документов не собирается по умолчанию.
- Canonical storage identity не зависит от drive letter.
- Raw counters не становятся incidents без policy-aware correlation.
- Missing/stale data никогда не отображаются как healthy.

## Localization

Русский обязателен.

- default locale: ru-RU
- fallback: en-US
- user-facing React strings только через i18n keys
- machine enums не локализуются в БД/API
- timestamps в БД — timezone-aware UTC
- UI business timezone configurable
- paths, account names, SID/GUID/FileId не переводятся

PR с hardcoded user-facing strings должен падать на тестах.

## Backend target

- Python 3.13
- FastAPI
- Pydantic v2
- SQLAlchemy 2
- Alembic
- PostgreSQL 16+
- pytest
- Ruff
- mypy или pyright

## Frontend target

- React
- TypeScript strict
- Vite
- TanStack Query
- TanStack Table
- react-i18next
- Vitest
- Playwright

## Security

- не коммитить secrets;
- collector auth отдельно от user auth;
- не раскрывать DB/collector credentials;
- production data в публичных fixtures запрещены.

## Quality gates

- tests
- lint
- type checks
- migration validation
- i18n missing-key validation
- Playwright smoke
- SonarQube Quality Gate
- secret scan

## Git workflow

Делать небольшие логические commits. Не расширять scope задачи молча. Незавершённое не помечать как готовое.
