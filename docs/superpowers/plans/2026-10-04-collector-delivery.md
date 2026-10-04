# Collector durable delivery implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, task by task, with one
> fresh whole-subsystem review at the end. Canonical scope/main/inline already authorized.

**Goal:** Durably couple collector batches and checkpoints and deliver unchanged batches
through strict HTTPS across outage, lost responses and restart.
**Architecture:** `collectors/common` SQLite outbox, strict ingest transport and bounded
delivery coordinator; existing API/contracts remain authoritative.
**Tech Stack:** Python3.13 sqlite3/ssl/urllib and pinned Pydantic2.13.5; PostgreSQL16 acceptance.
**Spec:** `docs/superpowers/specs/2026-10-04-collector-delivery.md` and canonical §8/26/30/34/35.

## Global constraints

- No provider/filesystem collection or mutation in the common delivery layer.
- Existing nine domains/version1 contracts; body16MiB, receipt32KiB, checkpoint16KiB.
- Default retained capacity1024batches/512MiB, lease60seconds, network15seconds,
  retry base1second/max300seconds. No automatic loss of retained/quarantined work.
- Keep credentials outside SQLite, logs, error messages and public Git; use verified HTTPS.
- Main and inline publication authorized; no additional method approval loop.
- Source/collector UUID immutable; no fabricated health/live runtime acceptance.
- GitNexus lacks Storage Console; use source and tests. Context7 Python3.13 docs before APIs.

## Review focus

1. Crash after SQLite commit or API acceptance but before producer/client acknowledgement:
   checkpoint/batch consistency, exact replay and no second effect.
2. Concurrent producers/claimers and stale lease responses: no lost cursor or deletion of
   newly claimed work; same-stream observations preserve order.
3. Disk/full/capacity/quarantine pressure: fail capture explicitly without silently dropping
   evidence or advancing a checkpoint; independent streams can still progress.
4. TLS/DNS/redirect/proxy and malformed/oversized success bodies: no credential disclosure
   or false ACK; auth revocation preserves retained work.
5. Collector identity/schema changes and platform permissions: reject unsafe reuse and
   distinguish verified Linux permissions from later Windows service ACL acceptance.

## Task 1 — Transactional local state

Files: create `collectors/__init__.py`, `collectors/common/{__init__,outbox}.py`,
`tests/backend/test_collector_outbox.py`; update package discovery/mypy in `pyproject.toml`.
Interfaces: Outbox(path,collector_id,limits); enqueue(domain,batch,stream,expected_revision,
checkpoint)->durable batch identity; checkpoint(stream)->revision/value; claim(now)->Claim
orNone; acknowledge(claim); retry(claim,code,next_attempt); quarantine(claim,code); status().
Claim is immutable body/domain/batch ID/lease ID; no credentials. Safe OutboxError has fixed code.

- [x] RED domain/identity/schema/UTF/body/checkpoint validation, private state initialization,
  immutable identity/future schema and bounded capacity tests.
- [x] RED atomic enqueue/CAS/failure rollback, repeated commit acknowledgement, changed payload,
  receipt retention/forgotten transition conflict and concurrent producers.
- [x] Implement explicit SQLite transactions/schema/limits and fixed value-free errors.
- [x] RED claim/lease expiry/stale ACK, same-stream FIFO/quarantine blocking and independent
  streams; implement transactional lifecycle without network under lock.
- [x] Run focused/full tests, Linux3.13 and Windows subprocess crash/restart tests, Ruff/mypy,
  package/import checks; inspect complete diff and commit `feat(collectors): add durable outbox`.

Task 1 verification: Linux Python3.13/PostgreSQL16 full backend327 tests and
46 deployment tests passed; final outbox39 cases passed on Linux; mypy75 source files plus6 deployment files, Ruff,
OpenAPI check and base/head/check migration round trips passed. Windows outbox35
cases passed, with4 POSIX-only permission cases skipped. Real subprocess exits
before checkpoint commit and after commit prove rollback/replay on both platforms.
Installed wheel/import and public-source Gitleaks checks passed. These checks
accept local state only; transport, real delivery integration and whole-component
review remain Tasks2/3. Windows service ACL installation is a later runtime gate.

## Task 2 — Strict transport and delivery policy

Files: create `collectors/common/{transport,_https_worker,delivery}.py`,
`tests/backend/test_collector_transport.py`, `tests/backend/test_collector_delivery.py`;
extend `outbox.py`/its tests with a transactional local schema1-to2 migration.
Consumes Task1 Claim and existing BatchEnvelope/Receipt semantics.
Interfaces: Transport(origin,ca,token,timeout,collector_id=UUID).send(claim)->DeliveryOutcome;
Delivery.run_once
uses injected clock/randomness/transport; explicit refresh_credentials resumes401/403 suspension.

