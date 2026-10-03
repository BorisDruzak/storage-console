# Codex Task — Wave 0C: Russian Web Console

## Goal

Реализовать полный русскоязычный shell Web Console поверх typed API abstraction.

## Navigation

- Обзор
- Состояние хранилища
- Активность
- Доступ и права
- Восстановление
- Гигиена данных
- Диагностика
- Поиск процессов
- Источники данных
- Политики
- Настройки
- Журнал действий

## Pages

### Обзор
Карточки:
- общее состояние
- свежесть данных
- capacity
- SMB
- NTFS
- access
- VSS
- Recovery
- PVE/ZFS
- Warning/Critical

### Состояние хранилища
Tabs:
- FILESERVER
- Том
- SMB
- DFS
- FSRM
- VSS
- PVE/ZFS
- Сеть

### Активность
Columns:
- Время
- Событие
- Пользователь
- Клиент
- Путь
- Было -> Стало
- Достоверность

### Доступ и права
- Expected vs Actual
- Drift
- Owner
- Group chain
- Exceptions

### Восстановление
Ladder:
- local snapshots
- off-host protection
- latest backup
- RPO
- verify
- restore test
- RTO

### Гигиена данных
- long paths
- age
- file types
- temp/lock
- large files
- zero-byte classification
- duplicate candidates
- rare extensions

### Диагностика
Pre-trigger / trigger / post-trigger timeline.

### Поиск процессов
- recurring series
- schema family
- digitization candidates
- workflow state

### Источники данных
- source
- online/offline
- version
- heartbeat
- lag
- cursor
- errors
- schema version

## Localization

Mandatory:
- ru-RU default
- en-US fallback
- react-i18next
- no hardcoded user-facing strings
- Russian loading/error/empty/tooltips/charts/forms/toasts
- configurable business timezone
- Cyrillic/UNC/long-path tests

Do not translate raw paths/SID/GUID/FileId/account/share names.

## UX

- persistent sidebar
- top freshness/status area
- filters in URL
- deep links
- typed API client
- explicit loading/empty/error/stale states
- keyboard/focus/ARIA
- state not communicated by color only

## Constraints

Не создавать:
- file manager;
- file delete/move actions;
- ACL mutation;
- backup/restore infrastructure action;
- fake green production health.

## Acceptance

1. Primary navigation entirely Russian.
2. Machine enums do not leak to normal UI.
3. Missing translation key test fails correctly.
4. UNKNOWN/STALE distinct from HEALTHY.
5. Recovery can show healthy platform + unprotected workload.
6. Raw event storm can render as grouped event.
7. Playwright ru-RU smoke covers primary pages.
8. No infrastructure mutation controls.
