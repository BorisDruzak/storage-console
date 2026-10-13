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

## MVP-005 — история изменений и статистика (новый приоритет)

Вместо повтора 72-часового USN soak — выполнить
[сквозную задачу](mvp-005-history-and-statistics.md) A → B → C:

- **A:** защищённая история изменений по произвольным датам, путь/файл/тип, keyset pagination, история объекта, безопасный CSV; сначала закрыть текущую видимость сырых путей всем ролям с общим read.
- **B:** реальная статистика событий из PostgreSQL — по дням, типам, часам, каталогам; три графика в Web Console.
- **C:** сохранять реальные срезы полной ёмкости NTFS-томов при existing inventory ingest, показывать историю used/free/total. Не путать ёмкость всего тома с размером monitored root.

После каждого этапа — RED→GREEN, отдельный PR, exact-main CI, реальная Web Console, приёмка
в [журнале](../acceptance/mvp-005-execution-ledger.md). Нет повторного 72h soak, reboot,
изменений Collector/USN/ACL/SMB, автоматического расширения scope. После C — STOP.

## STORAGE-AUDIT-001 — независимое подтверждение исполнителя файловой операции

Issue #23: https://github.com/BorisDruzak/storage-console/issues/23

- [Полное ТЗ](storage-audit-001-windows-security-attribution.md): Windows Security 4663/4660/4624 и сопоставление с существующим NTFS USN.
- [Журнал приёмки](../acceptance/storage-audit-001-ledger.md): A collector, B central correlation, C operator-gated real pilot с двумя доменными пользователями и двумя ПК.
- Независимые service, bookmark, state/outbox. Сопоставление audit/USN не должно портить source freshness.
- Пересечение с Issue #22 (MVP-005): совместить admin-only History/RBAC, не перетирать параллельную разработку.
- **Разработка разрешена**; установка Audit службы, смена auditpol/GPO/SACL, тестовое файловое CRUD на FILESERVER — **только после отдельного согласия оператора**. Никаких 5145/WEF/версий файлов/72h soak в этой задаче.
