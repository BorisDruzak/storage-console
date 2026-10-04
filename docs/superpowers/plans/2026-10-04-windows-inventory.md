# Windows heartbeat and inventory implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, task by task,
> with one fresh whole-component reviewer at the end. Full canonical scope/main/
> inline already authorized; no additional method-approval loop.

**Goal:** Native read-only Windows metadata and heartbeat capture into durable delivery.
**Architecture:** Typed observation port; pinned Win32 metadata handles and streaming
enumeration; bounded producer uses existing contracts/outbox and independent heartbeat.
**Tech Stack:** Python3.13 ctypes/os, pinned Pydantic2.13.5, PostgreSQL16 acceptance.
**Spec:** `docs/superpowers/specs/2026-10-04-windows-inventory.md`.

## Global constraints

- No new dependencies, file contents, remote paths, audit-policy changes or privilege enablement.
- 1..32 local non-overlapping drive-rooted directories <=32700 chars; depth<=64.
- Metadata access0x80/share0x3/open3/flags0x02200000; handle final path uses volume GUID.
- Existing version1 contracts;256-record/8MiB chunks default, configurable1..512 records.
- Retain queued batches/checkpoints; restart full scan, no deletion/snapshot/USN claims.
- Private state/service ACL and500k-object performance/live pilot remain gates.
- Exact main CI, one whole-component review; no per-task agents.

## Review focus

1. Concurrent ancestor replacement and mount/drive alias changes must not enumerate outside scope.
2. Open or query failure and generator cancellation must release every owned handle/iterator.
3. Hard links/renames/long Unicode names must preserve volume/FileId identity and actual paths.
4. Queue pressure and process restart must preserve previous batches and not claim scan completion.
5. Denied/reparse/disappearing entries must be explicit partial evidence without path/error leaks.

## Task 1 — Native metadata provider

Files: create `collectors/windows/{__init__,inventory,native}.py`,
`tests/backend/test_windows_inventory.py`, `tests/backend/test_windows_inventory_native.py`.
Interfaces: `CaptureError(code)` fixed-code; `Observation(record=None,error_code=None)`
record repr hidden; `Scope(roots:tuple[str,...]).fingerprint`; `NativeInventory.scan(scope)`
returns Iterator[Observation]. Native API private handle helpers support injected failures.

- [x] RED scope validation/privacy/platform and actual native temp-tree volume/object identity,
  rename/parent/size, junction ancestor/child exclusion and cleanup tests.
- [x] Implement lazy WinDLL, explicit signatures/structures, same-handle metadata,
  pinned ancestor containment and bounded streaming traversal.
- [x] RED concurrent replacement, query failure, iterator close/depth/Unicode tests;
  implement fixed issue handling, no raw OS messages/paths.
- [x] Windows native + portable cases, Linux import/types/Ruff; inspect complete diff;
  commit `feat(collectors): capture native Windows inventory metadata`.

Task1 evidence: actual Windows26 passed/1 unsupported-platform skip; Linux3.13
portable18 passed/9 native-only skips. Strict mypy3 source files and Ruff passed.
Final-path alias replacement regression failed before the exact final-path guard,
then passed. Actual junction exclusion, pinned ancestors, handle cleanup, hard-link
identity, long/Unicode paths and depth-limit tests passed. These accept metadata
capture only; durable producer, actual ingest and whole-component review follow.

## Task 2 — Bounded durable producer

Files: create `collectors/windows/producer.py`, `tests/backend/test_windows_producer.py`.
Interfaces: `capture_inventory(box,scope,observations,*,max_records=256,clock,stopped)`
->CaptureReport; `capture_heartbeat(box,*,error_code=None,clock)` ->str batch_id.
Consumes Scope/Observation fromTask1 and Outbox.enqueue/checkpoint; version0.1.0.

- [x] RED actual outbox/contracts/checkpoint/chunk limit/restart/scope mismatch/FIFO,
  cancellation and pressure tests; heartbeat independent stream/no invented cursor/lag.
- [x] Implement bounded builder, explicit partial report, scope check before iteration,
  transactional enqueue/checkpoint, close input generator on every exit.
- [x] Whole producer/native suite, Linux full tests/migrations/types/Ruff/OpenAPI;
  commit `feat(collectors): enqueue Windows inventory and heartbeat`.

Task2 evidence: Windows45 passed/1 platform skip. Linux3.13/PostgreSQL16 full
backend456 passed/10 native-only skips, deployment46 passed, migration round trips
and check passed, mypy82 source/7 deployment-helper files, Ruff/OpenAPI passed.
Installed wheel/isolated worker/native-provider imports passed; public-source
Gitleaks1.41MB found no leaks. Cleanup completion, callback error privacy, scope
overlap/case/depth and complete volume mount aliases were reproduced before fixes.
Capture restarts a new scan UUID and preserves old FIFO batches; this does not
accept live Windows Service/DACL/USN or pilot performance. Real ingest/review remainTask3.

## Task 3 — Real ingest acceptance and final review

Files: create `tests/backend/test_windows_inventory_integration.py`; update
Windows README/task index/status/this plan.

- [x] Real HTTPS/PostgreSQL fake-provider cross-platform and actual native Windows
  metadata/heartbeat accepted with retained replay and one batch effect.
- [ ] Final Linux3.13 full/backend/deployment/migrations/types/Ruff/OpenAPI, Windows
  native acceptance, secrets/package checks; one fresh whole-component review.
- [ ] Important/Critical fixes in one RED→GREEN pass; main publication/exact terminal CI;
  record remaining Service/DACL/USN/providers/performance/live pilot gates honestly.

Task3 current evidence: actual Windows HTTPS/PostgreSQL2 cases passed; lost local ACK
replays accepted duplicate with one effect, native rename preserves FileId/object ID
and adds exactly one path-history observation. Linux real HTTPS/PostgreSQL fake-provider
case passed, native case skipped. Full Linux3.13/PG16 backend457 passed/13 native-only
skips, deployment46 passed, migrations roundtrip/check/mypy82+7/Ruff/OpenAPI passed.
Windows provider/producer47 passed/1 platform skip. Mapped-drive regression failed
before local-GUID pre-open resolution, then passed with no metadata open; every
capture handle now uses GUID namespace. Whole-component review/fixes/exact CI remain.
