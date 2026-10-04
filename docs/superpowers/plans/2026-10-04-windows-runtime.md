# Windows collector runtime implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, one fresh whole
> component review at the end. Canonical/main/inline authorization persists.

**Goal:** Deliver bounded collector scheduling, protected state and a native SCM host.
**Architecture:** One outbox with reserved heartbeat capacity/fair priority;
explicit credential activation; machine DPAPI/protected state; owned capture child;
native SCM adapter and privileged CLI with separate foreground testing mode.
**Tech Stack:** Python3.13, existing SQLite/Pydantic, Windows ctypes; no new dependencies.
**Spec:** `docs/superpowers/specs/2026-10-04-windows-runtime.md`.

## Global constraints

- Preserve retained bodies/digests/checkpoints and default general delivery behaviour.
- FIFO is per stream; quarantined/retrying heads cannot be bypassed within a stream.
- No secrets, ciphertext, roots or tracebacks in logs/public Git.
- DPAPI requires protected owner/DACL; restart never resumes suspended credentials.
- Only owned subprocesses are terminated; full scans are not snapshots/deletion proof.
- No AD work, guessed pilot/service installation, primary deployment or audit-policy change.
- A native/foreground proof is not installed SCM/reboot/live-pilot acceptance.

## Review focus

1. Multiple writers near reserve boundaries cannot consume heartbeat capacity.
2. Heartbeat backlog cannot starve eligible data, or bypass quarantined stream heads.
3. Configuration crash/rollback cannot resume old credentials or settle stale claims.
4. Unsafe private state/interpreter paths cannot expose a LocalSystem token/code path.
5. Stop during blocked capture/delivery cannot leak a child or advance an uncommitted cursor.

## Task 1 — Reserved capacity and fair heartbeat delivery

Files: `collectors/common/outbox.py`, `collectors/common/delivery.py`, create
`tests/backend/test_collector_priority.py`; common README if contract docs change.
Interfaces: Limits heartbeat_reserve_batches/heartbeat_reserve_bytes default0;
Outbox.claim(now, *, heartbeat_priority='normal') with normal/first/last;
Delivery(..., prefer_heartbeat=False, heartbeat_burst=4).

- [ ] Write RED count/byte reserve cases including concurrent writers and checkpoint
  rollback; default0 behaviour remains unchanged. Expected: missing fields/failing reserve.
- [ ] Implement validated limits and transactional non-heartbeat budgets; GREEN.
- [ ] Write RED priority/per-stream FIFO/quarantine/backoff and heartbeat burst fairness
  cases, including heartbeat queued before all data. Expected: unsupported priority/fairness.
- [ ] Implement three claim ordering modes and bounded Delivery burst/reset; GREEN.
- [ ] Run all common outbox/delivery/transport, contracts and Windows producer tests;
  strict affected types/Ruff/diffcheck. Expected: PASS. Inspect/commit coherent support.

## Task 2 — Protected configuration and explicit credential activation

Files: common outbox schema/API/tests; create Windows `errors.py`, `security.py`,
`configuration.py` and portable/native security/configuration tests.
Interfaces: Outbox.credential_binding() and activate_credentials(UUID); config load
only verifies binding. Security opens/validates local protected state and machine
DPAPI; fixed-code errors only. Configuration owns exclusive runtime lock.

- [ ] RED schema1/2 retained-byte migration, atomic activation/stale lease rejection,
  repeated binding and restart suspension; implement schema3/binding transaction GREEN.
- [ ] RED unsafe owner/DACL/reparse/hardlink/invalid config/mismatch cases; implement
  native protected state, DPAPI and strict private config with repr-hidden fields GREEN.
- [ ] Actual Windows owned directories/DPAPI and restricted-token read/write denial;
  explicit activation/crash mismatch tests. Expected: PASS, no service registration.
- [ ] Full affected common/config/native suites, types/Ruff/package/secrets/diffcheck;
  inspect/commit. Expected: PASS; document schema3 rollback/configuration order.

## Task 3 — Bounded foreground scheduler and capture worker

Files: create `collectors/windows/runtime.py`, `_capture_worker.py`; bounded capacity
wait in producer; new runtime/worker and real HTTPS/PostgreSQL integration tests.
Interfaces: Runtime.run(stop_event), private validated settings, CaptureProcess
start/poll/stop; summary-only child output. No token reaches the capture child.

- [ ] RED independent heartbeat/full-queue progress, one active scan, no busy polling,
  error/quarantine heartbeat and recovery; implement scheduler/waits/counters GREEN.
- [ ] RED child stop/crash/oversized output/checkpoint interruption and finite capacity
  wait; implement owned-process cancellation/reaping and producer retry GREEN.
- [ ] Actual native owned-tree foreground runtime through strict HTTPS/PG under queue
  pressure, lost ACK/restart/auth suspension and bounded stop. Expected: PASS.
- [ ] Full affected suites, installed wheel/worker isolation/types/Ruff/diffcheck;
  inspect/commit. Expected: PASS; installed/pilot/performance acceptance remains open.

## Task 4 — Native SCM host, CLI and final acceptance

Files: create `collectors/windows/service.py`, `cli.py`, SCM/CLI tests, console entry
point, Windows README/runtime plan and implementation status.

- [ ] RED SCM callback/status/control/stop/error and installer ownership/path cases;
  implement typed native adapter, pinned callbacks and explicit CLI GREEN.
- [ ] Actual Windows console dispatcher failure, config/private-state/foreground
  packaging proof. Expected: PASS; do not register service without approved pilot.
- [ ] Full Linux/backend/deployment/migrations/types/lint/OpenAPI, Windows/native,
  real foreground HTTPS/PG, frontend drift and packaging/secrets. Expected: PASS.
- [ ] One fresh whole-component review; re-grade, one RED/GREEN important fix pass,
  no second review. Inspect/commit. Expected: green suite, no unresolved important.
- [ ] Publish authorized main, exact remote/clean/CI proof, public acceptance/pending
  installed/500k/USN/pilot gates. Expected: five required CI jobs PASS on exact source.
