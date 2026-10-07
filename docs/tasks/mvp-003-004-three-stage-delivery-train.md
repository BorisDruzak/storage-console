# Codex delivery train — MVP-003/004 (три этапа с независимыми проверками)

**Статус:** Implementation task / NOT ACCEPTED until all gates pass  
**Приоритет:** высокий, немедленно после MVP-PILOT-002  
**Один управляющий task, три отдельные этапа и три checkpoints.**  
**Base:** main, содержащий merged PR #7, baseline code SHA 07fbb9fdc31603a6309887684805ffb98ec5a9db.

Источники требований:
- docs/spec/storage-control-plane-v0.1.md
- docs/architecture/decisions.md
- AGENTS.md
- docs/tasks/mvp-pilot-001-live-fileserver.md
- docs/tasks/mvp-pilot-002-inventory-dashboard.md
- docs/pilot/windows-live-pilot-ru.md
- docs/implementation-status.md

## 0. Итоговая продуктовая цель

Перейти от проверенного ручного FILESERVER pilot к автоматически работающей и полезной наблюдаемости:

~~~text
Stage A: accepted Overview merged, CI + runtime pinned, issues reconciled
       GATE A
Stage B: FILESERVER Windows Service starts/restarts by itself
         heartbeat + inventory + outbox continue without PowerShell
       GATE B
Stage C: USN CREATE / WRITE / RENAME / DELETE in a bounded real scope
         durable cursor → existing HTTPS ingest → DB → Russian Activity UI
       GATE C
STOP
~~~

Это **не** full Storage Control Plane v0.1 release. Не реализовывать все последующие waves.

### Фактический стартовый контекст

- PR #7 уже **merged**, не пытаться merge повторно.
- main на момент создания этого плана имеет baseline SHA 07fbb9fdc31603a6309887684805ffb98ec5a9db.
- post-merge push CI требуется проверить до завершения Stage A.
- Issues #5 и #6 могут оставаться OPEN несмотря на real operator evidence.
- Live pilot FILESERVER уже продемонстрировал ненулевой inventory, capacity и heartbeat.
- Текущий Windows Collector запускается foreground, и его protected state удерживает эксклюзивный runtime lock. Второй run может корректно возвращать STATE_BUSY. Сервис не должен конкурировать с foreground процессом.
- Имеются: typed ChangeRecord, POST /api/v1/ingest/changes, change_events, object_path_history, durable SQLite outbox; frontend ActivityPage пока подключён к DomainLoader unavailable. Использовать существующие границы.

## 1. Общие правила выполнения

1. Выполнять **последовательно A → B → C**, а не тремя конкурентными агентами, которые правят одни файлы.
2. Перед каждым этапом записать baseline SHA, состояние CI, deployed SHA, критерии и риски.
3. Каждый этап: DESIGN/RED test → minimal implementation → GREEN tests → independent review → corrections RED→GREEN → exact-SHA CI → operator/demo acceptance → checkpoint.
4. Каждый этап — отдельные небольшие commits и отдельный PR. Не пушить непроверенный runtime напрямую в main.
5. Каждый PR содержит evidence: какие именно команды запущены, количества tests, реальные failure modes, SKIP с причиной, ссылки на CI, immutable SHA. Не записывать «всё OK» без доказательства.
6. Следующий этап **нельзя начинать**, пока предыдущий gate не подтверждён. Если gate блокируется доступом/разрешением оператора, остановиться на нём и запросить конкретное действие; не обходить gate mock-тестом.
7. Никаких долгих широких рефакторингов «на всякий случай». Исправлять только дефекты, блокирующие соответствующий gate; unrelated findings записывать в backlog.
8. Не изменять автоматически доступы на FILESERVER, ACL, auditpol, NTFS/USN Journal configuration, shares, AD, PVE, PBS, VSS, backup jobs.
9. Не требовать SSH/WinRM на FILESERVER. Команды реального pilot исполняет оператор, если заранее не предоставлен явно ограниченный доступ и отдельное разрешение.
10. Перезагрузка production FILESERVER требует **отдельного явного согласования времени с оператором**. Никогда не перезагружать его ради теста без согласования.
11. Production TLS private key, collector key, AD credentials, internal IP, SID, raw file paths, документы, SQL dumps, private runtime state не коммитить в публичный repository.
12. Использовать существующие русские i18n catalogs; default ru-RU, timezone Asia/Yekaterinburg; fallback en-US.
13. No automatic remediation. Only read-only monitoring of NTFS/USN and controlled service lifecycle when approved.
14. Если центральная VM доступна Codex по ранее разрешённому SSH, разрешено развернуть там проверенный runtime через существующий deployment runbook после backup. Если доступа нет — давать точные команды оператору; не блокировать разработку запросом root паролей.
15. Продолжать existing API auth/RBAC, TLS, CSRF, outbox, secrets scanning, Alembic and no fake health states.

