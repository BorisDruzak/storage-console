# Windows collector runtime and service

## Intent and authority

Canonical sections 8/30 require an installed Windows Service, durable identity/state,
heartbeat and inventory; later waves add USN and operational providers. This plan
continues the already authorized canonical/main/inline execution. AD integration
is deferred by the user. Do not guess a pilot host or roots, install a service on
an unapproved machine, or treat foreground/source tests as installed acceptance.

## Architecture

Use one existing SQLite outbox. Reserve configurable batch/byte capacity for
heartbeat and bound its delivery priority with a burst limit. FIFO remains strict
within each stream, including quarantined/retrying heads. Shared auth suspension
and credential generations remain atomic. Separate heartbeat/database queues were
rejected because activation and crash recovery would span multiple transactions.
Defaults of the general outbox and Delivery retain their current behaviour.

Windows private state is an explicitly chosen local directory owned by SYSTEM or
Administrators, with a protected DACL allowing writes only to those principals.
Reject reparse points, hard-linked private files, unsafe owners/DACLs and corrupt
state before decrypting credentials or starting collection. Protect the collector
token with machine-bound DPAPI and UI_FORBIDDEN. DACL protection is required because
machine DPAPI alone does not authorize who can decrypt an accessible blob.
Public CA bytes are copied into that protected directory; no ambient/user CA or
proxy fallback. All secrets, ciphertext and roots are repr-hidden and never logged.

Private config version1 contains collector UUID, HTTPS origin, Scope, credential
version UUID, encrypted token and bounded runtime settings. Serialized configuration
must fit128KiB, checked before activation. Configuration requires exclusive ownership
of the runtime lock and explicit operator activation. Add an
internal credential binding to SQLite schema3: activate a new UUID, clear auth
suspension, advance credential generation and invalidate old leases in one FULL
transaction. Startup only verifies binding/config agreement: restart never clears
persisted auth suspension. A crash between DB activation and config replacement
fails closed until an operator finishes configuration. Preserve every old batch,
receipt, digest and checkpoint in schema1/2 migrations; older code cannot open3.

Run heartbeat scheduling independently of inventory. At most one capture child
and one delivery thread operate at a time. Use monotonic scheduling, UTC evidence
timestamps and interruptible waits. Delivery uses explicit heartbeat priority with
a finite burst, then gives eligible data a turn. Configuration defaults: heartbeat
30s, full inventory3600s, poll1s, transport deadline15s, stop grace30s, batch512;
outbox2048 batches/512MiB with32 heartbeat slots/64KiB reserved. Validated settings
may tighten these limits; transport deadline must fit the stop grace with DB wait
and child termination allowances. No overlapping scans or busy polling.
The runtime SQLite busy deadline defaults to1s. Stop-budget validation includes
eight possible DB waits across scheduling/delivery plus child reaping overhead;
the general outbox default stays unchanged.

Native capture runs in an owned subprocess so a blocked filesystem API cannot
prevent bounded stop. Child stdin carries only capture configuration, no token;
stdout is one bounded fixed-code CaptureReport, never paths/content/tracebacks.
Launch installed Python with isolated imports and hidden Windows creation flags.
On stop, request cooperative cancellation, then terminate/reap only the owned
child after its grace. FULL outbox transactions retain committed batches and roll
back incomplete checkpoint updates. A bounded capacity wait may pause a scan while
delivery frees space; after the deadline close handles and report CAPACITY. Never
hold pins indefinitely offline or declare an interrupted scan complete.

The runtime reports recent inventory errors and quarantined inventory through
heartbeat as collection uncertainty, without clearing evidence before a successful
attempt. Network/auth failure never becomes a successful collection. Maintain a
bounded local ring of operational counts/codes; no raw filenames or credentials.

## Native service and installation

Use standard-library ctypes with official Win32 SCM APIs, without new dependencies.
Pin callbacks for the dispatcher lifetime. Report START_PENDING, RUNNING,
STOP_PENDING with progressing checkpoints, and STOPPED; STOP/SHUTDOWN handlers
signal cancellation and return promptly. Exceptions produce bounded fixed codes.
Console invocation outside SCM fails explicitly; foreground mode is a separate
operator/testing command and never masquerades as a Windows Service.

Installation/configuration are explicit privileged commands. A LocalSystem service
uses an absolute system-installed Python executable and `-I -m` entry point. Reject
an ordinary-user-writable interpreter/package/config path. Never silently overwrite
an existing unrelated service, delete retained state, enable audit policy or alter
monitored-root permissions. Stop before changing identity, credentials or scope;
scope changes retain existing checkpoint safety and require an explicit compatible
state transition, not discarded backlog. Service registration/live acceptance waits
for the approved pilot target. Foreground owned-tree tests and native private-state
tests are allowed independent of that target.

## Verification and remaining canonical gates

Prove count/byte reservation under concurrent SQLite writers, unchanged default
limits/FIFO, heartbeat priority with data fairness, quarantine/backoff behaviour,
credential schema migration, restart suspension, stale-generation settlement and
config/DB crash mismatch. Use actual native Windows private directories/DPAPI,
restricted-token access checks and owned capture children, plus strict HTTPS/PG
foreground runtime tests with queue pressure, errors, recovery and bounded stop.
Test SCM status/control logic and actual console dispatcher failure without service
registration. Installed SCM/reboot/account/path acceptance requires the approved
target and is not replaced by mocks. Run full Linux/backend/deployment/migrations,
Windows/native, types/lint/OpenAPI, packaging/secrets and exact-source CI. One fresh
whole-component review and one RED/GREEN fix pass precede publication.

USN journal continuity/path cache,500k interrupted throughput, operational providers,
live pilot and production deployment remain mandatory beyond this component.
