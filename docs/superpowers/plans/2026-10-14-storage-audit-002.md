# Bounded department audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add one operator-approved root and read-only directory enrichment while preserving history and bounded memory.

**Architecture:** Retain one existing USN collector and its durable outbox. Add explicit scope transition, bounded asynchronous readiness, resource admission and additive directory observations; enrich sensitive read APIs without changing original evidence.

**Tech Stack:** Python 3.13, native Win32/.NET read-only directory access, FastAPI/Pydantic2, SQLite, PostgreSQL16/SQLAlchemy2/Alembic, React/TypeScript/react-i18next, Docker Compose.

**Spec:** docs/superpowers/specs/2026-10-14-storage-audit-002.md. Production parameters are only in the approved private department-rollout-design.md.

## Global Constraints

- Preserve original STORAGE-AUDIT-001 PASS and USN-SOAK FAIL; no inferred historical completeness.
- No production paths, identities, credentials or raw evidence in public Git.
- Preserve existing USN roots/cursors/queue/credentials and MVP-005 history/RBAC.
- No content capture, automatic deletion, 5145/WEF/SIEM/reboot/mass audit or synthetic production CRUD.
- Bound every page, cache, loop, request lane and queue; incomplete proof never HEALTHY.
- Separate staged PRs, independent review, exact head/main CI and live acceptance.
- Operator authorized execution of the approved design and necessary single-root changes; no repeated scope permission loop. Implement inline; review independently at each stage.

## Review Focus

- Wide directories and long Unicode paths: lazy bounded enumeration and complete handle cleanup.
- Process interruption between state/config activation: no false continuity and no lost queued bytes.
- Sustained ingest pressure/client disconnects: immediate retryable refusal and released admission slots.
- Directory partial pages/renamed or disabled users: no stale identity relabeling or implicit role grant.
- Concurrent FILESERVER activity during bootstrap/SACL scans: finite proof lifetime, honest UNKNOWN/GAP and unchanged old-root coverage.

### Task 1: bounded readiness

**Files:** Modify collectors/windows_audit/{readiness,configuration,runtime,delivery}.py; packages/contracts/audit.py. Create collectors/windows_audit/readiness_worker.py; tests/backend/test_windows_audit_large_readiness.py.

**Interfaces:** Consumes existing Native.sacl_entry and policy. Produces scope_covered(root,sids,check,*,limit=256,max_depth=128,max_seconds=30,stopped=...,clock=...) -> bool and background ReadinessWorker snapshot with checked_at/duration/count; AuditConfig.readiness_max_objects <=100000, proof freshness <=60 seconds. Native calls use long-path aware metadata access.

- [x] Write and run RED for >256 approved objects, 52k wide synthetic entries without a width-sized pending list, depth/timeout/cancel/reparse/ACL failure and iterator cleanup.
- [x] Implement lazy DFS resource bounds and explicit validated configuration, preserving old defaults.
- [x] Write and run RED for background scan not blocking capture, stale/incomplete proof not HEALTHY, scan failure and worker stop cleanup.
- [x] Implement the readiness worker and typed proof diagnostics, preserving genuine policy/SACL mismatch GAP behavior.
- [x] Verify `pytest tests/backend/test_windows_audit_readiness.py tests/backend/test_windows_audit_large_readiness.py tests/backend/test_windows_audit_runtime.py tests/backend/test_windows_audit_delivery.py -q`, Ruff/mypy/OpenAPI. Record tests and commit.

### Task 2: explicit USN scope extension

**Files:** Create collectors/windows/scope_extension.py; modify collectors/windows/{configuration,cli,usn_state,usn_capture}.py and collectors/common/outbox.py only for bounded atomic checkpoint transition support. Create tests/backend/test_windows_scope_extension.py and owned native fixture cases.

**Interfaces:** Consumes Task1 stable resource bounds only. Produces extend_scope(state,new_roots,*,stopped=...) and restart-safe transition receipt. Normal activate remains strict. Outbox atomic transitions preserve batch bodies/digests and existing checkpoint cursor value.

- [x] RED: strict-superset validation, shrink/overlap/reparse rejection, queued byte identity, credentials/old roots/cursors/GAP preserved, new root unknown before fence, all crash boundaries fail closed or resume idempotently.
- [x] Implement staged bounded ancestry/fence admission, atomic checkpoint/config transition and operator CLI; no blind config/SQLite edits or shared rebaseline.
- [x] GREEN plus owned native new-root old-scope continuity and file-id/hard-link ambiguity tests.
- [x] Verify `pytest tests/backend/test_windows_scope_extension.py tests/backend/test_windows_usn_state.py tests/backend/test_windows_usn_capture.py tests/backend/test_windows_configuration.py -q`, full regression/native Windows/strict HTTPS. Commit; independently review A, fix RED→GREEN, PR A exact-head/main CI.

