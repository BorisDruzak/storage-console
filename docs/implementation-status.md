# Статус реализации

## Wave 0A — foundation опубликован; внешний Sonar gate не проверен

- [x] Monorepo directories: API, Web, worker, collectors, contracts, i18n, shared, migrations, deploy, tests.
- [x] Backend settings, JSON logs, health/readiness, optional Sentry hooks.
- [x] Worker heartbeat с проверкой свежести; UTC timestamptz migration.
- [x] Русский shell, 12 navigation entries, ru-RU default/en-US fallback, missing-key checks.
- [x] Frontend/backend tests и локальные lint/types/build.
- [x] Compose/Nginx и GitHub Actions definitions.
- [x] Чистый source snapshot + новая БД: PostgreSQL/API/Web/worker healthy; повторный startup сохраняет volume.
- [x] Fresh Git clone опубликованного `main` + отдельный Compose project/новый volume: все сервисы healthy.
- [x] Migration upgrade/check/downgrade/upgrade на disposable PostgreSQL.
- [x] Playwright smoke против собранного stack: 2/2; desktop/mobile screenshot QA, без page errors и горизонтального overflow.
- [x] CI green после publication: backend, frontend, Compose smoke, secrets.
- [x] Gitleaks v8.24.3: публичный source snapshot чистый; runtime .env исключён из Git.
- [ ] SonarQube Quality Gate: внешняя настройка пока отсутствует.

### Проверки 2026-10-03

- Commit: `97743e76405d9385d5f932d4b6ec9e3071b4072e`, `feat(foundation): add Compose runtime and Russian console shell`.
- [GitHub Actions run](https://github.com/BorisDruzak/storage-console/actions/runs/37145656343): success. Sonar job skipped — не считать Sonar gate успешным.
- Python 3.13 + PostgreSQL: 8/8 tests PASS; Vitest: 4/4; Playwright: 2/2; i18n lint negative-control test: PASS.
- PostgreSQL runtime: migration service exit 0; named volume сохраняется.
- Остановка worker: спустя freshness window health check возвращает failure.
- Остановка БД: `/ready` возвращает 503; после восстановления — 200.
- Сборка Web: Vite + TypeScript strict PASS; npm audit — 0 vulnerabilities.
- Independent review: исправлены обход i18n lint через JSX expressions/attributes и plain Uvicorn logs. Оба дефекта воспроизведены тестами RED→GREEN.
- Sentry before_send оставляет allowlisted metadata и структуру stack, удаляет request/user/extra/breadcrumbs/exception values; synthetic privacy test PASS. Live ingestion не проверялся.
- Локальный Python — 3.14; обязательный Python 3.13 проверен в Docker image.
- Browser plugin в списке skills отсутствует; использован repository Playwright workflow.

## Wave 0B — schema и collector contracts

2026-10-04:

- 47 required domain tables и supporting volume_aliases, ingest_batches, jobs созданы immutable migration `0002`.
- UUID/FK constraints, canonical volume/object uniqueness, timezone-aware timestamps.
- Version 1 batch envelope и typed records для девяти collector domains: bounded counts/strings/numbers,
  UTC normalization, extra-field rejection, согласованные count/time window.
- Python 3.13 + disposable PostgreSQL: 18 tests PASS; upgrade/check/downgrade/upgrade/check PASS.
- Ruff и strict mypy PASS. Independent review: исправлены storage bounds и сохранение volume identity
  в change events до разрешения object FK.
- Ingest heartbeat/inventory/changes: collector-only hashed token, source scope, atomic receipts/audit,
  concurrent duplicate replay и 409 при changed payload; canonical aliases/path history/delete.
- Request body limit 16 MiB; validation errors не возвращают входные значения.
- Дополнительный Python 3.13/PostgreSQL suite: 25 tests PASS, Ruff/mypy PASS.
- Compose smoke отдельного development project: fresh volume/migrations/API/worker/Web healthy.
- Independent review: alias reassignment и late claim после alias release воспроизведены RED→GREEN.
- [Schema/contracts CI](https://github.com/BorisDruzak/storage-console/actions/runs/37147154415): success;
  backend/frontend/Compose/secrets PASS, Sonar skipped.
- Все девять ingest domains реализованы: telemetry/events/ACL/recovery/hygiene/diagnostic-bundles
  используют ту же transactional receipt/auth/source boundary.
- Uncorrelated security evidence сохраняется в collector_events; explicit event link проверяет source.
  Collector confidence не становится автоматической attribution/health finding.
- ACL сохраняет ACE ordinal; recovery отдельно сохраняет backup/snapshot/verification/restore metadata,
  job и snapshot observation ordering проверяются независимо.
- Migration 0003 сохраняет существующие recovery rows и неизвестный legacy ACE order (NULL).
  Legacy observation timestamps backfilled из event time, без утверждения актуальной freshness.
- Public OpenAPI соответствует runtime: `python -m packages.contracts.export_openapi --check` PASS.
  CI проверяет drift. Python 3.13/PostgreSQL: 40 tests PASS; Ruff/mypy PASS, migration cycle PASS.
- Fresh Compose domain smoke: PostgreSQL/API/worker/Web healthy, `/ready` 200,
  Alembic check и worker health PASS; Gitleaks public source scan PASS.
- Read API и concurrent worker queue пока не реализованы.
- Partitioning/retention и operational domain processing остаются последующим этапам спецификации.

## Далее

Wave 0B backend/contracts/domain DB, Wave 0C полный shell/pages/typed domain API, Wave 0D production deployment/runbook не завершены.
Wave 1–8 collectors и operational/discovery modules не реализованы.
Полные pilot критерии v0.1 пока не выполнены.

Основная спецификация заморожена и описывает целевой продукт; этот документ отражает реализацию и evidence отдельно.
