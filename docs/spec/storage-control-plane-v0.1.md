# Storage Control Plane v0.1 — техническая спецификация

Статус: PLANNING / NOT IMPLEMENTED  
Версия: 0.1  
Язык интерфейса по умолчанию: ru-RU

## 1. Назначение

Storage Control Plane — внутренняя система наблюдаемости сетевого файлового хранилища.

Она объединяет два равноправных контура:

1. Storage Operations / Observability.
2. Data / Process Discovery.

Это не только аналитическая панель файлов.

## 2. Продуктовые границы

v0.1 умеет:
- наблюдать;
- диагностировать;
- коррелировать;
- хранить историю;
- показывать drift;
- формировать findings/incidents;
- поддерживать read-only Data Discovery jobs.

v0.1 не умеет автоматически:
- удалять/перемещать файлы;
- менять ACL/SACL;
- менять AD membership;
- менять SMB shares;
- менять quotas;
- удалять VSS;
- менять PVE/PBS/ZFS;
- выполнять restore;
- исправлять инфраструктуру.

## 3. Архитектура

~~~text
Windows Collector ─┐
PVE Collector ──────┼──> Storage API ───> PostgreSQL
PBS Collector ──────┘          │
                               ├──> State / Alert Worker
                               ├──> Diagnostic Bundle Store
                               ├──> Russian Web Console
                               └──> MCP / AI read-only
~~~

### API-first
Web и MCP работают только через API.

### Collector push
Collectors сами отправляют metadata/telemetry по HTTPS.

### Metadata-first
Содержимое документов не читается по умолчанию.

## 4. Рекомендуемый стек

Backend:
- Python 3.13
- FastAPI
- Pydantic v2
- SQLAlchemy 2
- Alembic
- PostgreSQL 16+
- pytest
- Ruff
- mypy или pyright

Frontend:
- React
- TypeScript strict
- Vite
- TanStack Query
- TanStack Table
- react-i18next
- Vitest
- Playwright

Deployment:
- Ubuntu Server 24.04 LTS
- Docker Compose
- Nginx
- TLS
- Sentry
- SonarQube

Redis не вводить без доказанной необходимости.

## 5. Русификация — обязательный release gate

Default locale: ru-RU  
Fallback locale: en-US

### Запрет
User-facing строки в React нельзя hardcode.

Использовать только translation keys.

### Machine states

| Code | ru-RU |
|---|---|
| HEALTHY | Исправно |
| OBSERVE | Наблюдение |
| WARNING | Предупреждение |
| CRITICAL | Критично |
| UNKNOWN | Нет данных |
| NOT_APPLICABLE | Не применяется |

### Data quality

| Code | ru-RU |
|---|---|
| COMPLETE | Полные данные |
| PARTIAL | Частичные данные |
| STALE | Устаревшие данные |
| ESTIMATED | Оценка |
| UNAVAILABLE | Недоступно |

### Обязательное русское меню
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

### Форматы
- DB timestamps: UTC timestamptz.
- UI timezone configurable.
- ru-RU number/date formatting.
- размеры в КиБ/МиБ/ГиБ/ТиБ.
- paths/accounts/SID/GUID/FileId не переводить.

### Обязательные тесты i18n
- Cyrillic paths;
- длинные пути;
- mixed Cyrillic/Latin;
- UNC;
- missing translation key;
- loading/empty/error states;
- CSV/XLSX кириллица.

## 6. Аутентификация и роли

User auth:
- AD/LDAP/LDAPS-compatible architecture;
- secure session cookie;
- CSRF protection для state-changing endpoints;
- break-glass local admin only if documented.

Roles:
- storage_admin
- storage_operator
- auditor
- analyst
- viewer

Collector authentication отдельно от user sessions.

## 7. Canonical identity

### Source node
Поля:
- source_node_id
- source_type
- hostname
- fqdn
- instance_id

Source type:
- FILESERVER
- PVE
- PBS

### Volume
Drive letter не является identity.

Хранить:
- volume_id
- unique volume identity
- filesystem
- label
- current mount aliases
- source_node_id

