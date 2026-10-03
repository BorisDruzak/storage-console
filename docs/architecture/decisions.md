# Архитектурные решения v0.1

## ADR-001 — API-first

Web Console, MCP/AI и внешние клиенты работают только через Storage API.

## ADR-002 — Collector push

Collectors отправляют telemetry/metadata по HTTPS. Backend не использует регулярные SSH/WinRM-сеансы для обычного мониторинга.

## ADR-003 — Metadata-first

Содержимое документов не читается по умолчанию. Content/schema inspection выполняется только в явно разрешённых Discovery jobs.

## ADR-004 — Canonical storage identity

Drive letter не является identity.

Canonical identity использует:
- source node;
- volume unique identity;
- object/file ID;
- parent ID;
- relative path history.

## ADR-005 — PostgreSQL first

PostgreSQL хранит metadata, state, telemetry aggregates и background jobs. Redis не обязателен в v0.1.

## ADR-006 — Raw signal != incident

Сигнал оценивается через baseline, policy, freshness, correlation, rate/burst и suppression.

## ADR-007 — No autonomous remediation

v0.1 не удаляет файлы, не меняет ACL/AD/SMB/VSS/PVE/PBS и не запускает restore автоматически.

## ADR-008 — Russian-first UI

ru-RU обязателен с первого UI-коммита. Только i18n keys.

## ADR-009 — Two product domains

Storage Operations / Observability и Data / Process Discovery — отдельные модули одной Control Plane.

## ADR-010 — Public repository hygiene

Production-specific infrastructure evidence и secrets не публикуются.
