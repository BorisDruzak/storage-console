# Windows Collector

Реализованы native metadata provider и bounded producer для Wave1. Они собирают
heartbeat, identity/filesystem/capacity/mount aliases томов и metadata файлов/каталогов
в explicitly configured local roots. Данные идут через существующий
[общий outbox/HTTPS delivery](../common/README.md); API contracts version1 не меняются.

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

Файлы с несколькими hard links дают `MULTIPLE_LINKS` и partial capture: текущий
ingest представляет один current path на FileId. Поддержка одновременных путей
остаётся обязательной задачей; такие файлы пока не публикуются как ложные rename.
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

[План и проверки](../../docs/superpowers/plans/2026-10-04-windows-inventory.md):
native temporary-tree tests и четыре Windows HTTPS/PostgreSQL replay/rename/error/
hard-link partial cases прошли; Linux458/backend (17 native-only SKIP)+46 deployment/
migrations/types/Ruff/OpenAPI прошёл. Один независимый обзор выявил три Important;
исправления проверены RED→GREEN. Публикация и exact CI ещё выполняются.

Windows Service/state DACL, USN continuity, SMB/DFS/FSRM/VSS/ACL/telemetry,
500k-object performance и live pilot остаются отдельными обязательными этапами.
