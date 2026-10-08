# Статус реализации

## Issue #8 — delivery train A → B → C

GATE A PASS на runtime `dda125d08f97fac78ccea466ec89fd0ad6f79776` после
merged PR #9 и [exact-main push CI](https://github.com/BorisDruzak/storage-console/actions/runs/37686825905):
все шесть обязательных jobs PASS; Sonar SKIPPED. Полный regression и независимый
source review пройдены. Central обновлён через runbook после проверенного backup;
exact images/revision, TLS/auth/redirect, Alembic check, продолжение heartbeat,
реальные inventory/capacity/UNKNOWN, desktop/mobile/reload/timezone проверены.
Pre/post-deploy backup и внешние копии проверены; rollback сохранён.
Issues #5/#6 закрыты с evidence. Stage B / Windows Service реализован:
native SCM wrapper, lifecycle CLI, LocalSystem и installed-wheel negative/native
проверки; полный frozen-source regression и независимый review завершены.
PR #11 merged как `c28ef069236a67da2f03bbaa5637fa29e7b88002`; exact head/main CI:
все шесть required jobs SUCCESS, Sonar SKIPPED. Точные release/rollback wheel
проверены native operator lifecycle. По явному указанию пользователя пакет перенесён
на FILESERVER, выполнены foreground Ctrl+C → service и stop/start: LocalSystem,
тот же config/identity/binding, heartbeat/inventory HEALTHY и очередь 0/0 подтверждены.
Live reboot B PASS: пользователь сам отправил FILESERVER в reboot и поручил проверку.
Служба автоматически запустилась в session 0 от LocalSystem примерно через 139 секунд
после boot, без интерактивного входа. Console HEALTHY примерно через 155 секунд;
новый heartbeat, inventory и очередь 0/0 подтверждены. Codex не выполнял reboot
или ручной start/run после boot. Существующие ACL/SMB/audit policy неизменны;
USN configuration не менялась. Browser login/source/inventory/reload после reboot
PASS, strict TLS без bypass. Evidence и screenshots остаются приватными.
Initial CI документального PR #14 упал на native synthetic replay timeout;
причина не установлена, локальное воспроизведение PASS. Добавлена bounded
failure-only диагностика без изменения runtime, predicate или timeout. Fresh head
`fda8a7597ee665e48f78875ba7b9f668278066d8` / CI `37732147714`: все шесть jobs
SUCCESS, native 43 passed без skips; Sonar SKIPPED. Диагностика не объявлена fix.
GATE B BLOCKED: final head `7d957032…` / CI `37732725825` упал в другом native
queue-pressure/lost-ACK test: `STATE_UNAVAILABLE` при чтении outbox status.
Native 42 passed, включая сервисный replay test; пять других jobs PASS.
Diagnostic head `54f83b34…` / CI `37733855050` доказал SQLite code 5
на `BEGIN IMMEDIATE`: test observer запрашивал writer lock для чтения status.
Test-only correction — отдельный read-only observer с прежними limits, runtime
сохраняет writable outbox. Reserved-lock RED воспроизведён; прежние assertions
и deadlines сохранены. Corrected PR #14 head `cdd48fd82…` / CI `37734822496`:
все шесть jobs SUCCESS; exact merged-main `8e7eb05f96…` / CI `37735548662`:
FAIL, native 41 passed / 2 failed, пять других jobs SUCCESS, Sonar SKIPPED.
Дополнительная диагностика доказала BUSY на PRAGMA у test monitor и оставшиеся
только новые heartbeat после успешной доставки старого outage backlog.
Дополнительные native RED→GREEN: bounded exclusive lock с отдельным read-only
monitor (runtime busy budget неизменен); slow HTTPS receipt и штатная cadence
30 секунд только lifecycle fixture, прежний drain deadline 105 секунд сохранён.
Полный локальный installed CLI/native regression: 57 passed без skips, Python
3.14.3; independent review без Important, Ruff/diff-check/public secret scan PASS.
Runtime на FILESERVER не меняется: продолжает автоматически запущенный SYSTEM
процесс, queue 0/0 и HEALTHY подтверждены повторно. GATE B остаётся BLOCKED до
fresh full exact head/main CI, включая target Python 3.13. USN / Stage C не начат.
[PR #15](https://github.com/BorisDruzak/storage-console/pull/15) head `a4333e3f40…`
/ CI `37738636490`: все шесть jobs SUCCESS, native 43 passed без skips. Exact
merged-main `30ac6c69ac…` / CI `37739444011`: FAIL, native 42 passed / 1 failed,
пять других jobs SUCCESS, Sonar SKIPPED. Service replay PASS; capture integration
получил `NATIVE_FAILED` после 6 records / 3 batches. Причина пока не установлена.
Добавлена только test-only bounded диагностика installed worker (runpy/exception
codes, без exception text/locals/paths); обычный entrypoint проверяют другие
native tests. Это diagnostic execution, не fix; budgets и deadlines не меняются.
GATE B BLOCKED, C NOT STARTED до диагностики/full exact head+main CI.
Operator checklist:
[Windows Service](pilot/windows-service-ru.md).
Актуальные SHA, результаты и незакрытые проверки:
[execution ledger](acceptance/mvp-003-004-execution-ledger.md).
Любая следующая перезагрузка реального FILESERVER требует отдельного явного разрешения.

## MVP-PILOT-002 — inventory dashboard (Issue #6)

Реализован отдельный central `inventory_stale_seconds` (default 7200, 1..604800):
volume/share quality и HTTP evidence не используют heartbeat cadence. Overview
расширен typed capacity/inventory summaries; OpenAPI, generated TS и standalone
validators обновлены. Totals включают только current complete capacity с total > 0,
state определяется худшим томом по frozen thresholds 70/80/90%; excluded count виден.
Filesystem inventory показывает типы/число томов/время без вывода о целостности.
Domain health engine и overall semantics сохранены; новые collectors не добавлены.
Общий IEC formatter применяется на Overview и в таблице томов. Новый browser profile
использует Asia/Yekaterinburg, явно сохранённый UTC сохраняется.

Regression покрывает отдельную freshness, границы capacity, worst volume, отсутствие/
stale/partial/future/нулевую capacity, sums и независимость overall. Web проверки:
capacity/filesystem UNKNOWN, i18n, IEC, timezone; Playwright desktop/mobile — Overview,
volumes, reload и explicit UTC.

Runtime revision: `f12b345ecd660618fce35f11ff4f3fb0dc05a529` (feature
`9624d6fff62429709ec3f291ebe9bc62062609c7`, затем deployment parser для bounded
`INVENTORY_STALE_SECONDS`). [CI37674102372](https://github.com/BorisDruzak/storage-console/actions/runs/37674102372)
успешен: шесть обязательных jobs; backend 590 passed/50 skipped, frontend 121,
Playwright 12. Sonar SKIPPED: не настроен.

Central pilot обновлён после CI. До переключения проверен PostgreSQL backup и
сохранена копия вне ВМ; предыдущие checkout/env оставлены для rollback. Exact
revision/image checks, HTTPS/redirect, четыре healthy services, `alembic check`
и runtime `inventory_stale_seconds=7200` подтверждены.

Live operator acceptance на существующем FILESERVER: PASS. Реальные authenticated read
APIs и Chromium со strict TLS, без mocks: Overview/Volumes на desktop и mobile, reload,
default Asia/Yekaterinburg и сохранённый UTC; console/page errors = 0. Inventory старше
пяти минут остаётся COMPLETE. Capacity вычислена по реальным current данным; filesystem
inventory виден, integrity и overall остаются UNKNOWN. Source identity, volume
identity/mount aliases и ненулевые object counts сохранены. Collector/runtime
configuration не менялись; новые providers не добавлены. Скриншоты и сырые runtime
evidence хранятся отдельно от публичного репозитория.
Операторский checklist: [Windows live pilot](pilot/windows-live-pilot-ru.md#10-проверка-mvp-pilot-002-на-уже-подключённом-fileserver).

После deployment/live acceptance — STOP; Windows Service, USN и новые providers остаются вне этой задачи.

## Wave 1 — управление источниками в API и console; runtime в работе

Реализованы регистрация FILESERVER/PVE/PBS с неизменяемым UUID/natural identity,
регистрация соответствующих collectors, одноразовая выдача/ротация ключа и отключение.
Изменения требуют storage_admin, актуальной сессии и Origin/CSRF; collector bearer
не разрешает управление. В БД только хеш ключа; изменение и аудит атомарны.
Список collectors содержит metadata, без ключей/хешей. Источник без телеметрии
остаётся UNKNOWN. Размер JSON ограничен по фактически полученным байтам; ошибки generic,
ответы no-store. OpenAPI, TypeScript и standalone validators обновлены.

API опубликован в `adc8ad20088d26f2595b2132702ab81780c2ecbe`;
[CI37176997771](https://github.com/BorisDruzak/storage-console/actions/runs/37176997771)
завершён успешно: пять обязательных jobs, Sonar SKIPPED.
Финальная console-проверка Linux3.13/PostgreSQL16: backend291, миграции round-trip/check,
deployment46, Ruff/mypy72/strict deploy6/pipcheck/OpenAPI PASS.
Frontend115/types/lint/i18n/build/APIcheck/audit0 и shell E2E11 PASS; Gitleaks/ShellCheck PASS.

Русские/английские формы регистрации и управления доступны администратору; остальные
четыре роли видят metadata. Одноразовый ключ и соответствующий collector UUID показаны
только в component memory; закрытие, unmount, выход/expiry/известная смена роли очищают их.
После потерянного ответа обновляется metadata, без повторной выдачи ключа.
Настоящий Chromium на изолированном production Compose: strict TLS trust/rejection,
регистрация, реальная потеря ответа после commit enrollment, ротация, old-key401/new-key202,
disable401/re-enable202, source freshness, reload/mobile и backup/restore PASS.
Один полный независимый обзор завершён; два Important воспроизведены RED→GREEN и исправлены.
Console опубликован в `a9012163bce77815f709790502187fdce69cf46f`;
[CI37178692013](https://github.com/BorisDruzak/storage-console/actions/runs/37178692013)
успешен на точной ревизии: пять обязательных jobs, Sonar SKIPPED.
План: [source management](superpowers/plans/2026-10-04-source-management.md).
Общий outbox/delivery описан ниже; Windows/PVE/PBS runtime и живой inventory ещё не реализованы.

## Wave 1 — общий collector delivery; приёмка компонента завершена

Transactional SQLite outbox/checkpoints и strict HTTPS sender опубликованы в
`725849a39922a655f016fc1b61396db6d24d1abd` и
`d14258c34c1a70b7ec029555d00d93609aeadd0a`.
[CI37184767926](https://github.com/BorisDruzak/storage-console/actions/runs/37184767926)
завершён успешно: пять обязательных jobs, Sonar SKIPPED.
Сохраняются byte-identical replay, FIFO stream, capacity/quarantine evidence,
auth suspension после restart и защита от позднего lease/credential response.
SQLite schema1→2 обновляется атомарно; токен в state не хранится.

Настоящий Uvicorn HTTPS/API/PostgreSQL: client process death после server commit,
duplicate ACK без второго inventory effect, rotation/disable и explicit refresh
проверены на Linux3.13 и Windows. Route диагностики исправлен по published API;
diagnostic metadata реально сохраняются. Последний Linux full420/backend и46
deployment, миграции round-trip/check, mypy78+8, Ruff/OpenAPI/package/Gitleaks и
frontend API/types PASS. Независимый полный обзор завершён: одна гонка settlement
при обновлении ключа воспроизведена тремя тестами и исправлена атомарной проверкой
поколения внутри SQLite-транзакций. Финальный прогон после исправления прошёл.
Исходный код опубликован в `05410ba3d8caa5cdb29829aecfa52d80bce37b5c`;
[CI37186391705](https://github.com/BorisDruzak/storage-console/actions/runs/37186391705)
успешен на этой точной ревизии: пять обязательных jobs, Sonar SKIPPED.
Подробнее: [план](superpowers/plans/2026-10-04-collector-delivery.md),
[интерфейсы и эксплуатационные ограничения](../collectors/common/README.md).
Windows Service/ACL, USN и live Windows/PVE/PBS collectors/pilot остаются открытыми.

## Wave 1 — Windows metadata/heartbeat component принят; runtime остаётся в работе

Native Win32 provider: local scope validation, volume GUID/128-bit FileId, metadata-only
handles, complete mount aliases, Unicode/long paths, bounded streaming traversal.
Mapped network drives/reparse points не обходятся; фиксированные issue codes сохраняют
partial/error вместо ложной полноты. Pinned ancestors могут временно мешать directory
rename/delete. Producer пишет256-record/8MiB chunks с atomic checkpoint, scope
fingerprint, отдельным heartbeat stream и явной остановкой при queue pressure.
Restart начинает новый scan и сохраняет старые FIFO batches; durable enumeration
cursor/snapshot/deletion proof отсутствуют.

Windows temporary-tree/provider/producer50 PASS/1 platform SKIP; реальный
Windows HTTPS/PostgreSQL4 cases PASS. Retained replay/rename сохраняют FileId/object
identity; repeated partial hard-link scans не создают ложную историю путей.
Один свежий обзор выявил три Important: actual FSCTL scope escape, hard-link path
replacement и error-heartbeat false HEALTHY. Исправления проверены RED→GREEN:
handle-relative open/enumeration, MULTIPLE_LINKS partial и UNKNOWN/COLLECTION_ERROR.
Linux full458/backend (17 native-only SKIP)+46 deployment/migrations/types82+7/
Ruff/OpenAPI PASS; installed wheel/worker/provider imports и Gitleaks1.44MB PASS.
Published source `0e4cefac8515fb45b234922e7caea8bc9ee59c38`,
[exact CI](https://github.com/BorisDruzak/storage-console/actions/runs/37191597943)
terminal SUCCESS: backend/frontend/compose/production/secrets PASS; Sonar SKIPPED.
Production browser acceptance explicitly proves invalid-cookie protected API401,
then retains both tabs/session-rejection orders/shell cleanup/TLS/backup/restore gates.
План: [Windows inventory](superpowers/plans/2026-10-04-windows-inventory.md).
Поддержка simultaneous paths принята отдельным компонентом ниже. Windows Service/state DACL,
USN/операционные providers,500k-object performance,
backpressure orchestration и живой pilot остаются открытыми.

## Wave 1 — simultaneous paths приняты; установленный runtime остаётся в работе

Один volume/FileId сохраняет несколько наблюдённых hard-link paths. Неизменные сканы
не создают новые интервалы; rename/delete одного alias сохраняет остальные.
Реальный link_count=1 является датированным sole-path доказательством; отсутствие
пути в scan не доказывает удаление. Старые пакеты сохраняют сериализацию/digest;
новый collector активируется после backend/schema0005. Длинные пути остаются Text,
точная проверка hash collision и source locks сохраняют atomicity.

Linux3.13/PostgreSQL16: backend508/20 native-only SKIP, deployment46, миграции/check,
mypy84+7/Ruff/OpenAPI PASS. Windows53/1 platform SKIP и пять настоящих HTTPS/PG cases
PASS: повторные hard-link scans/unlink-one, retained replay, rename/error freshness,
создание ссылки между metadata query и поздней публикацией старого count.
Frontend117/API/types/lint/build, installed wheel/worker/provider imports и secrets PASS.
Один независимый обзор выявил два Important; разрыв истории при позднем удалении
и небезопасный rollback подтверждены RED→GREEN, включая legacy migration rows.
Downgrade после нового path-only DELETE или при нескольких active aliases отклоняется;
нужен совместимый rollback или проверенный pre-upgrade backup.

Published source `57043e9fe19cf26cc0ef447652c027d2f79a2ddf`;
[exact CI](https://github.com/BorisDruzak/storage-console/actions/runs/37201358871) SUCCESS,
пять обязательных jobs PASS, Sonar SKIPPED. План:
[object path aliases](superpowers/plans/2026-10-04-object-path-aliases.md).
Windows Service/DACL, USN, large-tree performance/backpressure и live pilot остаются
обязательными; основной runtime этим source acceptance не обновлялся.

## Пользовательская авторизация — source acceptance и CI подтверждены

Локальный аварийный администратор и строгий LDAPS-провайдер, сессии с DB-clock expiry,
Origin/CSRF, пять ролей и защищённые read API реализованы. Русская/английская форма входа,
восстановление сессии и очистка evidence при выходе/read401 проверены. Приватный JSON
монтируется только в API; development и production Compose требуют HTTPS.

Linux3.13/PostgreSQL16: backend203, deployment45, миграции/check, mypy67/strict deploy6 PASS.
Frontend81 и shell E2E11, lint/types/build/OpenAPI, Gitleaks/ShellCheck PASS; npm audit0.
Изолированный production Compose: строгий TLS и отказ недоверенному CA, настоящий Chromium
login/reload/cross-tab logout/read401, CSRF/collector boundary, backup/restore0002→head PASS.
Один независимый полный обзор завершён; замечания по CA permissions и аудиту исправлены
и подтверждены. Подробности: [план авторизации](superpowers/plans/2026-10-04-user-auth.md).

Это не приёмка живого AD, внешних Sonar/Sentry, production DNS или переключения основного
runtime. Эти инфраструктурные проверки остаются открытыми.

Первый интеграционный push `bf8ae84b12b1aff92e394778f26c987307b91dd1` проверен на main.
CI обнаружил отсутствие keyUsage в синтетическом CA при строгой проверке Python3.13.
Генератор fixture исправлен без отключения TLS-проверок: deployment46 PASS, включая
OpenSSL -x509_strict/server-purpose/hostname и отказ неправильному hostname.
Исправление опубликовано в `8880329f43bb76ec4669d9abb9476da89fbcd05c`.
[CI 37174844328](https://github.com/BorisDruzak/storage-console/actions/runs/37174844328)
завершён успешно на этой ревизии: backend, frontend, compose-smoke, production-smoke,
secrets. Sonar пропущен; внешний Quality Gate остаётся открытым.

## Wave 0A — foundation опубликован; внешний Sonar gate не проверен

- [x] Monorepo directories: API, Web, worker, collectors, contracts, i18n, shared, migrations, deploy, tests.
- [x] Backend settings, JSON logs, health/readiness, optional Sentry hooks.
- [x] Worker heartbeat с проверкой свежести; UTC timestamptz migration.
- [x] Русский shell, 12 navigation entries, ru-RU default/en-US fallback, missing-key checks.
- [x] Frontend/backend tests и локальные lint/types/build.
- [x] Compose/Nginx и GitHub Actions definitions.
- [x] Чистый source snapshot + новая БД: PostgreSQL/API/Web/worker healthy; повторный startup сохраняет volume.
- [x] Fresh Git clone опубликованного `main` + отдельный Compose project/новый volume: все сервисы healthy.
- [x] Migration upgrade/check/downgrade/upgrade на disposable PostgreSQL.
- [x] Playwright smoke против собранного stack: 2/2; desktop/mobile screenshot QA, без page errors и горизонтального overflow.
- [x] CI green после publication: backend, frontend, Compose smoke, secrets.
- [x] Gitleaks v8.24.3: публичный source snapshot чистый; runtime .env исключён из Git.
- [ ] SonarQube Quality Gate: внешняя настройка пока отсутствует.

### Проверки 2026-10-03

- Commit: `97743e76405d9385d5f932d4b6ec9e3071b4072e`, `feat(foundation): add Compose runtime and Russian console shell`.
- [GitHub Actions run](https://github.com/BorisDruzak/storage-console/actions/runs/37145656343): success. Sonar job skipped — не считать Sonar gate успешным.
- Python 3.13 + PostgreSQL: 8/8 tests PASS; Vitest: 4/4; Playwright: 2/2; i18n lint negative-control test: PASS.
- PostgreSQL runtime: migration service exit 0; named volume сохраняется.
- Остановка worker: спустя freshness window health check возвращает failure.
- Остановка БД: `/ready` возвращает 503; после восстановления — 200.
- Сборка Web: Vite + TypeScript strict PASS; npm audit — 0 vulnerabilities.
- Independent review: исправлены обход i18n lint через JSX expressions/attributes и plain Uvicorn logs. Оба дефекта воспроизведены тестами RED→GREEN.
- Sentry before_send оставляет allowlisted metadata и структуру stack, удаляет request/user/extra/breadcrumbs/exception values; synthetic privacy test PASS. Live ingestion не проверялся.
- Локальный Python — 3.14; обязательный Python 3.13 проверен в Docker image.
- Browser plugin в списке skills отсутствует; использован repository Playwright workflow.

## Wave 0B — schema и collector contracts

2026-10-04:

- 47 required domain tables и supporting volume_aliases, ingest_batches, jobs созданы immutable migration `0002`.
- UUID/FK constraints, canonical volume/object uniqueness, timezone-aware timestamps.
- Version 1 batch envelope и typed records для девяти collector domains: bounded counts/strings/numbers,
  UTC normalization, extra-field rejection, согласованные count/time window.
- Python 3.13 + disposable PostgreSQL: 18 tests PASS; upgrade/check/downgrade/upgrade/check PASS.
- Ruff и strict mypy PASS. Independent review: исправлены storage bounds и сохранение volume identity
  в change events до разрешения object FK.
- Ingest heartbeat/inventory/changes: collector-only hashed token, source scope, atomic receipts/audit,
  concurrent duplicate replay и 409 при changed payload; canonical aliases/path history/delete.
- Request body limit 16 MiB; validation errors не возвращают входные значения.
- Дополнительный Python 3.13/PostgreSQL suite: 25 tests PASS, Ruff/mypy PASS.
- Compose smoke отдельного development project: fresh volume/migrations/API/worker/Web healthy.
- Independent review: alias reassignment и late claim после alias release воспроизведены RED→GREEN.
- [Schema/contracts CI](https://github.com/BorisDruzak/storage-console/actions/runs/37147154415): success;
  backend/frontend/Compose/secrets PASS, Sonar skipped.
- Все девять ingest domains реализованы: telemetry/events/ACL/recovery/hygiene/diagnostic-bundles
  используют ту же transactional receipt/auth/source boundary.
- Uncorrelated security evidence сохраняется в collector_events; explicit event link проверяет source.
  Collector confidence не становится автоматической attribution/health finding.
- ACL сохраняет ACE ordinal; recovery отдельно сохраняет backup/snapshot/verification/restore metadata,
  job и snapshot observation ordering проверяются независимо.
- Migration 0003 сохраняет существующие recovery rows и неизвестный legacy ACE order (NULL).
  Legacy observation timestamps backfilled из event time, без утверждения актуальной freshness.
- Public OpenAPI соответствует runtime: `python -m packages.contracts.export_openapi --check` PASS.
  CI проверяет drift. Python 3.13/PostgreSQL: 40 tests PASS; Ruff/mypy PASS, migration cycle PASS.
- Fresh Compose domain smoke: PostgreSQL/API/worker/Web healthy, `/ready` 200,
  Alembic check и worker health PASS; Gitleaks public source scan PASS.
- Read API реализован: overview, domain health, source detail/freshness и bounded volumes/shares.
  Freshness учитывает всех enabled collectors; missing/stale/future evidence и lag не маскируются.
  Persisted policy findings необходимы для domain HEALTHY; UNKNOWN coverage сохраняется при CRITICAL.
- Python 3.13/PostgreSQL: 55 tests PASS; migration cycle/check, Ruff, strict mypy (52 files),
  OpenAPI repeatability и Gitleaks PASS. Fresh Compose read smoke: все сервисы healthy.
  Independent review и четыре regression RED→GREEN: multi-collector freshness и unknown scopes.
- Concurrent worker queue реализована: atomic ingest enqueue, SKIP LOCKED/advisory lock,
  savepoint rollback, bounded retries, terminal codes и transactional completion.
  Foundation postprocess acknowledgement не выдаётся за operational policy processing.
- Python 3.13/PostgreSQL: 62 tests PASS; Ruff, strict mypy (54 files), OpenAPI/migration
  checks и Gitleaks PASS. Два worker в Compose, остановка/возобновление и restart:
  один job, один postprocess effect, одна attempt; оба worker healthy.
- Final review исправление: batch boundaries точно равны min/max records; inflated fresh
  envelope со stale records воспроизведён RED→GREEN. Ранее принятые metadata не переписываются.
- Backend foundation Tasks 1–6 опубликованы: `bee5f78f780df9249a0f29f0fd0af26894705902`;
  [CI](https://github.com/BorisDruzak/storage-console/actions/runs/37151579965) success,
  backend/frontend/Compose/secrets PASS. Sonar skipped — external acceptance gate unverified.
- Partitioning/retention и operational domain processing остаются последующим этапам спецификации.

## Далее

Wave0C Task1: typed GET client и runtime response validation из published OpenAPI реализованы.
11 transport tests (15 frontend tests total), cancellation/timeout/safe errors,
bounded pages/source filters, query deduplication, Cyrillic/UNC preservation PASS.
Generated types/schema drift и negative control PASS; npm ci/lint/types/build/audit PASS.
Live overview domain cards/source list+detail/volumes/shares подключены к typed API.
12 URL links, bounded paging, source filters и back restoration проверены; данные refetch каждые
30 секунд, errors скрывают старый successful view. Unknown/stale отделены от health и API readiness.
20 Vitest +4 Playwright PASS, actual Compose/CSP read API desktop+mobile и synthetic stale inventory
проверены. Standalone validators исправляют запрещённую CSP runtime compilation; CSP сохранён.
Полные overall/freshness summaries и остальные domain pages/locale-timezone UX остаются впереди.

Wave 0B backend/contracts/domain DB/queue реализованы; external Sonar gate не подтверждён.
Wave 0C shell/pages и Wave 0D deployment package/runbook реализованы; основной runtime
ещё не переключён, production DNS/live AD/внешние Sonar/Sentry gates не подтверждены.
Wave 1 source management реализован; collectors/runtime и Wave 2–8 operational/discovery
modules ещё не реализованы.
Полные pilot критерии v0.1 пока не выполнены.

Основная спецификация заморожена и описывает целевой продукт; этот документ отражает реализацию и evidence отдельно.
