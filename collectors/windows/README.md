# Windows Collector

Защищённая конфигурация runtime реализована библиотечно: `ProtectedState` создаёт
локальный state с владельцем Administrators и DACL только SYSTEM/Administrators,
удерживает ancestor handles и эксклюзивный lock. Credentials шифруются machine DPAPI;
нельзя размещать ciphertext в общем доступе. `configuration.activate(...)` явно
создаёт новую credential version, затем атомарно заменяет private config до128KiB.
CA сохраняется отдельно для каждой version. `configuration.load(...)` проверяет
binding в SQLite schema3 и не снимает сохранённый auth suspension при перезапуске.
Сбой между активацией БД и заменой config требует повторной настройки оператором.
Изменение identity/scope отклоняется; backlog никогда не удаляется автоматически.
Операторский CLI установлен через wheel: `storage-collector activate`, `status`,
`inventory-once`, `run`. Первый live pilot выполняется по
[русскому runbook](../../docs/pilot/windows-live-pilot-ru.md).
Установленная SCM-служба остаётся вне MVP-PILOT-001.

Issue #8 / Stage B добавляет native SCM host над тем же `Runtime` и operator
команды `service install/start/status/stop/uninstall`. Protected state/UUID/DPAPI,
CA, credential binding и outbox сохраняются; service status читает SCM без
runtime lock. LocalSystem, delayed start и один bounded crash restart описаны в
[service runbook](../../docs/pilot/windows-service-ru.md).
Gate/CI/live acceptance фиксируются отдельно в
[execution ledger](../../docs/acceptance/mvp-003-004-execution-ledger.md).
Это не разрешение live handover или reboot и не начало Stage C.

Реализованы native metadata provider и bounded producer для Wave1. Они собирают
heartbeat, identity/filesystem/capacity/mount aliases томов и metadata файлов/каталогов
в explicitly configured local roots. Данные идут через существующий
[общий outbox/HTTPS delivery](../common/README.md); `schema_version=1` сохраняется.
Файловые записи содержат положительный `link_count`; старые пакеты без него сохраняют
прежнюю сериализацию и digest. Перед запуском нового capture обновите backend и
примените migration `0005`: старый strict endpoint отвергает новое поле.

```python
from collectors.windows.inventory import Scope
from collectors.windows.native import NativeInventory
from collectors.windows.producer import capture_heartbeat, capture_inventory

# box is an existing private Outbox with the provisioned immutable collector UUID.
scope = Scope(("D:\\SyntheticData",))
report = capture_inventory(box, scope, NativeInventory().scan(scope))
capture_heartbeat(box, error_code=report.errors[0] if report.errors else None)
```

Provider использует Unicode Win32 API, metadata-only access, volume GUID и128-bit
FileId. Перед первым open проверяет local drive и переводит root в GUID path;
mapped network drives отклоняются. Reparse points не обходятся. Ancestor handles
удерживаются без DELETE sharing; это может временно мешать rename/delete директории
во время scan. Это не запрещает reparse mutation: защита основана на NtCreateFile
относительно parent handle и handle-based directory enumeration, без повторного
разрешения pathname. File contents, audit policy и privileges не меняются.

Файлы с несколькими hard links сохраняют один FileId и несколько наблюдённых путей.
Повторные сканы не открывают новые интервалы для неизменённых ссылок. Реальный
`link_count=1` закрывает более старые другие aliases; отсутствие пути в scan не
считается удалением. Path-only DELETE закрывает конкретный alias; удаление объекта
целиком требует отдельного события без пути. Другая ссылка может находиться вне scope.
`MULTIPLE_LINKS` остаётся допустимым кодом для ранее сохранённых ошибок/checkpoints.
Heartbeat с ошибкой сбора даёт source freshness `UNKNOWN/COLLECTION_ERROR`;
следующий heartbeat без ошибки снимает этот признак.

Scope:1..32 local roots, <=64 ancestor components, <=64 уровней обхода ниже root;
пересекающиеся roots отклоняются. Fingerprint сохраняет регистр компонентов пути:
Windows поддерживает case-sensitive directories. При смене scope сначала доставьте/
разберите retained batches, затем явно создайте новый private state; не удаляйте
старый outbox с недоставленными данными.

Chunks:256 records/8MiB по умолчанию; queue pressure/cancellation останавливают scan,
сохраняя committed batches/checkpoints. `CaptureReport.completed=False` и fixed
codes сообщают partial/error; не логируйте payload/paths. Heartbeat не придумывает
USN cursor/lag. Delivery/scheduling должны учитывать backpressure: последовательный
полный scan большого дерева до начала доставки может заполнить ограниченный outbox.

После process restart новый scan начинается с roots, а старые batches остаются FIFO.
Enumeration cursor не durable; scan не является snapshot или deletion proof.
Живой scheduler/Windows Service и interrupted large-tree throughput ещё не приняты.

