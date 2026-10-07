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

## MVP-PILOT-002 — использовать уже полученный live inventory

После operator acceptance MVP-PILOT-001 выполнить:

1. `mvp-pilot-002-inventory-dashboard.md` — исправить inventory freshness, показать реальную ёмкость на Overview, оставить filesystem integrity честно UNKNOWN и включить `Asia/Yekaterinburg` по умолчанию.

До завершения MVP-PILOT-002 не переходить автоматически к новым collectors/USN/Windows Service.

## Controlled MVP delivery train — после MVP-PILOT-002

Следующий **единый** task:

- docs/tasks/mvp-003-004-three-stage-delivery-train.md — три обязательные стадии:
  A. Стабилизация/CI/main и operator acceptance;
  B. Windows Service/autostart/reboot acceptance;
  C. NTFS USN → real Activity.
- docs/acceptance/mvp-003-004-execution-ledger.md — журнал SHA, RED→GREEN, CI и operator checkpoints.

Переход A→B→C строго по PASS gates. Реальный FILESERVER не перезагружать без
отдельного явного согласия оператора. USN допускается только read-only;
нет автоматических ACL/SMB/audit policy изменений. По завершении Stage C — STOP.
