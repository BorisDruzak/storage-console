# Windows heartbeat and metadata inventory

Approved canonical scope: §8/26/30/31/34/35 of storage-control-plane-v0.1.
Main publication and inline execution remain authorized. This component advances
Wave1; Windows Service installation, USN and the full pilot remain subsequent gates.

## Outcome and boundaries

Capture heartbeat, volume and file/directory metadata for explicitly configured
local Windows roots through existing version1 contracts and the accepted durable
outbox/strict HTTPS delivery. No file contents, audit-policy changes, privilege
enablement, remediation, remote paths or automatic filesystem discovery.
Windows >=Windows10/Server2016 and Python>=3.13; no additional dependency.

Native ctypes is chosen over PowerShell subprocess export (locale/streaming/error
boundaries) and pywin32 (additional installation/dependency). All functions have
explicit Unicode signatures, HANDLE-sized results and owned handle cleanup.

## Native capture

Accept 1..32 drive-rooted local directory roots, each <=32700 characters.
Each root has <=64 ancestor components, bounding simultaneously pinned handles.
Reject UNC/device prefixes, relative paths, dot components, alternate streams, control
characters and overlapping roots. Configured paths and observations are private
runtime data and never belong in public examples/logs/error messages.

Open with FILE_READ_ATTRIBUTES only, OPEN_EXISTING,
FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT and READ|WRITE sharing.
Omit DELETE sharing to pin every ancestor while enumerating. Open each ancestor
from the drive root, reject reparse/non-directory, and resolve each handle using
GetFinalPathNameByHandleW/VOLUME_NAME_GUID. Continue using this stable volume GUID
path, checking each child's actual parent/volume. Do not enumerate an alias whose
parent changed. This deliberately may report sharing violations during concurrent
rename, rather than follow a replacement outside the configured scope.

GetFileInformationByHandleEx FileIdInfo/BasicInfo/StandardInfo from the same handle:
128-bit file ID, directory/type, size and attributes. GetVolumeInformationByHandleW
and GetDiskFreeSpaceExW supply filesystem/label/capacity; GetVolumePathNamesForVolumeNameW
supplies the complete mount-alias list (<=128 names/65536 WCHAR buffer), since ingest
ends aliases omitted from a later volume observation. Stable volume GUID is
volume identity; file IDs are lowercase 32-hex strings. Relative paths are relative
to the volume, so two configured roots cannot alias object paths. Parent file ID
comes from the pinned parent. No synthetic path-derived IDs or filesystem fallback.

Depth-first streaming scandir; <=64 directory levels, with no whole-directory sort
or in-memory frontier. Reparse children, access denial, disappearance, sharing
violation and excessive depth produce fixed issue codes. Root failure does not
fabricate volume/object evidence. Close scandir and handles on exhaustion,
cancellation, consumer close and exceptions. Unsupported platforms fail explicitly
without loading Windows libraries at import time.

## Producer durability and limits

Observation(record|fixed issue) feeds capture_inventory. Observations' repr hides
metadata. CaptureReport exposes counts, unique fixed codes and completed only.
Default chunks256 records, <=8MiB including envelope reserve, configurable1..512
records. Existing outbox remains <=16MiB/body,1024 batches/512MiB retained.
Each enqueue atomically writes a checkpoint (scope fingerprint, scan UUID,
sequence, completed) and immutable batch. Same inventory stream preserves replay
order; heartbeat uses an independent stream. Stop on queue pressure, preserving
previous batches and checkpoint. Cancellation closes input iterators and returns
incomplete; no secrets/path exception text escapes.

Filesystem enumeration cursors are volatile. Restart a new scan at the configured
roots, preserving old retained batches in FIFO order. Repeated inventory is a new
observation and uses a new scan UUID. Do not persist an opaque enumeration handle,
claim restart resumes a directory position, infer deletions, or call this a snapshot.
The scope fingerprint preserves directory case and must match durable state before
any native enumeration. Windows directories can be case-sensitive; case-only config
changes conservatively require an explicit state reset.
Incomplete/issue scans never set completed=true. Heartbeat reports known fixed
capture failures; cursor/lag remain absent until actual USN continuity exists.

Windows state/service DACL installation remains mandatory before live deployment.
No pilot host/root is guessed. Large-tree CPU/memory/throughput and interrupted
scan restart cost must be measured in pilot before production acceptance.

## Acceptance

- Portable validation/producer tests: contracts, scope/restart/FIFO, atomic checkpoint,
  pressure, byte/count limits, cancellation, partial failures and no secret repr.
- Native temporary Windows tree: stable IDs through rename, file size/type/parents,
  zero data-read access, ancestors pinned, junction/reparse exclusion, long/Unicode
  paths, depth failure and cleanup. No install or changes to host policies.
- Actual strict HTTPS/PostgreSQL inventory+heartbeat ingest and retained replay.
- Linux3.13 full backend/deployment/migrations/Ruff/mypy/OpenAPI; native Windows tests;
  one fresh whole-component review and RED→GREEN fixes; exact terminal required CI.
- No source test substitutes for Windows Service, USN, live AD or full pilot gates.

References: [Win32 handle metadata](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex),
[volume metadata](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getvolumeinformationbyhandlew),
[final handle path](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew).