### Filesystem object
Unique key:
- volume_id
- file_id

Хранить:
- parent_file_id
- type
- current_name
- current_relative_path
- first_seen_at
- last_seen_at
- deleted_at

### Path history
Хранить историю path aliases / rename.

## 8. Windows Collector

Windows Service.

Local durable state:
- collector identity;
- USN cursor;
- Journal ID;
- FileId path cache;
- last-known path;
- durable outbox;
- local metric ring buffer.

### USN
Собирать:
- Journal ID
- USN
- FileId
- ParentFileId
- reason bitmask
- timestamp
- name

Reason parsing по bitmask, не по локализованному тексту.

### Rename
RENAME_OLD + RENAME_NEW одного FileId сворачивать в одно событие.

### Delete
DELETE использует last-known path cache.

### Windows enrichment
Поддержать:
- 4663
- 4660
- 5145

Collector не включает audit policy самостоятельно.

Если source не настроен:
- NOT_CONFIGURED / UNKNOWN
а не ERROR.

### Operational sources
- volumes/partitions
- SMB
- DFS
- FSRM
- VSS
- services
- scheduled tasks
- event channels
- CPU/memory/disk/network telemetry
- ACL state

## 9. PVE Collector

Read-only сбор:
- node health
- VM state/config
- QEMU state
- disk mapping
- storage status
- ZFS pool/vdev health
- scrub state
- host load
- VM network path
- configuration drift

Запрещены mutation commands.

## 10. PBS Collector

Read-only сбор:
- datastore health/capacity
- protection coverage
- backup groups/snapshots
- latest backup age
- verify
- prune
- GC
- task failures
- restore evidence
- version/lifecycle state

## 11. Normalized change event

Machine event types:
- CREATE
- WRITE
- RENAME
- DELETE
- METADATA_CHANGE
- SECURITY_CHANGE

Event включает:
- canonical object
- occurred_at
- old/new relative path
- FileId/ParentFileId
- actor
- client IP/name
- evidence sources
- confidence

## 12. Health states

Использовать:
- HEALTHY
- OBSERVE
- WARNING
- CRITICAL
- UNKNOWN
- NOT_APPLICABLE

Не использовать единый «процент здоровья».

Overview показывает отдельные domains:
- Телеметрия
- Ёмкость
- Файловая система
- SMB/DFS
- Доступ и права
- VSS
- PBS/Recovery
- Сеть
- PVE/ZFS
- Гигиена данных

UNKNOWN не должен выглядеть зелёным.

## 13. Signal / Finding / Incident

Signal:
- raw observation.

Finding:
- policy-evaluated normalized result.

Incident:
- grouped actionable condition.

Stable fingerprint:
- domain
- signal type
- canonical object
- principal/client
- cause class

Thousands of repeated raw events must not create thousands of incidents.

## 14. Freshness

Каждый source имеет:
- expected cadence
- last success
- source event timestamp
- cursor/lag

Пример логики:
- current -> HEALTHY
- 1 missed interval -> OBSERVE
- 2–3 missed -> WARNING
- prolonged gap / continuity risk -> CRITICAL
- never configured -> UNKNOWN

## 15. Capacity

Хранить:
- total
- used
- free
- quota
- growth
- forecast

Default policy values configurable.

Пример:
- <70% HEALTHY
- 70–80 OBSERVE
- 80–90 WARNING
- >=90 CRITICAL

Forecast может повышать severity раньше статического порога.

## 16. NTFS / filesystem integrity

Signals:
- volume health
- dirty bit
- integrity scan evidence
- NTFS/storage events
- enumeration gaps
- USN state

Не считать long paths повреждением filesystem.

## 17. SMB operations

Отдельно:
- sessions
- open files
- dialect
- service state
- signing/encryption policy
- throughput
- slow operations
- authorization telemetry

Slow-operation events являются diagnostic triggers.

Raw access-denied counts не являются incident counts.

## 18. Authorization / ACL drift

Сравнивать с semantic templates.

