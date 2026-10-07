# Stage B — native Windows Service implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. Perform one independent whole-stage review before publication; user-authorized ordered train A → B → C remains binding.

**Goal:** Run the existing Windows Collector Runtime under native SCM without an interactive shell, preserving enrollment, protected state and durable delivery.

**Architecture:** A small native SCM adapter manages one own-process service; a dispatcher bridges SCM callbacks to the existing `Runtime.run(stop)` and `ProtectedState`/`load`. Operator CLI verbs query SCM independently of the runtime lock. No duplicated capture/delivery implementation, scheduled task, external service wrapper or new dependency.

**Tech Stack:** Python >=3.13, standard-library ctypes/Win32 SCM; existing installed wheel, DPAPI, SQLite outbox and strict HTTPS.

**Spec:** `docs/tasks/mvp-003-004-three-stage-delivery-train.md`, Stage B (user explicitly requested execution of this written delivery train).

## Baseline and constraints

- GATE A accepted runtime/source `dda125d08f97fac78ccea466ec89fd0ad6f79776`; push CI `37686825905` terminal SUCCESS, all six jobs, Sonar SKIPPED.
- Final Stage A documentation merged via PR #10 at `ef78111c0d2e8f971cb16f7b64a40c3f7cffd716`; exact push CI `37688827452` terminal SUCCESS, six jobs, Sonar SKIPPED.
- Central remains deployed to accepted runtime `dda125d…`; later commits only publish documentation. Live identity/inventory/freshness and pre/post backups verified; Issues #5/#6 closed with evidence.
- Service name `SosnadminStorageCollector`; native own-process, automatic delayed start, LocalSystem. This principal is necessary for the current SYSTEM/Administrators-only state and native capture; a restricted principal is a separate, explicitly authorized future design, not an AD/account change in this task.
- Recovery: one restart after 10 seconds, then NONE; failure count reset after 86400 seconds. No reboot action or arbitrary recovery command.
- Startup/stop have explicit finite deadlines; native controls return promptly, pending states use checkpoints. RUNNING only after protected configuration is loaded; SCM RUNNING is process state, not storage/source health.
- Status must not open the protected runtime lock. Install/start idempotence must preserve a disabled service. Reject incompatible registration rather than managing an unrelated service.
- Existing state is neither re-enrolled nor purged; credential suspension/binding, pending batches and checkpoints are preserved. No ACL/SMB/audit/USN configuration change on FILESERVER.
- Validate LocalSystem executable/module installation safety read-only; never repair an unsafe binary directory by changing its ACL. Native tests use only owned synthetic fixtures and uniquely named services in an isolated environment.
- Real FILESERVER handover/service trial requires the operator approval specified in the task; real reboot additionally requires explicit approval and a maintenance window. No live action before the concrete package/tests/runbook are reviewable.
- GATE B remains BLOCKED without approved/completed real reboot; do not start Stage C.

## Files and interfaces

- `collectors/windows/scm.py`: native bindings, typed service configuration/status, own registration validation, finite management waits, safe install/start/status/stop/uninstall.
- `collectors/windows/service.py`: native dispatcher/control callbacks, strong callback references, serialized service state reporting and machine-code-only Event Log, thin Runtime lifecycle.
- `collectors/windows/cli.py`: service subcommands and friendly Russian lifecycle/conflict messages; arguments remain sanitized.
- `tests/backend/test_windows_service.py`: portable lifecycle/management/CLI negative behavior.
- `tests/backend/test_windows_service_native.py`: installed wheel and real SCM/LocalSystem integration, actual DPAPI/TLS, ownership, crash recovery, stop/cleanup, disabled/idempotent registration and durable state.
- Existing Windows runtime/CLI integration and real HTTPS/PostgreSQL fixtures: reuse actual transport/ingest and synthetic source scope; no production data in fixtures.
- `.github/workflows/ci.yml`: include new Windows-native tests in windows-pilot; preserve every existing required job and Sonar semantics.
- `docs/pilot/windows-service-ru.md`, Windows README, implementation status and execution ledger: operator handover, maintenance approval, rollback, exact evidence and outstanding gates.

## Tasks — RED → GREEN

1. **SCM management:** Write failing tests for absent/already-running/idempotent/disabled service, incompatible ownership, start/stop timeout, safe command quoting and no credential/config mutation. Implement the minimal native adapter; test actual queried start/recovery settings on Windows.
2. **Runtime host:** Failing tests for configuration-before-RUNNING, STOP/SHUTDOWN, runtime lock conflict, startup failure, unexpected runtime termination, bounded cleanup and callback lifetime. Implement native dispatcher over current Runtime. Explicit stop must not cause an automatic recovery restart; abrupt unexpected process death may recover once.
3. **Operator CLI and packaging:** RED service parsing/status-with-busy-state/friendly repeat/start errors/sanitized arguments. Add service verbs and module entrypoint; prove installed wheel operates outside the checkout, preserving existing foreground and activation behavior.
4. **Native/durable acceptance:** Installed wheel + native SCM/LocalSystem + synthetic protected state. Verify identity, credential binding, CA, pending/quarantine, inventory/heartbeat checkpoints and sequence over stop/start; transient HTTPS outage/lost ACK/auth suspension; controlled death and bounded recovery; uninstall retains state. Real HTTPS/PostgreSQL acceptance uses an isolated source/database environment; CI native tests must run, not merely skip on Linux.
5. **Review/publication/live gate:** Full Linux backend/deployment/migrations/types/lint/OpenAPI and frontend/Playwright regression, Windows native/package tests, secret scan. One independent whole-stage review; Important corrections RED→GREEN and full regression. Separate draft PR, exact head CI, merge and exact main push CI. Only then request the concrete operator handover/reboot approvals and run the approved live checklist. Record PASS only with all GATE B criteria; otherwise stop at BLOCKED with the exact operator action.

## Review focus

- SCM status may be RUNNING while delivery is auth-suspended; never report source HEALTHY from process state.
- A second foreground/service process must fail STATE_BUSY without touching queue/credentials.
- Native callbacks must remain referenced and must not leak Python exceptions or secrets to stdout/Event Log.
- Explicit stop, crash recovery and pending recovery are different states; no restart storm or unrelated process termination.
- Binary paths, arguments, state paths and existing service ownership must fail closed; no implicit ACL repair.

## Rulings

- Execute the user-provided written Stage B architecture/spec inline, with routine native-interface choices documented here; do not restart design approval for an already-authorized delivery train.
- Existing protected-state owner/DACL already permits SYSTEM; no credential migration or owner/ACL change is needed.
- Source/runtime acceptance SHA and later documentation SHA are distinct; their exact push checks are independently recorded above.

## Documentation references

- Python 3.13 ctypes docs through Context7 `/python/cpython/v3.13.9`: stdcall, explicit argtypes/restype, last-error handling and callback lifetime.
- [SCM dispatcher](https://learn.microsoft.com/en-us/windows/win32/api/winsvc/nf-winsvc-startservicectrldispatcherw).
- [Service states](https://learn.microsoft.com/en-us/windows/win32/services/service-status-transitions).
- [Service failure actions](https://learn.microsoft.com/en-us/windows/win32/api/winsvc/ns-winsvc-service_failure_actionsw).