### Task 3: bounded central resource admission

**Files:** Create apps/api/ingest_admission.py; modify apps/api/main.py, deploy/compose/docker-compose.prod.yml and environment validator as needed; tests/backend/test_ingest_admission.py; tests/deployment resource fixture.

**Interfaces:** Produces ASGI admission middleware for two heavyweight ingest slots and two heartbeat slots; excess returns 503/Retry-After without consuming request body. Production memory/swap budgets from spec; SQL connection pool within PostgreSQL40 connection budget.

- [x] RED: third heavy request refused immediately, heartbeat reserve works, exception/disconnect/oversize release, no partial ingest/receipt on refusal.
- [x] Implement admission and documented enforced container/PostgreSQL limits; retain retryable transport contract.
- [x] GREEN targeted integration plus actual Compose cgroup inspection/load fixture and full regression. Independent review, PR B and exact-head/main CI. Preserve all history and capture cursor semantics.

### Task 4: streamed directory observations and sensitive read enrichment

**Files:** Create packages/contracts/directory.py, packages/shared/models/directory.py, additive migration, apps/api/directory_ingest.py, packages/shared/directory/*.py, collectors/windows_audit/directory*.py; modify registration/auth only for explicit collector capability, audit read DTOs, Web audit components and ru/en catalogs.

**Interfaces:** Typed DirectoryPage and ClientNameObservation with source/domain/snapshot/page identity, observed_at/completeness/freshness. Authorized collector push and admin-only projections. Original evidence fields unchanged.

- [x] RED DTO/page bounds, duplicate/conflict/partial snapshot, cross-source auth, SID/GUID conflicts, outage/disabled/rename and indexed query limits.
- [x] Implement paged signed/sealed machine-identity collection and bounded durable delivery; no operator credential storage or direct DB insertion.
- [x] RED→GREEN PTR/forward/unique-computer resolver, negative cache/TTL/timeouts/ambiguity and immutable native WorkstationName.
- [x] RED→GREEN admin-only API/RBAC and i18n UI with explicit provenance/freshness. Verify schema upgrade/check/roundtrip, EXPLAIN, full backend/Web/Playwright/secret scan. Independent review, PR C exact-head/main CI.

### Task 5: protected live rollout

**Files:** private apply/rollback helpers and baseline under .local; sanitized docs/acceptance/storage-audit-002-ledger.md only.

**Interfaces:** Consumes exact merged-main packages from Tasks1–4. Runtime is permanent single-root capture; final Audit RUNNING after acceptance.

- [x] Fresh private preflight: root/volume, GPO policy owner, current roots/state/package, queue, RAM/disk; verified backup with off-VM copy. Resolve disk deployment headroom before changing services.
- [x] Stage and verify wheel/source hashes, use tested stopped-runtime USN transition retaining old data; own Audit new state and scope. Apply only precise selected-root SACL/Success-policy diff after backup; do not touch DACL/SMB/Failure/other roots.
- [x] Verify actual machine-identity directory read and collector push; never install operator password. Apply enforced central resource limits through canonical deployment with rollback.
- [x] Observe ordinary operations: exact new-root events/history, evidence/UNKNOWN/AMBIGUOUS honesty, UI/RBAC, queues, stable RSS/cgroups/disk and unchanged old-root history. No production CRUD or outage injection.
- [x] Record installed/deployed SHA, CI, live counts, limitations and final disposition. Stop work after acceptance; no new scheduled monitor.

2026-10-14 final disposition: CI correction and approved250GiB migration PASS;
Audit RUNNING with corrected installed main9296ca51357635207325e50c447f2213997e4093.
Central/USN remain927e4c5107785765b5040f571dd6b9cf6f119014. Four live Audit/directory
samples PASS; ordinary new-root history acceptance remains PENDING because the
bounded Activity sample has no selected-root rows and reports UNAVAILABLE/UNKNOWN.
No synthetic production CRUD or scheduled monitor. See acceptance ledger.


2026-10-15 recovery acceptance: source PR #40/central1540 fixes inventory scope
and stable-volume ingest. Explicit stopped-state repair preserves original USN
runtime/registration/cursor/GAP/queue/credentials; actual full inventory completed.
Three exact missing-SACL files restored with the approved inherited Success ACEs,
without business content I/O or DACL/owner/group/policy changes. All31 retained
Audit batches replayed unchanged; old GAP/backup retained. Explicit fresh Audit
state/generation uses the same identity/runtime with canonical volume mapping.
Task5 PASS: selected-root ordinary history and actual UI/evidence verified through
OLD-GENERATION replay, with UNKNOWN/AMBIGUOUS retained. A positive ordinary event
from the fresh quiet generation is not claimed. Final queues empty, central jobs
pending0/failed0, enforced memory limits/no OOM, approved data UUID/history/backup
preserved; see acceptance ledger for measurements. Both services RUNNING. STOP.
