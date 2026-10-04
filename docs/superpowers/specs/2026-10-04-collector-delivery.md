# Collector durable delivery

Implements the approved canonical specification §8/26/30/34/35 for restart-safe,
idempotent collector uploads. Windows/PVE/PBS runtime and live inventory remain later
subsystems; this shared delivery component does not complete Wave1 or the pilot.

## Responsibility and boundary

Producers collect read-only evidence, normalize it through the existing version1
BatchEnvelope contracts, and atomically commit a batch together with their checkpoint.
The delivery component sends exactly those durable bytes to the existing nine ingest
domains. It never reads the filesystem/provider itself, mutates providers, enrolls
collectors, changes audit policies or invents health observations.

Use Python3.13 standard sqlite3/ssl/urllib and existing Pydantic contracts. No broker or
new service. `collectors/common` is packaged and typed with the existing repository.
Credential configuration is separate from outbox state; secrets never enter its payload,
SQL, audit, exception text or logs. Linux private directory/file permissions and Windows
service-directory ACLs are different platform acceptance gates; chmod alone cannot prove
Windows protection. Actual runtime installation owns Windows ACL enforcement later.

## Durable outbox and checkpoints

Initial SQLite schema version1 stores immutable collector UUID, allowed domain, immutable batch
ID/body/digest, delivery state and per-stream checkpoint revision/value. Reject a future
schema or a different collector identity; never silently replace or drop existing work.
Use one connection per operation, bounded busy timeout, parameter bindings and explicit
BEGIN IMMEDIATE/COMMIT/ROLLBACK with autocommit=True. synchronous=FULL and rollback journal
are the initial durability choice; no WAL sidecars without a demonstrated need.

Delivery adds local schema2 through a transactional, lossless schema1 migration. A boolean
authentication suspension and integer credential generation survive restart; neither is a
credential or credential hash. Explicit credential refresh advances the generation and
clears suspension. An older controller or late old-credential rejection cannot silently
resume or suspend the newer sender. Existing batch bytes, checkpoint transitions, receipts
and collector identity must survive unchanged; unsupported newer versions remain rejected.

enqueue validates the domain-specific BatchEnvelope and collector identity, serializes
canonical UTF-8 JSON once, checks limits, inserts the durable batch and compare-and-swaps
the stream checkpoint in one transaction. A stale checkpoint, disk/SQL/commit failure or
capacity rejection must leave both batch and checkpoint unchanged. A repeated batch ID
with identical body and checkpoint transition is idempotent; changed payload/domain or
checkpoint transition is a conflict. Keep a bounded durable enqueue receipt/transition
identity for safe producer retry after a lost commit acknowledgment, even if delivery
has already acknowledged and removed the pending body.

Initial defaults: at most1024 retained batches and512MiB payload bytes; each body at
most16MiB, matching actual API admission. Configurable limits must be bounded and reject
inconsistent settings. Checkpoint JSON at most16KiB; stream identity uses bounded text.
Never delete old evidence to make room. Quarantined batches retain their body and count
toward storage pressure. A bounded receipt-retention policy must never claim a forgotten
transition succeeded: old producer retries return an explicit checkpoint conflict.

Generic checkpoints provide restart-safe capture; the Windows USN subsystem will define
JournalID/cursor/FileId-cache atomicity and continuity. Do not assert USN acceptance here.
Private state directories must reject unsafe ownership/links where the platform supports
those checks; do not traverse a symlink or initialize over an unrelated database.

## Claims and acknowledgement

Claim the oldest due batch under a transaction with a random opaque lease ID and60-second
expiry. Expired claims can be reclaimed after a crash. Only the current claim can update
retry state or acknowledge/delete its batch; a stale response cannot delete a new lease.
The network timeout is15seconds, less than the lease. Do not hold the SQLite transaction
over network I/O. Successful ACK and receipt bookkeeping are transactional.

The15-second deadline bounds the whole attempt, including DNS and response reads. Use a
private stdlib worker subprocess, not a new service or broker; send credentials/config/body
through memory-only stdin. The parent terminates a timed-out child and the worker has its
own deadline for parent death. Neither command arguments, files, stderr nor result output
may disclose credentials. Result output contains bounded fixed outcome metadata only.

No ordering promise across unrelated streams. Per-stream delivery must preserve enqueue
order: a backoff, active lease or quarantine at its head cannot be skipped by later
inventory/change observations from that stream. Other streams may progress independently.

## Strict HTTPS and response semantics

Configuration fixes the HTTPS origin, CA and collector UUID. The token is supplied from
protected operator configuration at send time, with secret-safe repr. Validate origin,
timeout and token format before opening a socket. HTTPS verifies chain, DNS hostname and
TLS1.2 minimum; no insecure fallback, automatic redirects or ambient proxies. The allowed
ingest domain determines the route; payload/input cannot choose a URL or header.
Snapshot the configured public CA at construction so later file replacement cannot change
the worker's trust without explicit configuration refresh.

An HTTP202 response confirms delivery only if its bounded32KiB JSON exactly matches the
existing Receipt: accepted=true and duplicate a strict boolean. Both duplicate=false and
duplicate=true permit ACK. A lost/malformed response retains the unchanged body/batch ID;
its retry can receive duplicate=true after a real API commit. The existing receipt has
no batch ID field; do not invent a provider contract or accept an unrelated successful body.

Network/TLS/timeout/429/5xx failures retain work with capped exponential jitter backoff,
base1second/max300seconds and a bounded Retry-After. Authentication401/403 suspends repeated
sends while preserving work until explicit credential refresh. Permanent400/404/409/413/
415/422 and unexpected redirects quarantine the batch with a fixed code and retained body;
never echo an error body, token or URL. Bounded status/error metadata is observable to the
runtime; it is not a fabricated source HEALTHY/ERROR result. Shutdown leaves recoverable
claims; producers cannot advance capture state after enqueue failure.

## Acceptance

Prove atomic enqueue/checkpoint CAS, byte-identical replay/conflict, retention limits,
rollback and subprocess crash/restart. Test concurrent producers and claimers, expired
lease/stale ACK, per-stream ordering and independent-stream progress, future schema and
immutable identity. Prove real strict HTTPS trust/DNS/redirect rejection, receipt limits,
safe error classification, bounded retries and auth suspension/resume without data loss.

An integration test must use the actual PostgreSQL ingest: accept a batch, discard the
response, restart delivery and accept the duplicate receipt without a second effect.
Rotate/disable credentials and prove queued work survives until explicit recovery.
LinuxPython3.13 checks, Windows process-crash durability checks, source/package typing,
secrets checks, one fresh whole-subsystem review and exact main CI are required before
claiming this component accepted. Live Windows Service/provider/USN/pilot remain open.
