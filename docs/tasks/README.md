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
- Wave 2 — USN change stream
- Wave 3 — attribution
- Wave 4 — operational health
- Wave 5 — ACL / recovery / hygiene
- Wave 6 — diagnostics
- Wave 7 — Data Discovery
- Wave 8 — read-only MCP/AI

Не расширять Wave 0 задачами следующих волн без отдельного решения.
