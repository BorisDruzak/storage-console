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

## Наблюдаемость и внешние gates

API/worker пишут JSON logs с UTC timestamp и allowlisted event names. Exception/config details не выводятся.
`SENTRY_DSN` необязателен: без него startup работает; с ним SDK использует `send_default_pii=false` и отключённый tracing по умолчанию. Реальное ingestion требует отдельной проверки.

SonarQube: задайте repository variable `SONAR_HOST_URL` и secret `SONAR_TOKEN`, обеспечьте сетевую доступность сервера runner-у. CI включает scan и quality gate при заданном URL; отсутствие настройки означает **непроверенный Sonar gate**, а не PASS. Для внутренних серверов нужен соответствующий runner.

Lockfiles фиксируют разрешённые версии. При обновлении dependencies повторяйте tests/build, `npm audit`, PostgreSQL migrations и Compose smoke.