### Формат gate report

Вести отдельный файл docs/acceptance/mvp-003-004-execution-ledger.md. Для каждого gate:

~~~text
GATE <A|B|C>: PASS | BLOCKED | FAIL
Source SHA:
Merged main SHA:
Exact CI run URL:
Tests summary:
Disposable acceptance:
Live/operator acceptance:
Deployed central SHA (if applicable):
Installed collector package SHA/version (if applicable):
Pending/quarantine:
Freshness:
Rollback readiness:
Operator approval/evidence:
Known remaining limits:
Next step authorized: YES | NO
~~~

Статусы LIVE проверок ставить только по действительно наблюдавшимся результатам. Не копировать production screenshots/evidence в public repo.

## 2. ЭТАП A — закрепить действующий MVP в main

### Goal

Убедиться, что уже проверенный Inventory Dashboard является воспроизводимым runtime именно main, с рабочими источниками, ёмкостью и корректной семантикой UNKNOWN.

### Required

1. Проверить PR #7 merged, ancestry head SHA, current main HEAD.
2. Проверить **post-merge push CI на exact main SHA**. Не считать PR CI заменой проверки main. Backend/frontend/windows-pilot/compose-smoke/production-smoke/secrets — PASS; Sonar: PASS, либо честно SKIPPED если external config отсутствует.
3. Прочитать текущие docs/implementation-status.md, operator acceptance предыдущих pilots и runbooks, сверить, что stage A не зависит от незамерженных изменений.
4. Если central уже развёрнут на feature SHA, выполнить safe update до main только при наличии разрешённого доступа; перед изменением — проверенная PostgreSQL backup, config backup, rollback checkpoint, проверка health и текущей версии. После — exact image SHA, migration check, HTTPS/redirect, user login, collector ingestion, Overview.
5. Повторить read-only end-to-end проверки **без изменения FILESERVER**: real source freshness, volume DATA или equivalent реальный label, capacity/free, filesystem object count >0, correct inventory TTL, unknown integrity health, timezone. Если live access отсутствует — предоставить команды operator acceptance и оставить gate BLOCKED до ответа.
6. Закрыть Issues #5 и #6 **только при наличии evidence**: CI, deployed SHA и реальный operator acceptance. Сохранить ссылки на проверку в issue comments.
7. Зафиксировать reproducible runtime baseline, к которому можно вернуться. Не удалять production DB, state, volumes, сертификаты или collector credentials.

### Self-check A — RED→GREEN

- Regression: empty data does not claim healthy.
- Inventory five+ minutes old but inside configured stale threshold stays COMPLETE.
- Heartbeat freshness and inventory quality remain independent.
- Capacity calculation uses only current measured data.
- Non-collected health domains remain UNKNOWN, regardless of capacity.
- Browser reload preserves real source, inventory and preferred timezone.
- Exact deployed SHA belongs to accepted main history.
- Post-merge CI terminal PASS for all required jobs.

### GATE A — pass only if

