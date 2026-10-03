# Storage Console

Storage Control Plane для наблюдаемости сетевого файлового хранилища.

> Репозиторий инициализирован. Детальная внутренняя инфраструктурная информация и исследовательские evidence не публикуются в этом публичном репозитории.

## Статус

**PLANNING / IMPLEMENTATION START**

Текущий этап: Wave 0 — foundation.

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