Track:
- DACL fingerprint
- owner
- inheritance
- share ACL
- expected group chain
- unresolved SID
- direct user ACE
- group scope/category
- policy exceptions

Поддерживать explicit exception model.

## 19. Recovery ladder

Состояния recovery должны различать:

1. local snapshots
2. off-host protection policy
3. latest backup
4. RPO
5. verification
6. retention/GC health
7. restore test
8. measured RTO
9. consistency level

Consistency:
- CRASH_CONSISTENT
- GUEST_AGENT
- VSS_QUIESCED
- UNKNOWN

Healthy backup platform не означает protected workload.

## 20. Hygiene

### Long paths
Buckets:
- 240+
- 260+
- 320+
- 400+
- 500+

### File age
LastWriteTime buckets:
- 0–30d
- 31–90d
- 91–180d
- 181–365d
- 366–730d
- >730d

Age не означает delete candidate.

### Temp/lock
Различать active/recent/stale.

### Zero-byte
Классифицировать по extension/path context.

### Duplicate candidates
Stage 1:
- normalized filename + exact size

Stage 2:
- targeted hashing

States:
- CANDIDATE
- HASH_PENDING
- CONFIRMED
- DIFFERENT_CONTENT
- EXCLUDED

Auto-delete запрещён.

## 21. Data / Process Discovery

Отдельные approved jobs.

По умолчанию metadata-only.

Content inspection job должен иметь:
- scope
- extensions
- max files
- max bytes
- parser
- purpose

Outputs:
- recurring series
- schema family
- digitization candidates
- confidence
- workflow state

## 22. PostgreSQL schema domains

Core:
- source_nodes
- collectors
- collector_heartbeats
- volumes
- shares
- filesystem_objects
- object_path_history

Activity:
- change_events
- event_attributions
- event_evidence_links

Telemetry:
- metric_samples_1m
- metric_samples_1h
- metric_samples_1d
- diagnostic_bundles

Health:
- health_signals
- health_findings
- incidents
- incident_events
- health_policies
- policy_exceptions

Authorization:
- principals
- ad_groups
- group_memberships
- acl_templates
- acl_snapshots
- acl_aces
- acl_findings

Recovery:
- vss_snapshots
- backup_jobs
- backup_snapshots
- backup_verifications
- restore_tests
- recovery_policies

Hygiene:
- hygiene_snapshots
- scope_stats
- long_path_samples
- large_file_samples
- temp_artifact_stats
- duplicate_candidates

Discovery:
- discovery_jobs
- discovery_series
- discovery_schema_families
- digitization_candidates

Security:
- users
- roles
- user_roles
- audit_log

## 23. Partitioning / retention

High-volume time tables partition by time.

Initial retention:
- local ring buffer: 15–60 min
- triggered diagnostics: ~180 days
- 1-minute telemetry: ~90 days
- hourly aggregates: ~1 year
- daily capacity/health: multi-year
- ACL changes: retain all changes
- recovery evidence: separate policy

Exact production retention is configurable.

## 24. Background jobs

PostgreSQL-backed queue:
- FOR UPDATE SKIP LOCKED
- retries
- next_attempt_at
- error state
- idempotency key
- advisory locks

No Redis in Wave 0.

## 25. API

Base:
- /api/v1

Auth:
- /auth/login
- /auth/logout
- /auth/me

Overview:
- /overview
- /health/domains

Sources:
- /sources
- /sources/{id}
- /sources/{id}/freshness

Storage:
- /volumes
- /shares
- /scopes
- /objects/{id}
- /objects/{id}/history

Activity:
- /activity
- /activity/{id}

Health:
- /findings
- /incidents
- /incidents/{id}

ACL:
- /acl/scopes
- /acl/findings
- /acl/templates
- /acl/groups

Recovery:
- /recovery/overview
- /recovery/vss
- /recovery/backups
- /recovery/restore-tests

Hygiene:
- /hygiene/overview
- /hygiene/long-paths
- /hygiene/age
- /hygiene/temp-artifacts
- /hygiene/large-files
- /hygiene/duplicates