~~~text
[ ] PR #7 merged, main contains its commits
[ ] exact main post-merge CI terminal green
[ ] central deployed revision validated or operator-approved proof provided
[ ] real source + volume + nonzero inventory visible after reload
[ ] capacity/NTFS/overall semantics correct
[ ] Issues #5/#6 reconciled with evidence
[ ] rollback/backup evidence recorded
~~~

Если Stage A не требует code changes, это нормально. Не затягивать его новым рефакторингом.

## 3. ЭТАП B — Windows Service, idempotent installation, reboot recovery

### Goal

Убрать необходимость оставлять PowerShell открытым: Windows Service работает круглосуточно, использует прежний Collector ID и уже активированный protected state, отправляет heartbeat и inventory.

### Architecture

Реализовать тонкий Windows Service wrapper над текущим collectors.windows.runtime.Runtime; не дублировать collector logic.

Имя службы в системе: SosnadminStorageCollector (или документировать убедительную причину совместимого отклонения).

Предпочтительно:
- SCM native lifecycle with START_PENDING/RUNNING/STOP_PENDING/STOPPED and bounded stop;
- Automatic (Delayed Start);
- explicit recovery policy with bounded restarts and avoidance of restart storms;
- LocalSystem только если необходимо для защищённого state/native capture; задокументировать privileges and least-privilege plan;
- existing machine-scoped DPAPI credentials, strict TLS, private ProgramData DACL, same source/collector identity;
- existing single-owner runtime lock, no parallel foreground/service instance;
- existing durable SQLite outbox and checkpoints;
- no mandatory collector key rotation or new enrollment on upgrade/reboot;
- full install/upgrade/uninstall/rollback path that preserves credentials and undelivered events.

Не маскировать Scheduled Task под службу. Не использовать неподконтрольный сторонний service wrapper. Windows-specific dependency допустима только обоснованно и pinned.

### Operator CLI

Минимум:

~~~text
storage-collector service install --state <STATE>
storage-collector service start
storage-collector service status
storage-collector service stop
storage-collector service uninstall
~~~

Названия могут быть иными при сохранении поведения/документации.

Requirements:
- install повторно не создаёт дубль;
- start повторно не создаёт второй runtime;
- stop ведёт к bounded cleanup, outbox/state не удаляется;
- status читает SCM state даже когда protected runtime lock удерживается;
- понятное сообщение «уже работает» вместо неоднозначной ошибки STATE_BUSY для install/start;
- foreground run при работающей service корректно отказывает без повреждения state;
- optional explicit migration/handover: оператор останавливает foreground Ctrl+C → дожидается shutdown → запускает службу; не делать taskkill всех python.exe и не удалять runtime.lock;
- uninstall останавливает и удаляет только service registration/installed binaries, не удаляет local state/outbox/token без отдельного explicit purge (purge out of scope).

### Self-check B — RED→GREEN (обязательные негативные случаи)

1. Initial installed wheel/service exists after clean installation.
2. Service starts as configured security principal, reads machine DPAPI config and trusted CA, sends real HTTPS heartbeat.
3. Service stops cleanly; no orphan native capture subprocess; bounded SCM timeout.
4. Second start/second install idempotent, no competing processes, no queue corruption.
5. Active foreground and service cannot run concurrently; friendly deterministic status.
6. Operator can inspect service status while running without STATE_BUSY (SCM-read, not grabbing protected state).
7. Stop/start retains collector UUID, credential binding, inventory checkpoint, heartbeat sequence and queued batches.
8. Network outage: queue retains items; after link recovery backlog replays exactly once, pending→0, quarantine0.
9. Revoked/rotated key: fail closed; do not silently clear auth suspension, do not leak token.
10. Crash/service process death: recovery policy restarts once within bounded time without losing state or creating restart storm.
11. Current Python wheel installs in clean Windows environment without repository checkout.
12. Native Windows subprocess and LocalSystem behavior tested on suitable disposable Windows host/VM, not only Linux mocks.
13. Disabled service auto-start remains disabled, and uninstall does not delete the evidence store.
14. No secret in argv, Event Log, stdout or git.

### Automated verification B

