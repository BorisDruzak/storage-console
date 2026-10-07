# Порядок задач Codex

## Wave 0

1. wave0-a-foundation.md
2. wave0-b-backend.md
3. wave0-c-web-ru.md
4. wave0-d-deployment.md

Production deployment: [русский runbook](../deployment/runbook-ru.md).

Wave 0B и Wave 0C могут частично выполняться параллельно только после Wave 0A.

## Далее

- Wave 1 — source registration / heartbeat / inventory
  - [Source management plan](../superpowers/plans/2026-10-04-source-management.md)
    — API/console регистрации и ключей collectors реализованы и проверены на изолированном
      HTTPS-стенде; общий delivery layer и живой inventory следуют отдельно.
  - [Collector durable delivery](../superpowers/plans/2026-10-04-collector-delivery.md)
    — transactional outbox/checkpoints и strict HTTPS опубликованы; реальная
      HTTPS/PostgreSQL crash/retry/rotation приёмка, финальный обзор и CI пройдены.
      Живые collectors не установлены.
  - [Windows heartbeat/inventory](../superpowers/plans/2026-10-04-windows-inventory.md)
    — native metadata и bounded producer приняты: Windows HTTPS/PG4 cases,
      финальный независимый обзор/RED→GREEN fixes и exact CI прошли.
  - [Simultaneous object paths](../superpowers/plans/2026-10-04-object-path-aliases.md)
    — DTO/ingest/schema/native hard links приняты: Linux508/46, Windows53/HTTPS-PG5,
      один полный обзор/RED→GREEN fixes и exact CI прошли. Windows Service/DACL,
      USN, large-tree backpressure/performance и live pilot остаются обязательными.
- Wave 2 — USN change stream
- Wave 3 — attribution
- Wave 4 — operational health
- Wave 5 — ACL / recovery / hygiene
- Wave 6 — diagnostics
- Wave 7 — Data Discovery
- Wave 8 — read-only MCP/AI

Не расширять Wave 0 задачами следующих волн без отдельного решения.

## MVP checkpoint — выполнять сейчас

Перед следующими Wave 1/2 задачами выполнить:

1. `mvp-pilot-001-live-fileserver.md` — первый живой FILESERVER → API → PostgreSQL → Web Console.

До его operator acceptance не переходить автоматически к Windows Service, USN, PVE/PBS, ACL, diagnostics или Discovery.

Операторский путь: [Windows live pilot runbook](../pilot/windows-live-pilot-ru.md).
CLI/wheel и disposable Windows → HTTPS → PostgreSQL → русская Web Console реализованы;
закрытие MVP checkpoint требует operator acceptance реального FILESERVER по checklist.
