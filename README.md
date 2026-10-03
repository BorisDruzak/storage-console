# Storage Console

Storage Control Plane для наблюдаемости сетевого файлового хранилища.

> Репозиторий инициализирован. Детальная внутренняя инфраструктурная информация и исследовательские evidence не публикуются в этом публичном репозитории.

## Статус

**IMPLEMENTATION IN PROGRESS**

Текущий этап: Wave 0A — foundation. Runtime API/worker и русский shell реализуются; live collectors и предметные данные отсутствуют. Подробный статус проверок: `docs/implementation-status.md`.

## Основные принципы

- API-first.
- Русский интерфейс `ru-RU` обязателен.
- Web/MCP не получают прямой доступ к файловой системе.
- Коллекторы отправляют метаданные и телеметрию в центральный API.
- v0.1 наблюдает, диагностирует и рекомендует; автоматическое исправление инфраструктуры не входит в scope.
- Документальное содержимое не читается по умолчанию.
- Raw counters не считаются инцидентами без policy-aware корреляции.

## План

1. Wave 0A — monorepo / Compose / CI / i18n.
2. Wave 0B — PostgreSQL / contracts / API / worker.
3. Wave 0C — русская Web Console.
4. Wave 0D — deployment package.
5. Wave 1+ — collectors и operational modules.

См. `docs/spec/storage-control-plane-v0.1.md` и `docs/tasks/`.

## Локальный запуск foundation

Требуются Docker Engine и Docker Compose v2 с поддержкой `--wait`.

```sh
cp .env.example .env
# Задайте локальный POSTGRES_PASSWORD; для URI используйте URL-safe значение.
docker compose up --build --wait --wait-timeout 180
```

Откройте http://localhost:8080. По умолчанию Web опубликован только на loopback.
PostgreSQL и API не публикуют порты в LAN. Это development stack: production HTTPS, authentication и deployment runbook относятся к следующим этапам.

```sh
docker compose ps
curl --fail http://localhost:8080/ready
docker compose exec worker python -m apps.worker.health
docker compose run --rm migrate alembic check
docker compose logs --tail=50 api worker
docker compose down
```

PostgreSQL хранится в named volume: обычный `down` сохраняет данные. `down -v` удаляет development database; не применять к данным, которые нужно сохранить.
Миграции выполняются до старта API и worker. `/health` API означает живой процесс, `/ready` — доступную БД; ни один из этих endpoints не означает исправность наблюдаемого хранилища.

## Проверки разработки

Python 3.13 обязателен в runtime/CI. Создайте virtualenv и установите lockfile:

```sh
python -m venv .venv
pip install -r requirements.lock
pytest --cov=apps --cov=packages --cov-report=xml
ruff check .
mypy
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Для PostgreSQL integration test нужны Alembic migration и `TEST_DATABASE_URL` **одноразовой тестовой БД**. Тест изменяет worker heartbeat; не направлять его на рабочую БД.
В CI migrations проверяются upgrade/check/downgrade/upgrade. ESLint запрещает literal JSX strings, TypeScript проверяет translation keys, Vitest проверяет полноту двух catalogs.

## Collector ingest — текущая реализация Wave 0B

Доступны `POST /api/v1/ingest/heartbeat`, `/inventory`, `/changes`, `/telemetry`, `/events`,
`/acl`, `/recovery`, `/hygiene`, `/diagnostic-bundles`.
Typed batch envelope version 1 содержит records и согласованные count/time window.
`first_event_at`/`last_event_at` должны точно совпадать с min/max timestamps records;
расширенный interval без соответствующих records отклоняется (422).
`Authorization: Bearer <collector-token>` проверяется по hash зарегистрированного enabled collector;
collector UUID должен совпадать с envelope. User credentials не принимаются.
Все записи привязаны к source этого collector, source UUID в payload запрещён.

Один batch выполняется в одной PostgreSQL транзакции вместе с receipt и audit entry.
Одинаковый batch возвращает 202 с `duplicate=true`; изменённое содержимое с тем же ID — 409.
Неизвестный volume — 409 с rollback всего batch. Inventory записывается в порядке records:
volume должен быть известен до share/object. Запоздалые observations не перезаписывают более новую
object/volume state или alias history. Delete сохраняет последний известный путь.

По умолчанию ingest body ограничен 16 MiB в API и development Nginx; validation errors не повторяют
input values. `MAX_INGEST_BYTES` настраивает API (при изменении нужно согласовать proxy limit).
ACL сохраняет порядок ACE; известная object identity требует одновременно volume и file ID.
Security evidence может храниться без корреляции; связь с change event проверяется в пределах source.
Backup, snapshot consistency, verification и restore test — отдельные metadata evidence;
отсутствие verification/restore не заменяется successful backup. Ingest не создаёт health findings.

Public OpenAPI: `packages/contracts/openapi/storage-console-v1.json`.
После изменения routes/contracts выполните `python -m packages.contracts.export_openapi`;
`--check` проверяет совпадение с runtime и выполняется в CI.
Collector provisioning/user sessions и queue продолжают реализацию Wave 0B/0D.
Live collectors не подключены.

## Read API — текущая реализация Wave 0B

Доступны `GET /api/v1/overview`, `/health/domains`, `/sources`, `/sources/{id}`,
`/sources/{id}/freshness`, `/volumes`, `/shares`. Пагинация: `limit` 1–100,
`offset` 0–1000000; volumes/shares допускают фильтр `source_id` (неизвестный source → 404).
Ответы читаются в согласованной PostgreSQL snapshot; ошибка БД → generic 503.

Freshness учитывает каждый enabled collector: receipt time, event time, collector last_seen
и heartbeat lag. Ответ показывает collector counts и bottleneck UUID; cursor/event timestamps
относятся к этому collector. `last_success_at` — время последнего успешного ingest source.
Missing/future observations дают UNKNOWN; превышение cadence — OBSERVE/WARNING/CRITICAL.
Свежий heartbeat не создаёт HEALTHY для operational domain: нужны актуальные persisted
policy findings. Неполное покрытие остаётся видимым даже при CRITICAL в другом scope.
Volumes/shares отдельно показывают metadata quality; aliases содержат только активные значения.

## Наблюдаемость и внешние gates

API/worker пишут JSON logs с UTC timestamp и allowlisted event names. Exception/config details не выводятся.
`SENTRY_DSN` необязателен: без него startup работает; с ним SDK использует `send_default_pii=false` и отключённый tracing по умолчанию. Реальное ingestion требует отдельной проверки.

SonarQube: задайте repository variable `SONAR_HOST_URL` и secret `SONAR_TOKEN`, обеспечьте сетевую доступность сервера runner-у. CI включает scan и quality gate при заданном URL; отсутствие настройки означает **непроверенный Sonar gate**, а не PASS. Для внутренних серверов нужен соответствующий runner.

Lockfiles фиксируют разрешённые версии. При обновлении dependencies повторяйте tests/build, `npm audit`, PostgreSQL migrations и Compose smoke.