- Windows unit + integration tests with installed wheel and SCM.
- Real HTTPS/PostgreSQL collector acceptance on isolated environment.
- Existing Linux backend/frontend/compose/production/secrets gates remain green.
- Run CI on PR SHA and exact merged main SHA.
- Stage B independent code review identifies important regressions, reproduces them RED then verifies fixes GREEN; do not create unbounded test matrix.

### Operator acceptance B on FILESERVER

Only after explicit approval:

1. Record current foreground PID/runtime, pending count and recent heartbeat from Web Console.
2. Ctrl+C foreground, wait bounded shutdown; no killing unrelated processes.
3. Install/start service with operator-approved installer.
4. Verify Get-Service / sc query, running identity, service configuration and automatic delayed start.
5. Watch 3 successive heartbeats and source freshness HEALTHY; verify inventory remains visible.
6. Stop/restart service; verify fresh heartbeat, same collector identity, pending=0 and quarantine=0.
7. Reboot FILESERVER **only in an explicitly approved maintenance window**. Record before/after identity/cursor and confirmation from console. If approval missing, GATE B must remain BLOCKED even if disposable reboot tests passed.
8. After boot, service runs without interactive login, source returns HEALTHY in a justified configured window, no manual CLI.
9. Verify no unexpected impact on FILESERVER/SMB/CPU, no ACL/audit policy changes.
10. Keep rollback path to previous wheel + foreground run; demonstrate it in disposable environment, not by breaking live data.

### GATE B

~~~text
[ ] PR for Windows Service merged, CI on merge SHA success
[ ] native installed wheel + SCM tests pass
[ ] protected DPAPI/outbox/CA usable by service
[ ] install/start/status/stop/uninstall idempotence verified
[ ] foreground→service controlled handover verified
[ ] current heartbeat + inventory preserved
[ ] outage/retry and restart recovery verified
[ ] explicit operator approval for FILESERVER reboot recorded
[ ] real reboot acceptance PASS, service runs without login
[ ] no unauthorized infrastructure mutations
[ ] rollback + operator runbook present
~~~

If real reboot has not been approved/completed: code may be ready, but GATE B = BLOCKED, and Stage C live rollout is not authorized.

## 4. ЭТАП C — USN change stream → Activity UI

### Goal

Сделать первый реальный read-only журнал активности на одном пилотном локальном scope:

~~~text
создали файл → Activity: Создание
записали файл → Activity: Изменение
переименовали файл/директорию → Activity: Было → Стало
удалили файл → Activity: Удаление
~~~

Не реализовывать user attribution на этом этапе. NTFS USN **не содержит достоверной личности пользователя**.

### Existing components to reuse

- collectors/windows/native.py: canonical volume identity/FileId/metadata scope.
- collectors/common/outbox.py: atomic checkpoint+batch durable queue.
- collectors/common/delivery.py + transport.py: strict HTTPS/replay.
- packages/contracts/changes.py: ChangeRecord, machine types CREATE/WRITE/RENAME/DELETE/METADATA_CHANGE/SECURITY_CHANGE.
- apps/api/ingest.py: POST /api/v1/ingest/changes.
- packages/shared/ingest/core.py: change() and object/path history.
- packages/shared/models/activity.py: change_events.
- apps/web/src/pages/ActivityPage.tsx.
- apps/web/src/domains/models.ts: currently unavailable domainReader — replace only Activity reader, keep other modules untouched.

### USN native reader

