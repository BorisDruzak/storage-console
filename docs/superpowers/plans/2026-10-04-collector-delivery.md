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
- Credential/token never in SQLite, logs/exception messages/public Git; strict HTTPS only.
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

## Task1 — Transactional local state

Files: create `collectors/__init__.py`, `collectors/common/{__init__,outbox}.py`,
`tests/backend/test_collector_outbox.py`; update package discovery/mypy in `pyproject.toml`.
Interfaces: Outbox(path,collector_id,limits); enqueue(domain,batch,stream,expected_revision,
checkpoint)->durable batch identity; checkpoint(stream)->revision/value; claim(now)->Claim
orNone; acknowledge(claim); retry(claim,code,next_attempt); quarantine(claim,code); status().
Claim is immutable body/domain/batch ID/lease ID; no credentials. Safe OutboxError has fixed code.

- [ ] RED domain/identity/schema/UTF/body/checkpoint validation, private state initialization,
  immutable identity/future schema and bounded capacity tests.
- [ ] RED atomic enqueue/CAS/failure rollback, repeated commit acknowledgement, changed payload,
  receipt retention/forgotten transition conflict and concurrent producers.
- [ ] Implement explicit SQLite transactions/schema/limits and fixed value-free errors.
- [ ] RED claim/lease expiry/stale ACK, same-stream FIFO/quarantine blocking and independent
  streams; implement transactional lifecycle without network under lock.
- [ ] Run focused/full tests, Linux3.13 and Windows subprocess crash/restart tests, Ruff/mypy,
  package/import checks; inspect complete diff and commit `feat(collectors): add durable outbox`.

## Task2 — Strict transport and delivery policy

Files: create `collectors/common/{transport,delivery}.py`,
`tests/backend/test_collector_transport.py`, `tests/backend/test_collector_delivery.py`.
Consumes Task1 Claim and existing BatchEnvelope/Receipt semantics.
Interfaces: Transport(origin,ca,token,timeout).send(claim)->DeliveryOutcome; Delivery.run_once
uses injected clock/randomness/transport; explicit refresh_credentials resumes401/403 suspension.

- [ ] RED config/secret repr, exact routes/headers/unchanged body, real TLS trust/hostname,
  untrusted/redirect/ambient proxy rejection and response32KiB/exact202 receipt tests.
- [ ] Implement bounded stdlib HTTPS transport with fixed outcome codes/no response echo.
- [ ] RED transient capped retry/Retry-After,401/403 suspend+refresh, permanent quarantine,
  malformed success/no ACK, cancellation/shutdown and stale completion tests.
- [ ] Implement coordinator, no issuance/re-enrollment and no lost queued work.
- [ ] Focused/full tests/Ruff/mypy/package checks; commit
  `feat(collectors): deliver retained batches over verified HTTPS`.

## Task3 — Real API acceptance and review

Files: create `tests/backend/test_collector_delivery_integration.py` and a focused native
TLS/disposable delivery acceptance helper under `tests/deployment`; update collector READMEs,
task index/status and this plan. Keep runtime integration tests independent from browser keys.

- [ ] RED actual PostgreSQL ingest firstaccept, lost response, restart and duplicate ACK with
  one persisted effect; rotation/disable leaves batches retained and explicit refresh recovers.
- [ ] Exercise real HTTPS with synthetic private credentials and Windows process-crash
  durability. No traces/logs/public artifacts containing credentials or real evidence.
- [ ] Full Linux3.13/PG16/migrations, frontend compatibility, type/package/secret/native checks;
  one fresh whole-subsystem review; Important fixes RED→GREEN in one pass.
- [ ] Publish main, verify exact terminal required CI, record actual acceptance and remaining
  Windows/PVE/PBS/USN/pilot work. Do not mark the full goal or Wave1 complete.

## Rulings

Rollback journal is the initial durability mechanism; synchronous=FULL and explicit SQL
transactions avoid Python transaction-mode ambiguity. Cost: SQLite serializes local writers;
measure before introducing WAL/sidecar ownership and backup complexity.
Per-stream FIFO is required despite independent-stream progress. Cost: a quarantined stream
blocks later observations until explicit operator repair, preventing stale replay inversion.
Enqueue receipts remain bounded; a forgotten retry returns checkpoint conflict rather than
pretending to have reconstructed committed state. Cost: producer must reload its durable
checkpoint before continuing after a sufficiently old acknowledgement loss.
