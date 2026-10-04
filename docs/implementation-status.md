# Статус реализации

## Пользовательская авторизация — source acceptance, публикация CI ожидается

Локальный аварийный администратор и строгий LDAPS-провайдер, сессии с DB-clock expiry,
Origin/CSRF, пять ролей и защищённые read API реализованы. Русская/английская форма входа,
восстановление сессии и очистка evidence при выходе/read401 проверены. Приватный JSON
монтируется только в API; development и production Compose требуют HTTPS.

Linux3.13/PostgreSQL16: backend203, deployment45, миграции/check, mypy67/strict deploy6 PASS.
Frontend81 и shell E2E11, lint/types/build/OpenAPI, Gitleaks/ShellCheck PASS; npm audit0.
Изолированный production Compose: строгий TLS и отказ недоверенному CA, настоящий Chromium
login/reload/cross-tab logout/read401, CSRF/collector boundary, backup/restore0002→head PASS.
Один независимый полный обзор завершён; замечания по CA permissions и аудиту исправлены
и подтверждены. Подробности: [план авторизации](superpowers/plans/2026-10-04-user-auth.md).

Это не приёмка живого AD, внешних Sonar/Sentry, production DNS или переключения основного
runtime. Эти инфраструктурные проверки остаются открытыми.

Первый интеграционный push `bf8ae84b12b1aff92e394778f26c987307b91dd1` проверен на main.
CI обнаружил отсутствие keyUsage в синтетическом CA при строгой проверке Python3.13.
Генератор fixture исправлен без отключения TLS-проверок: deployment46 PASS, включая
OpenSSL -x509_strict/server-purpose/hostname и отказ неправильному hostname.
Терминальный результат исправленного CI ещё ожидается.

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
- Read API реализован: overview, domain health, source detail/freshness и bounded volumes/shares.
  Freshness учитывает всех enabled collectors; missing/stale/future evidence и lag не маскируются.
  Persisted policy findings необходимы для domain HEALTHY; UNKNOWN coverage сохраняется при CRITICAL.
- Python 3.13/PostgreSQL: 55 tests PASS; migration cycle/check, Ruff, strict mypy (52 files),
  OpenAPI repeatability и Gitleaks PASS. Fresh Compose read smoke: все сервисы healthy.
  Independent review и четыре regression RED→GREEN: multi-collector freshness и unknown scopes.
- Concurrent worker queue реализована: atomic ingest enqueue, SKIP LOCKED/advisory lock,
  savepoint rollback, bounded retries, terminal codes и transactional completion.
  Foundation postprocess acknowledgement не выдаётся за operational policy processing.
- Python 3.13/PostgreSQL: 62 tests PASS; Ruff, strict mypy (54 files), OpenAPI/migration
  checks и Gitleaks PASS. Два worker в Compose, остановка/возобновление и restart:
  один job, один postprocess effect, одна attempt; оба worker healthy.
- Final review исправление: batch boundaries точно равны min/max records; inflated fresh
  envelope со stale records воспроизведён RED→GREEN. Ранее принятые metadata не переписываются.
- Backend foundation Tasks 1–6 опубликованы: `bee5f78f780df9249a0f29f0fd0af26894705902`;
  [CI](https://github.com/BorisDruzak/storage-console/actions/runs/37151579965) success,
  backend/frontend/Compose/secrets PASS. Sonar skipped — external acceptance gate unverified.
- Partitioning/retention и operational domain processing остаются последующим этапам спецификации.

## Далее

Wave0C Task1: typed GET client и runtime response validation из published OpenAPI реализованы.
11 transport tests (15 frontend tests total), cancellation/timeout/safe errors,
bounded pages/source filters, query deduplication, Cyrillic/UNC preservation PASS.
Generated types/schema drift и negative control PASS; npm ci/lint/types/build/audit PASS.
Live overview domain cards/source list+detail/volumes/shares подключены к typed API.
12 URL links, bounded paging, source filters и back restoration проверены; данные refetch каждые
30 секунд, errors скрывают старый successful view. Unknown/stale отделены от health и API readiness.
20 Vitest +4 Playwright PASS, actual Compose/CSP read API desktop+mobile и synthetic stale inventory
проверены. Standalone validators исправляют запрещённую CSP runtime compilation; CSP сохранён.
Полные overall/freshness summaries и остальные domain pages/locale-timezone UX остаются впереди.

Wave 0B backend/contracts/domain DB/queue реализованы; external Sonar gate не подтверждён.
Wave 0C полный shell/pages/typed domain API и Wave 0D production deployment/runbook не завершены.
Wave 1–8 collectors и operational/discovery modules не реализованы.
Полные pilot критерии v0.1 пока не выполнены.

Основная спецификация заморожена и описывает целевой продукт; этот документ отражает реализацию и evidence отдельно.