1. Read NTFS USN Journal through supported native read-only Win32 FSCTL APIs. Never create/resize/delete the journal.
2. Parse required supported USN_RECORD versions with strict structure size/offset bounds; unsupported versions gracefully produce a machine-coded source status. No OCR, locale-specific parsing or naive string comparison.
3. Read JournalID, FirstUSN/NextUSN, FileId, ParentFileId, USN, ReasonHex bitmask, UTC event time and UTF-16 name. Preserve raw bitmask source identifier in normalized evidence.
4. Use canonical volume identity, not B:/D: drive letter. Correlate with existing filesystem object identity (volume_id, FileId).
5. **Read only volumes containing explicitly configured roots.** USN itself is volume-wide; do not persist/upload unrelated paths outside configured scope. Scope membership through parent/FileId ancestry. Renames of ancestor directories and moves in/out of scope need explicit tests; unknown paths are UNKNOWN, not fabricated.
6. Path cache persists in local protected state. Do not rely on queryfilenamebyid after deletion. On delete, last-known path or null with explicit unknown — never invent path.
7. One RENAME_OLD + RENAME_NEW pair yields one logical RENAME with old/new relative paths. Handle same FileId, parent changes, rename of ancestor, partial pair and restart boundary.
8. Coalesce DATA overwrite/extend/truncation and CLOSE noise into bounded logical WRITE events; preserve event provenance and deterministic ordering. Metadata/security reason classes handled only when reliably identifiable, not guessed.
9. Store JournalID+next cursor, cache mutations and durable outgoing events transactionally where feasible; no event loss between acknowledged cursor advancement and enqueue. After crash re-reading may duplicate raw journal but must not duplicate logical DB events.
10. Same replay batch remains byte-identical across restart. Do not create new BatchID for re-send.
11. Detect JournalID change, cursor below FirstUSN (wrap/truncation), unsupported record, access denial, volume loss, corrupted checkpoint. Report CONTINUITY_GAP/UNKNOWN and require documented rebaseline; **never silently claim complete history**.
12. Bounded memory/CPU, batch size/max bytes, throttle/backpressure, max local outbox limits. Keep independent heartbeat and periodic inventory functional even during USN burst.
13. No reading document content; no SACL/auditpol change; no SMB, ACL, VSS, PVE/PBS mutation.

### Event identity and data model

Use source_event_id stable from canonical journal identity/USN and source record identity (not process runtime time). Preserve reason_mask.

Prevent duplicate logical events after:
- lost HTTPS ACK;
- crash before/after enqueue;
- service restart;
- duplicate journal record read;
- duplicate client delivery.

DB migration/indexes only if genuinely needed for above; no broad schema redesign. Document any non-backward compatible state/migration and safe rollback plan.

### Backend read API

Implement authenticated **GET /api/v1/activity** (or consistent existing /api/v1 equivalent) with:
- bounded limit and offset/cursor-based pagination;
- source_id;
- event_type;
- optional bounded time window;
- newest-first deterministic sort (occurred_at, id);
- stable object identity, event time, event type, old/new paths, reason/provenance, nullable actor/client/confidence;
- explicit data quality/freshness, no pretending stream continuity if journal gap;
- safe/typed JSON, no content body or collector secret;
- existing session RBAC and no-store/evidence freshness semantics;
- adequate source/time filters and indexes without unbounded full scans.

Do not widen all domain APIs; only Activity.

### Russian UI

Replace only ActivityDomainLoader placeholder with a typed real API client:
- Create/Write/Rename/Delete visible with Russian translations;
- Before → After for rename;
- source filter, type filter, empty/loading/error/stale;
- event time in user's business timezone;
- Actor/User and Client remain «Не определено», because USN cannot attribute users;
- provenance «NTFS USN» or equivalent explicit label;
- display path relative to configured source/scope if safely available;
- no fake confidence %, no invented user;
- proper Cyrillic and long paths;
- Activity UI auto-refresh/polling at documented reasonable cadence; no SSE/WebSocket platform rewrite unless strictly necessary.

Remaining domains remain unchanged/UNKNOWN.

### Controlled scenario C

ONLY in a dedicated disposable test directory created by operator **inside the already-approved monitored root**:

1. Create test file.
2. Modify its content once.
3. Rename test file.
4. Rename its parent test directory, verify descendants can be resolved or explicitly marked unresolved.
5. Delete test file.
6. Refresh Activity page and verify CREATE/WRITE/RENAME/DELETE with stable FileId and accurate old/new paths.
7. Restart service and repeat a small controlled sequence; verify no duplicates or missing events.
8. Simulate brief HTTPS loss; restore and verify outbox replay and sequence.
9. Verify no events from a sibling directory outside allowed scope are uploaded.
10. Cleanup only the dedicated test directory with operator consent. Never touch real department files.