[Первоначальный план и проверки](../../docs/superpowers/plans/2026-10-04-windows-inventory.md):
native temporary-tree tests и четыре Windows HTTPS/PostgreSQL replay/rename/error/
hard-link partial cases прошли; Linux458/backend (17 native-only SKIP)+46 deployment/
migrations/types/Ruff/OpenAPI прошёл. Один независимый обзор выявил три Important;
исправления проверены RED→GREEN. Source `0e4cefac8515fb45b234922e7caea8bc9ee59c38`
опубликован; [exact CI](https://github.com/BorisDruzak/storage-console/actions/runs/37191597943)
terminal SUCCESS, все пять обязательных jobs PASS. Sonar SKIPPED остаётся внешним gate.

[Поддержка path aliases](../../docs/superpowers/plans/2026-10-04-object-path-aliases.md):
Linux508 backend (20 native-only SKIP)/46 deployment, migrations/types84+7/Ruff/OpenAPI
прошли; Windows53 native/provider/producer tests и пять реальных HTTPS/PostgreSQL
cases прошли, включая repeated hard links/unlink-one и delayed link-count race.
Frontend117/APIcheck/types/lint/build, installed wheel/worker и public secrets scan
прошли. Один независимый обзор выявил два Important; история через позднее удаление
и небезопасный downgrade исправлены с PostgreSQL RED→GREEN и финальным полным прогоном.
Исходный код `57043e9fe19cf26cc0ef447652c027d2f79a2ddf` опубликован;
[exact CI](https://github.com/BorisDruzak/storage-console/actions/runs/37201358871) SUCCESS, пять обязательных jobs PASS.
Sonar SKIPPED остаётся внешним gate. Downgrade после новых path-only DELETE или
при нескольких активных aliases требует совместимого плана rollback.

Windows Service/state DACL, USN continuity, SMB/DFS/FSRM/VSS/ACL/telemetry,
500k-object performance и live pilot остаются отдельными обязательными этапами.

## Stage C: read-only USN activation and rebaseline

Implementation and acceptance are tracked in
[Issue #8 ledger](../../docs/acceptance/mvp-003-004-execution-ledger.md).
The following operator commands belong to the Stage C candidate; Gate C is not
accepted until the ledger records exact CI and controlled live acceptance.

- Stop the collector service through its existing lifecycle and confirm STOPPED.
  Back up its protected state using the existing offline backup procedure.
- Run `storage-collector usn-enable --state <protected-state>` and start the service.
  A protected, scope-bound sidecar enables the feature without changing enrollment
  credentials or the existing config. An absent sidecar keeps the accepted B mode.
- Initial ancestry enumeration is fenced with QUERY/READ of the already-existing
  journal. If a monitored object/parent changes during enumeration, no initial
  cache is committed: coverage stays UNKNOWN and a subsequent bounded pass retries.
- Successful passes prove coverage through their initial queried target, not
  complete historical coverage. Eight transitions of at most 256 raw records bound
  each pass; remaining backlog is USN_LAG. Polling runs every two seconds.
  Heartbeat/inventory/delivery remain independent. When USN is enabled, heartbeat
  publication is bounded to five seconds without rewriting the configured interval;
  disabling USN restores the configured cadence. A proof ages after 15 seconds;
  Activity cannot retain COMPLETE beyond that proof's absolute expiry. A stalled
  established worker is stopped after 30 seconds; initial bootstrap has 600 seconds.
- Gap, malformed/unsupported read, access denial or volume loss after an established
  baseline remains latched UNKNOWN. After investigating, explicitly stop the
  service and back up state, then run `storage-collector usn-rebaseline --state
  <protected-state>`. This clears only the collector's USN checkpoints, keeps
  queued event bytes/receipts/credentials, and starts a new observation window on
  restart. Missing history is not recovered. It does not change OS journal settings.
- For rollback, stop the service, run `storage-collector usn-disable --state
  <protected-state>`, retain the state backup and restore the accepted B package
  through its existing runbook. The sidecar and checkpoint additions do not modify
  the old config or SQLite table schema. Pending C changes with `path_quality` or
  a missing RENAME side are incompatible with the B contract: preserve their exact
  bytes in the C state backup and drain them through the C ingestion contract before
  switching delivery to B. A restored older state starts an explicitly incomplete
  observation window; it must not silently discard pending C events. A central
  rollback additionally requires a compatible database snapshot or retained C
  ingestion/read support. Index downgrade alone does not provide that compatibility.
  Actual package rollback acceptance is still required before Gate C PASS.

Activity polls every five seconds, uses source/type filters and bounded pages,
retains nullable unknown paths, and shows NTFS USN provenance. It never infers
actor/client/confidence from journal records. Total protected USN cache is capped
at 250,000 checkpoint entries and 256 MiB encoded data across volumes; individual
scope state also limits object count. Capacity rejects the complete transition
without advancing its cursor or consuming heartbeat reserve. No journal create,
resize/delete operation, content capture, audit/ACL/SMB mutation or reboot is used.

Pending WRITE retains its first data-record time and parent FileId. If ancestry
changes before CLOSE and its historical path cannot be proven, the event carries
an explicitly unknown path. Outside activity redacts cached descendants without
discarding pending in-scope WRITE or RENAME evidence; paired re-entry restores only
proven ancestry. Outside names are neither cached nor included in event payloads.
