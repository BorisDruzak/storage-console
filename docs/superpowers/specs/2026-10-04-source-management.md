# Wave 1 source management

This subsystem implements source registration from the approved canonical specification
`docs/spec/storage-control-plane-v0.1.md` §6–10/25/26/34. It is the first Wave1 deliverable.
Collector runtime, durable outbox and live inventory require subsequent subsystem plans;
publishing this subsystem does not complete Wave1 or the full product.

## Decisions

Use the existing PostgreSQL source_nodes/collectors tables and protected user-session API.
An administrator registers immutable source identity and enrolls a collector. Enrollment
does not depend on a running collector. Each collector has an independent random credential.
An authenticated collector sends heartbeat/inventory through the existing ingest interface.

Source identity is `(source_type, instance_id)`; duplicate registration returns409 rather
than merging hosts. UUIDs never depend on hostname, drive letter or current network address.
Source types are FILESERVER/PVE/PBS; corresponding collector types WINDOWS/PVE/PBS. Source
and collector reassignment, deletion and source-identity editing are excluded. Registration
does not fabricate freshness: an unreported collector/source remains UNKNOWN.

Names and instance IDs preserve case and Unicode. Reject empty values, outer whitespace,
control characters, invalid Unicode, more than255 code points or1020 UTF-8 bytes. Optional
FQDN obeys the same bounded text rule; it is metadata, never a connection destination.
Expected cadence defaults60 seconds and accepts strict integers1..86400. Unknown fields,
types, coercible booleans/numbers and unsupported enum values are rejected.

## HTTP interface

- POST `/api/v1/sources`: CreateSource, returns201 SourceRegistration (UUID/type/names/
  immutable instance ID/cadence/created timestamp). Natural-identity collision409.
- POST `/api/v1/sources/{source_id}/collectors`: CreateCollector(type), returns201
  CollectorCredential. Missing source404; incompatible type409.
- GET `/api/v1/sources/{source_id}/collectors`: Page[CollectorView], limit1..100 default50,
  offset0..1000000, stable created_at/id order. All existing read roles may use it.
- POST `/api/v1/collectors/{collector_id}/rotate-token`: empty typed JSON object,
  returns200 CollectorCredential. Rotation preserves enabled state and collector/source IDs.
- PATCH `/api/v1/collectors/{collector_id}`: strict boolean enabled only, returns CollectorView.
  Disabling preserves history; re-enabling is explicit. Missing collector404.

CollectorView contains id, source_node_id, collector_type, version, enabled, created_at and
last_seen_at. CollectorCredential adds token, exposed only by enrollment/rotation responses.
Use token_urlsafe(32); store only the existing SHA256 collector token hash. SecretStr with
repr-hidden field keeps Python repr/dump masked; a JSON-only serializer supplies the wire
credential. Never return hashes, persist raw tokens or put tokens in audit/logs/URLs/browser
storage/query caches. A lost response is recovered by explicit rotation from the collector
list; no automatic retry of credential issuance and no replayable plaintext token store.

All writes require current storage_admin/manage_sources plus existing exact Origin/CSRF
checks. A collector bearer cannot satisfy these dependencies. JSON write bodies are limited
to16KiB of actual received bytes; malformed/unknown input receives generic422, wrong media
type415, excessive body413. All control/list responses, including errors, have no-store.
Database failures return generic503 CONTROL_UNAVAILABLE without SQL/input values.

## Transactions and audit

Insert source with PostgreSQL on_conflict_do_nothing at the natural unique constraint,
returning the row; no successful result without commit. Mutations and value-free audit
records commit together. Audit includes actor UUID, resource UUID, whitelisted action and
result, with empty details. Do not record input hostname/instance ID/credential.

Ingest already locks collector then source. Rotation and enabled changes lock collector only;
enrollment locks the existing source and inserts a new collector, never locks an existing
collector after its source. Finished rotation/disable must reject old credentials even for
replayed batch IDs. A concurrent ingest serialized before rotation may finish first; after
rotation completes no subsequent old-token admission is permitted. No migration is required.

## Console

Extend Sources with translated RU/en-US administrator forms and collector controls. Other
roles retain source/collector metadata views. Credentials exist only in component memory,
shown explicitly once with a close action; clear on close/unmount/logout/session change.
Use generic translated errors and disable resubmission while pending. Refresh metadata queries
after successful mutation. Backend permission remains authoritative when a displayed role
changes. Never show credentials in screenshots, traces or acceptance artifacts.

## Acceptance

Prove bounded contracts, Unicode policy and secret serialization; authenticated PostgreSQL
registration, natural-identity concurrency, audit rollback, old-token revocation/replay,
disable/re-enable, role/CSRF/bearer separation and body/error controls. Verify real ingest
heartbeat makes the source fresh. Console tests cover all role gates, pending/failure/close
states and session races. Extend disposable strict-TLS Chromium acceptance with synthetic
source lifecycle and collector ingestion. One fresh whole-feature review before completion;
full required CI succeeds on the exact published revision. No live provider/AD mutation.
