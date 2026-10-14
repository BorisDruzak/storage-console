# STORAGE-AUDIT-002 — bounded department rollout

Operator approved a private single-root rollout design after STORAGE-AUDIT-001
acceptance. Exact production scope, identities and evidence remain in the private
operator plan. This specification contains synthetic limits and interfaces only.

## Outcome and invariants

Observe one additional approved local NTFS root, retain previous USN scope and
history, capture independent Security evidence, enrich SID and client names from
read-only directory/DNS observations, and keep memory, queue and request processing
bounded. API-first collector push remains mandatory. Directory enrichment grants
no Web roles and never edits original evidence or increases correlation confidence.
There is no 5145, WEF, SIEM, content capture, restore, mass-department audit, reboot,
automatic record deletion or new 72-hour soak claim. MVP-005 history/RBAC remain.

## A: bounded capture and observation scope

Keep the existing 256-object readiness default for existing configurations.
An explicitly configured maximum up to 100000 objects permits the approved larger
scope. Replace breadth-sized pending path lists with lazy depth-first enumeration;
bound depth, elapsed time and visited count, close every iterator on failure,
reject reparse and unreadable descendants, and report incomplete coverage honestly.
Full readiness proof must have a bounded lifetime; incomplete/expired proof never
means HEALTHY. Verification runs outside Security capture processing so a large
scan cannot block bookmark progress or delivery. Status records proof duration,
verified count, completion time and fixed-code errors without paths/identities.

Implement an explicit stopped-runtime scope-extension operation, never silently
allow changed scope in activate. Validate strict superset and safe new roots;
stage bounded new-root ancestry in durable storage and retain previous volume
cursors, queued packets, receipts, gaps and roots. Keep credentials unchanged. New-root coverage
starts at a proven fence; old history is not reconstructed or relabelled. Atomic
transition state is resumable after process interruption; startup either completes
the approved transition or fails closed. No partial state/config combination can
claim continuity. Operator rollback retains every new observation and pending body.

## B: central resource admission

Production defaults: API 768 MiB, worker 512 MiB, PostgreSQL 2048 MiB,
Web 128 MiB; finite swap bound equal to memory bound. Migration 512 MiB transient.
PostgreSQL shared_buffers 256 MB, work_mem 4 MB, maintenance_work_mem 128 MB,
max_connections 40. Application pool total must fit connection headroom.
At most two concurrent heavyweight ingest requests, with a separate bounded lane
for heartbeat. Excess requests return retryable 503 with Retry-After and never
accept partial records or move the collector cursor. Release slots on exception,
client disconnect and body limit failure. No unbounded waiting-request queue.
Backpressure preserves immutable batch replay. Existing row/page/body/cache/outbox
limits remain. Disk headroom is a separate capacity gate; no automatic history
deletion. Deployment requires the canonical preflight/backup/rollback, and runtime
resource proof includes actual enforced cgroup limits, RSS, free disk and queue age.

## C: directory and DNS enrichment

Read all user objects in the selected domain via bounded paged signed/sealed
Kerberos or validated LDAPS. Use a verified machine/technical identity, never the
operator password as a permanent secret. Full snapshots are streamed as bounded
pages; incomplete snapshots do not delete users or become current/full coverage.
Store SID/GUID/account/UPN/display name/enabled/domain namespace with observed_at
and freshness separately from immutable audit events. Collector push only.
Source-specific capability and token authorization prevent cross-source binding.

For observed client IPs only: bounded PTR, forward address confirmation and exact
unique enabled directory-computer lookup. Cache entries have finite count/bytes,
timeouts and TTL, including short negative TTL; no network-wide discovery.
Expose separate names with provenance/time and UNKNOWN/AMBIGUOUS/STALE statuses.
Current lookup cannot prove event-time computer identity. Preserve NULL native
WorkstationName and exact native SID/account/session/IP/RecordIDs. Admin-only typed
API and ru i18n UI; all non-admin roles fail with 403 and no sensitive payload.

## D: approved deployment and acceptance

Separate PRs and exact-head/main CI per stage; RED→GREEN, regression, native owned
fixtures and one independent focused review per delivered stage. Ledger records
failures, rulings, deployed/installed SHA separately and historical limitations.
Before real changes, capture current GPO ownership/effective policy/SACL baseline,
package hashes, off-VM backup and own registration/state rollback. Configure only
the approved root and selected domain principals; preserve DACL, SMB permissions,
Failure policy, other SACL ACEs, old collector identity/history/queue and GAP.
New Audit scope uses new protected state/generation, retaining prior pilot state.
Ordinary activity validates live capture/history/UI/resource bounds. No synthetic
CRUD, outage injection or reboot is needed unless separately requested. Final
accepted permanent Audit disposition RUNNING; stop task after acceptance.
