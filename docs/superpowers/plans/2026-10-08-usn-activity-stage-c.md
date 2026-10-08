# Stage C: read-only NTFS USN and real Activity

**Goal:** Complete only Gate C of Issue #8 after the accepted A/B gates.
**Spec:** `docs/tasks/mvp-003-004-three-stage-delivery-train.md`, Stage C.
**Baseline:** main `8a1916d96aaca75287ff9b0865c9b5b98c8454ec`; exact-main
CI `37742833424`, six required jobs SUCCESS; Sonar SKIPPED.
**Architecture:** Native, bounded QUERY/READ USN -> scoped FileId ancestry and
protected persistent cache -> existing transactional outbox -> HTTPS changes
ingest -> PostgreSQL change_events -> authenticated typed Activity API -> Russian UI.
**Tech stack:** Python 3.13/ctypes/sqlite3, pinned FastAPI 0.142.2/Pydantic 2.13.5/
SQLAlchemy 2.0.54/PostgreSQL 16, React 19.3.0/TanStack Query 5.104.1/TypeScript 5.9.3.

## Constraints and review focus

- No journal create/resize/delete API, document contents, attribution, audit/ACL/
  SMB/VSS changes, reboot or work beyond Stage C. No private evidence in Git.
- User explicitly delegated creating the dedicated test folder with “создай сам”.
  Preparation succeeded in existing approved scope; QUERY of existing journal PASS.
  Folder/path and raw query remain private. Controlled CRUD/restart/outage and
  explicitly consented cleanup completed; see the final execution ledger.
- Reuse installed identity/config/binding and A/B lifecycle. Independent heartbeat,
  inventory and delivery remain bounded during USN pressure and shutdown.
- Existing Outbox schema can persist individual cache entries as bounded checkpoints;
  extend its transaction interface rather than introduce an independent non-atomic DB.
  Cursor/cache/batch mutations must share one SQLite transaction and revision guard.
  Zero-event reads also need a guarded atomic cursor/cache transition.
- Stable source event IDs derive from canonical volume, journal and record USN/type.
  Replay must preserve stored batch bytes. Add a narrow USN event uniqueness index
  only if source inspection confirms existing ingest lacks logical-event deduplication.
- Native V2 identifiers must match inventory's 128-bit little-endian byte representation;
  V3 identifiers retain all 128 bits. Never compare identities by drive letter.
- Initial bootstrap explicitly establishes a new observation baseline, not recovered
  historical completeness. Journal gaps remain latched UNKNOWN until an explicit,
  documented rebaseline. No silent cursor reset after gaps or invalid state.
- Scope is proven before persist/upload. Unproven parents never imply membership.
  Moves out redact outside names; descendants under renamed ancestors either resolve
  accurately or carry explicit unknown paths. Deleted paths use persisted evidence.
- Historical B partial-capture root cause remains unestablished; do not describe C as
  fixing it. Gate reopening is required if a concrete regression is reproduced.

## Task 1 — strict portable parser and native QUERY/READ

Files: `collectors/windows/usn.py`, `collectors/windows/usn_native.py`,
`tests/backend/test_windows_usn.py`, `tests/backend/test_windows_usn_native.py`.

- [x] RED V2/V3 reason/time/UTF-16/128-bit fixtures and malformed/truncated buffers.
- [x] Implement bounded bytes parsing, strict offsets/alignment/monotonic cursor;
      unsupported version produces a fixed error code, not fabricated evidence.
- [x] Implement QUERY and non-waiting READ only on configured-root volumes;
      explicit unsupported/access/volume/journal-gap states. No mutation controls.
- [x] Actual native NTFS CRUD test; journal must already exist. Unsupported host
      is reported as a gate limitation, never substituted by portable fixtures.
- [x] GREEN relevant pytest, Ruff/mypy and API documented against Microsoft Learn.

## Task 2 — atomic cache/cursor/event state

Files: `collectors/common/outbox.py`, `collectors/windows/usn_state.py`,
`tests/backend/test_windows_usn_state.py`, `tests/backend/test_collector_outbox.py`.

- [x] RED atomic multi-checkpoint updates, stale revision, injected pre-commit failure,
      reopen/crash before/after enqueue and byte-identical lost-ACK replay.
- [x] Add bounded checkpoint-group transitions in existing transaction and table set;
      validate all inputs before commit; empty transition never sends empty batches.
- [x] Persist only approved ancestry/component cache plus journal cursor and pending
      rename/write state. Bound entry count, component sizes and per-tick mutations.
- [x] Test rollback with accepted B reader/writer and preserve backup recovery.
- [x] GREEN complete Outbox/delivery regressions plus new persistence tests.

## Task 3 — scope, normalization and continuity

Files: `collectors/windows/usn_capture.py`, scope/state tests and native tests.

- [x] RED create/write/rename/delete, one rename across restart, CLOSE coalescing,
      ancestor rename, deleted last-known path, long/Cyrillic names, scope moves.
- [x] Resolve membership by pinned FileId ancestry. Unknown or out-of-scope raw
      volume names remain transient and are neither checkpointed nor uploaded.
- [x] Stable deterministic event IDs; bounded coalescing and pending-pair retention;
      unresolved rename paths are explicit unknown, never invented.
- [x] RED journal ID change/wrap/access/unsupported/corrupt state; latch continuity
      UNKNOWN and document operator rebaseline including its observation gap.