Diagnostics:
- /diagnostics
- /diagnostics/{id}

Discovery:
- /discovery/candidates
- /discovery/series
- /discovery/jobs

## 26. Collector ingest

Separate collector authentication.

Endpoints:
- /ingest/heartbeat
- /ingest/telemetry
- /ingest/changes
- /ingest/events
- /ingest/inventory
- /ingest/acl
- /ingest/recovery
- /ingest/hygiene
- /ingest/diagnostic-bundles

Every batch:
- collector_id
- batch_id
- schema_version
- sent_at
- first_event_at
- last_event_at
- record_count

batch_id idempotent.

## 27. Web Console

Required pages:
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

No file-manager behavior.

## 28. Event-triggered diagnostics

Collectors keep short local ring buffer.

Trigger bundle:
- pre-trigger interval
- event interval
- post-trigger interval

Potential triggers:
- SMB slow operation
- filesystem/storage error
- VSS failure
- ZFS failure
- USN continuity risk
- high-impact ACL drift
- backup failure

## 29. MCP / AI

MCP — read-only consumer of Storage API.

Forbidden direct access:
- filesystem
- DB
- collector local state
- PVE/PBS shell

No remediation tools in v0.1.

## 30. Reliability requirements

Collector:
- durable outbox
- restart-safe cursor
- retry/backoff
- idempotent upload
- continuity checks

API:
- transactional migrations
- health endpoints
- no duplicate-batch data loss

Worker:
- idempotent jobs
- retry
- singleton locks

## 31. Performance targets

Initial targets:
- >=500k filesystem objects
- >=1M change events
- >=90 days minute telemetry

Interactive:
- overview P95 <2 sec
- filtered activity first page P95 <2 sec
- ACL view <2 sec
- hygiene overview <3 sec

Collector:
- average CPU <5% outside scheduled scans
- memory target <500 MiB

## 32. Deployment

Dedicated central VM.

Recommended baseline:
- Ubuntu Server 24.04 LTS
- 4 vCPU
- 16 GiB RAM
- separate OS and data disks
- HTTPS only
- PostgreSQL not exposed to LAN

Production addresses, DNS names, certificate paths and credentials supplied out-of-band.

## 33. Quality gates

PR gate:
- backend tests
- frontend tests
- lint
- type checks
- migration check
- OpenAPI compatibility
- i18n missing-key test
- Playwright smoke
- SonarQube Quality Gate
- secret scan

## 34. Implementation waves

Wave 0A:
- repository foundation
- Compose
- CI
- i18n

Wave 0B:
- PostgreSQL
- contracts
- ingest/read API
- worker foundation

Wave 0C:
- Russian Web Console shell

Wave 0D:
- deployment package/runbook

Wave 1:
- source registration/heartbeat/inventory

Wave 2:
- USN

Wave 3:
- attribution

Wave 4:
- operations health

Wave 5:
- ACL/recovery/hygiene

Wave 6:
- diagnostics

Wave 7:
- Data Discovery

Wave 8:
- MCP/AI

## 35. Definition of Done v0.1 pilot

- Russian UI usable end-to-end.
- No hardcoded user-facing strings.
- Collector/API data contracts versioned.
- Missing/stale data shown distinctly.
- USN continuity survives restart.
- Activity can represent create/write/rename/delete.
- Recovery distinguishes local snapshots, backup, verify and restore evidence.
- ACL drift uses templates/exceptions.
- Hygiene exposes long paths/age/temp/large/duplicate candidates.
- Raw event storms are aggregated.
- Diagnostics can preserve trigger context.
- Web/MCP have no direct filesystem access.
- No autonomous remediation.
- Audit logging enabled.
- CI/Sonar/Playwright/Sentry foundation in place.
- Deployment and backup/restore runbooks documented.

## 36. Public repository rule

Production topology, internal addresses, real identities, ACL evidence, credentials and diagnostic archives do not belong in this public repository.

Production values must be injected via deployment configuration/secrets and maintained outside public source control.