Target observable latency: normal local creation → visible in Activity within 60 seconds including Web polling; capture measured time, don't invent a result.

### Self-check C — RED→GREEN

- Reason bitmask fixtures, multiple USN record versions and malformed buffers.
- Create/write/rename/delete controlled NTFS tree.
- Two rename records collapse into one.
- Ancestor rename; FileId remains stable.
- Delete uses last-known path after native resolution fails.
- Unknown path does not leak out-of-scope content.
- UTF-16 Cyrillic, UNC-like names as literal data, long paths.
- Restart crash with cursor/outbox transaction safety.
- Journal reset/wrap: explicit continuity gap state, not fake green.
- Transport lost ACK/idempotency.
- No actor inference from USN.
- Web real API, filters, sorting, correct source timezone, reload and no stale fake events.
- Existing inventory and heartbeat continue even with USN burst.
- Security scan verifies no production contents/paths/keys committed.

### GATE C

~~~text
[ ] USN collector implemented only for approved scope
[ ] journal never enabled/resized/deleted by code
[ ] correct CREATE/WRITE/RENAME/DELETE on synthetic native NTFS test
[ ] stable FileId / canonical volume / path cache
[ ] cursor + event/outbox durable and restart-safe
[ ] journal wrap/reset surfaces gap
[ ] no out-of-scope data persisted or sent
[ ] existing HTTPS ingest/PG path reused; replay idempotent
[ ] GET /api/v1/activity authenticated, paginated, bounded
[ ] Russian Activity UI renders actual events without fake actor
[ ] test scenario create→modify→rename→delete visible <= 60 seconds (measured)
[ ] foreground/service restart + temporary network outage acceptance
[ ] existing heartbeat/inventory/Overview not regressed
[ ] exact-SHA CI successful, Sonar truthfully reported
[ ] operator verified controlled live folder scenario
[ ] rollback and privacy requirements satisfied
~~~

Stop if any data continuity or path-scope integrity failure remains.

## 5. Пакет проверок и release gates для каждого этапа

Required CI: backend, frontend, windows-pilot, compose-smoke, production-smoke, secrets. Any newly introduced service/USN Windows-native checks must run on Windows, not only via skips on Linux.

Sonar:
- if configured: must be a real Quality Gate PASS;
- if unconfigured: explicitly report SKIPPED, never claim it passed;
- do not disable existing quality checks for speed.

Existing tests must not be removed. Cover missing negative behavior with targeted tests, not inflated arbitrary test counts.

Publish **each stage** as:
- separate PR with tests and docs;
- exact source SHA;
- exact CI URL after merge;
- updated docs/implementation-status.md;
- updated docs/acceptance/mvp-003-004-execution-ledger.md;
- sanitized operator instructions;
- rollback procedure.

Automated green != live accepted. Do not mark a stage PASS if only a disposable environment was tested.

## 6. Hard STOP / non-goals after Stage C

After GATE C PASS, **stop all development**, report to operator. Do not silently continue:
- 4663/5145 user attribution;
- SMB/DFS/VSS/FSRM/ACL;
- PVE/PBS/ZFS;
- diagnostics or Data Discovery;
- large/full file content scan;
- remote mutations;
- fleet-wide mass rollout;
- auto-update and auto-remediation.

Allowed final report structure:

~~~text
Stage A — PASS / BLOCKED / FAIL
SHA / CI / deployed SHA / observed Overview / Issues

Stage B — PASS / BLOCKED / FAIL
SHA / CI / service install+reboot evidence / queue and auth / rollback

Stage C — PASS / BLOCKED / FAIL
SHA / CI / live USN event proof / no duplicates / latency / rollback

Open gates and specific operator actions required:
...

Further work: separate issue, NOT executed.
~~~

No generic «100% production ready». This is a bounded observable MVP train with verified intermediate results.
