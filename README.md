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

Требуются Linux, Python3.12+, OpenSSL, Docker Engine и Docker Compose v2 с поддержкой `--wait`.
Для одноразового стенда создайте отдельный приватный каталог с тестовыми TLS-файлами и env:

```sh
fixture_env=$(PYTHONPATH=. python tests/deployment/prepare_development.py)
docker compose --env-file "$fixture_env" -p storage-console-disposable up --build --wait --wait-timeout 180
```

Web публикуется только на loopback: HTTPS8443, HTTP8080 перенаправляет на HTTPS.
Тестовый origin — `https://storage.example.test:8443`; настройте разрешение этого имени
на loopback и доверие публичному `ca.pem` из каталога fixture только для тестового клиента.
Не отключайте проверку TLS. PostgreSQL и API не публикуют порты в LAN. Форме входа нужна
явно созданная локальная учётная запись: [bootstrap](docs/deployment/local-admin-ru.md),
в команде укажите тот же env и Compose-проект. Автоматического пользователя нет.

```sh
docker compose --env-file "$fixture_env" -p storage-console-disposable ps
curl --fail --noproxy '*' --cacert "$(dirname "$fixture_env")/ca.pem" --resolve storage.example.test:8443:127.0.0.1 https://storage.example.test:8443/ready
docker compose --env-file "$fixture_env" -p storage-console-disposable exec worker python -m apps.worker.health
docker compose --env-file "$fixture_env" -p storage-console-disposable run --rm migrate alembic check
docker compose --env-file "$fixture_env" -p storage-console-disposable down
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
Collector provisioning/user sessions продолжают реализацию Wave 1/0D.
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

## PostgreSQL worker queue

Ingest атомарно создаёт `ingest_postprocess` job вместе с receipt/domain records/audit.
Replay не создаёт вторую задачу. Worker использует `FOR UPDATE SKIP LOCKED` и transaction
advisory lock, сохраняет handler effect и COMPLETE в одной транзакции.
Handlers выполняют только DB effects через предоставленный connection: внешний I/O
этой гарантией не покрывается. Foundation handler проверяет применённый receipt и пишет
`INGEST_POSTPROCESSED`; operational policy processing относится к следующим waves.

Ошибки handler-а откатывают его savepoint; сохраняется generic `HANDLER_FAILED`.
Retry: exponential delay 2–300 секунд, default 5 attempts (enqueue допускает 1–20).
После лимита — FAILED; неизвестный kind — terminal `UNKNOWN_JOB_KIND`.
При потере процесса транзакция откатывается, задача остаётся доступной следующему worker.
`next_attempt_at`, attempts/status/error и UTC completion time хранятся в PostgreSQL.
Worker продолжает heartbeat и проверяет SIGTERM/SIGINT между задачами.

## Наблюдаемость и внешние gates

API/worker пишут JSON logs с UTC timestamp и allowlisted event names. Exception/config details не выводятся.
`SENTRY_DSN` необязателен: без него startup работает; с ним SDK использует `send_default_pii=false` и отключённый tracing по умолчанию. Реальное ingestion требует отдельной проверки.

SonarQube: задайте repository variable `SONAR_HOST_URL` и secret `SONAR_TOKEN`, обеспечьте сетевую доступность сервера runner-у. CI включает scan и quality gate при заданном URL; отсутствие настройки означает **непроверенный Sonar gate**, а не PASS. Для внутренних серверов нужен соответствующий runner.

Lockfiles фиксируют разрешённые версии. При обновлении dependencies повторяйте tests/build, `npm audit`, PostgreSQL migrations и Compose smoke.