Execution rulings: persist suspension and a non-secret credential generation in schema2
so restart cannot resume a revoked credential and stale rejection cannot suspend a refreshed
sender. Preserve all schema1 evidence and identity during migration; retain future-schema
rejection. A private stdlib subprocess enforces the whole15-second attempt deadline because
urllib's socket timeout alone does not bound DNS or a slow response. Invoke its absolute
script with isolated Python; secret/config/body use memory-only stdin, error output is
discarded and result output contains only fixed bounded outcome fields. Snapshot the public
CA configuration at construction; the worker must not reload changed trust silently.

- [x] RED config/secret repr, exact routes/headers/unchanged body, real TLS trust/hostname,
  untrusted/redirect/ambient proxy rejection and response32KiB/exact202 receipt tests.
- [x] Implement bounded stdlib HTTPS transport with fixed outcome codes/no response echo.
- [x] RED transient capped retry/Retry-After,401/403 suspend+refresh, permanent quarantine,
  malformed success/no ACK, cancellation/shutdown and stale completion tests.
- [x] Implement coordinator, no issuance/re-enrollment and no lost queued work.
- [x] Focused/full tests/Ruff/mypy/package checks; commit
  `feat(collectors): deliver retained batches over verified HTTPS`.

Task 2 verification: Linux Python3.13/PostgreSQL16 full backend413 tests and46
deployment tests passed, with migration base/head/check round trips, mypy78 source
files plus7 deployment files, Ruff and OpenAPI checks. Installed wheel and its
isolated worker ran successfully; public-source Gitleaks scanned1.33MB without leaks.
Windows expanded checks passed117 cases, with4 POSIX-only skips; the remaining
worker-owned deadline case passed separately after its fixture timing correction.
Linux exposed an eager annotation startup error hidden by Python3.14 on Windows;
future annotations and an isolated-process regression corrected it. This accepts
transport/policy only; real API lost-response acceptance and final review remain Task3.

## Task 3 — Real API acceptance and review

Files: create `tests/backend/test_collector_delivery_integration.py` and a focused native
TLS/disposable delivery acceptance helper under `tests/deployment`; update collector READMEs,
task index/status and this plan. Keep runtime integration tests independent from browser keys.

- [x] RED actual PostgreSQL ingest firstaccept, lost response, restart and duplicate ACK with
  one persisted effect; rotation/disable leaves batches retained and explicit refresh recovers.
- [x] Exercise real HTTPS with synthetic private credentials and Windows process-crash
  durability. No traces/logs/public artifacts containing credentials or real evidence.
- [ ] Full Linux3.13/PG16/migrations, frontend compatibility, type/package/secret/native checks;
  one fresh whole-subsystem review; Important fixes RED→GREEN in one pass.
- [ ] Publish main, verify exact terminal required CI, record actual acceptance and remaining
  Windows/PVE/PBS/USN/pilot work. Do not mark the full goal or Wave1 complete.

Task 3 execution evidence: actual Uvicorn HTTPS/API/PostgreSQL accepted inventory;
the client subprocess exited29 after acceptance and before local ACK. Restart
replayed unchanged bytes, received duplicate=true and retained exactly one effect
in each of batches/volumes/objects/path history. Real credential rotation/disable
preserved pending work and auth suspension across restart until explicit refresh.
These three cases passed on native Windows through an encrypted connection to a
separate disposable PostgreSQL database; the additional real diagnostic route
case passed on Windows and Linux. No primary runtime/data or production DNS was changed.

Provider-path verification found diagnostics must use `/diagnostic-bundles`;
the previous generic TLS recorder had accepted the mirrored wrong route.
The corrected route expectation failed before the explicit map fix and passed
afterward; real API acceptance persists a diagnostic bundle and its correct batch kind.
Final Linux3.13/PostgreSQL16 full backend417/deployment46/migration round trips,
mypy78 source plus8 deployment/helper files, Ruff/OpenAPI, installed wheel/worker,
public Gitleaks1.35MB and frontend API/type checks passed. One whole-component
review and final publication/terminal CI remain before component acceptance.

## Rulings

Rollback journal is the initial durability mechanism; synchronous=FULL and explicit SQL
transactions avoid Python transaction-mode ambiguity. Cost: SQLite serializes local writers;
measure before introducing WAL/sidecar ownership and backup complexity.
Per-stream FIFO is required despite independent-stream progress. Cost: a quarantined stream
blocks later observations until explicit operator repair, preventing stale replay inversion.
Enqueue receipts remain bounded; a forgotten retry returns checkpoint conflict rather than
pretending to have reconstructed committed state. Cost: producer must reload its durable
checkpoint before continuing after a sufficiently old acknowledgement loss.