- [x] GREEN portable and real native synthetic tree tests, including scope privacy.

## Task 4 — service integration and pressure

Files: `collectors/windows/runtime.py`, owned USN worker/process adapter as needed,
`collectors/windows/inventory.py`, heartbeat producer and runtime tests.

- [x] RED independent heartbeat/inventory while USN burst/backpressure is active;
      bounded stop, worker crash and service restart retain all durable state.
- [x] Integrate independently bounded owned capture without competing service owner,
      reenrollment, transport replacement or private configuration changes.
- [x] Report USN cursor/continuity in heartbeat; missing/gapped coverage cannot become
      healthy merely because heartbeat or inventory succeeds.
- [x] GREEN existing SCM/runtime/CLI plus new installed native USN lifecycle tests.

## Task 5 — Activity API and idempotent ingestion

Files: `packages/contracts/read.py`, `apps/api/read/activity.py`, read routes,
`packages/shared/ingest/core.py`, activity model/index migration only if needed;
backend read/ingest/migration tests and generated OpenAPI.

- [x] RED session/RBAC, source/type/time window validation, pagination/newest-first
      ties, nullable object/path/actor/client/confidence, continuity/stale/no-store.
- [x] Bound default/max time windows, page size and offset; preserve provenance and
      stable identity. USN provides no authenticated actor or client attribution.
- [x] RED same logical USN event in different batches has one DB effect; guard
      history side effects under duplicate insert as well as changes row insertion.
- [x] GREEN actual PostgreSQL tests, migration upgrade/check/downgrade roundtrip,
      Ruff/mypy and generated OpenAPI/client contract checks.

## Task 6 — real Russian Activity

Files: Activity page/domain reader/client types, schema generator, catalogs and
frontend/Playwright tests. Other domain providers stay untouched.

- [x] RED real typed API, source/type filters, sorting, timezone, Cyrillic/long paths,
      loading/empty/error/stale states, unknown actor/client and no false confidence.
- [x] Implement documented 5-second polling, provenance and before/after paths;
      preserve expiry semantics and business timezone preferences.
- [x] GREEN Vitest, typecheck/lint/i18n/generated-client checks/build/audit and
      strict-CSP real API Playwright smoke.

## Task 7 — full regression, review and separate PR

- [x] Add new actual native tests explicitly to Windows Python 3.13 CI.
- [x] Full backend/deployment/migration/type/lint/OpenAPI, frontend/Playwright,
      installed wheel/CLI/SCM/native/integration and public secret scan.
- [x] Independent whole-change review; Important corrections verified RED -> GREEN.
- [x] Atomic Conventional Commits; inspect all diff/status before each commit.
- [x] Separate Stage C PR; exact-head six-job SUCCESS, honest Sonar status, then
      normal merge and exact merged-main SUCCESS. No force push or CI cancellation.

## Task 8 — bounded pilot and Gate C STOP

- [x] Freeze exact artifact hashes; verified PostgreSQL/config/collector-state backup,
      rollback checkpoint and compatibility proof before central/collector update.
- [x] Controlled dedicated folder create -> one write -> file/parent rename -> delete;
      stable FileId, correct paths, native counts and strict TLS/API/actual browser.
- [x] Measure creation -> Activity visibility <=60 seconds including polling.
- [x] Controlled service restart, brief HTTPS loss/lost ACK replay, no duplicates or
      missing events, synthetic outside-scope exclusion, heartbeat/inventory intact.
- [x] Cleanup only the owned dedicated synthetic folder under delegated user scope;
      verify resolved absolute target and use native literal-path operations.
- [x] Ledger records exact SHAs/CI/artifact/test/live results and any limitations.
      Gate C PASS only after all required evidence; after Gate C STOP.

## Verification commands

Use the primary `.venv/Scripts/python.exe` by absolute path in the worktree;
target Python 3.13/real PostgreSQL/full gates also run in isolated canonical CI.

```text
python -m pytest tests/backend/test_windows_usn.py -q
python -m pytest tests/backend/test_collector_outbox.py tests/backend/test_windows_usn_state.py -q
python -m pytest tests/backend/test_windows_usn_native.py -q
python -m ruff check apps packages collectors tests
python -m mypy apps/api apps/worker packages/shared packages/contracts collectors
python -m pytest tests/deployment -q
alembic upgrade head; alembic check
python -m pytest tests/backend -q
npm run api:check --workspace apps/web
npm run lint --workspace apps/web
npm run typecheck --workspace apps/web
npm run test --workspace apps/web
npm run build --workspace apps/web
npm run test:e2e --workspace apps/web
```

## Reference boundaries

GitNexus repository list was checked: Storage Console is not indexed; repository
source/tests are used without interpreting another project's graph as this repo.
External behavior is checked against pinned-version Context7 documentation and
[Microsoft QUERY/READ USN documentation](https://learn.microsoft.com/en-us/windows/win32/api/winioctl/ni-winioctl-fsctl_read_usn_journal).
Historical initial source inspection found that `change()` inserts each logical event without
a source-event conflict guard; task 5 established the narrow dedup boundary, verified with real PostgreSQL.

Execution is inline under the user's already-authorized three-stage train.
This plan adds no permission requirement or product scope beyond the source spec.

Final acceptance: exact merged-main CI and actual deployment/live proof PASS.
Operator-consented cleanup completed. After Gate C STOP; no later stage executed.
