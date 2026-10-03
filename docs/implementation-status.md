# Статус реализации

## Wave 0A — in progress

- [x] Monorepo directories: API, Web, worker, collectors, contracts, i18n, shared, migrations, deploy, tests.
- [x] Backend settings, JSON logs, health/readiness, optional Sentry hooks.
- [x] Worker heartbeat с проверкой свежести; UTC timestamptz migration.
- [x] Русский shell, 12 navigation entries, ru-RU default/en-US fallback, missing-key checks.
- [x] Frontend/backend tests и локальные lint/types/build.
- [x] Compose/Nginx и GitHub Actions definitions.
- [x] Чистый source snapshot + новая БД: PostgreSQL/API/Web/worker healthy; повторный startup сохраняет volume.
- [x] Migration upgrade/check/downgrade/upgrade на disposable PostgreSQL.
- [x] Playwright smoke против собранного stack: 2/2; desktop/mobile screenshot QA, без page errors и горизонтального overflow.
- [ ] CI green после publication.
- [x] Gitleaks v8.24.3: публичный source snapshot чистый; runtime .env исключён из Git.
- [ ] SonarQube Quality Gate: внешняя настройка пока отсутствует.

### Проверки 2026-10-03

- PostgreSQL runtime: migration service exit 0; named volume сохраняется.
- Остановка worker: спустя freshness window health check возвращает failure.
- Остановка БД: `/ready` возвращает 503; после восстановления — 200.
- Сборка Web: Vite + TypeScript strict PASS; npm audit — 0 vulnerabilities.
- Independent review: исправлены обход i18n lint через JSX expressions/attributes и plain Uvicorn logs. Оба дефекта воспроизведены тестами RED→GREEN.
- Sentry before_send оставляет allowlisted metadata и структуру stack, удаляет request/user/extra/breadcrumbs/exception values; synthetic privacy test PASS. Live ingestion не проверялся.
- Локальный Python — 3.14; обязательный Python 3.13 проверен в Docker image.
- Browser plugin в списке skills отсутствует; использован repository Playwright workflow.

## Далее

Wave 0B backend/contracts/domain DB, Wave 0C полный shell/pages/typed domain API, Wave 0D production deployment/runbook не завершены.
Wave 1–8 collectors и operational/discovery modules не реализованы.
Полные pilot критерии v0.1 пока не выполнены.

Основная спецификация заморожена и описывает целевой продукт; этот документ отражает реализацию и evidence отдельно.
