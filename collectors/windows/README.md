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
CLI, scheduler и установленная SCM-служба пока остаются следующими задачами.

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
