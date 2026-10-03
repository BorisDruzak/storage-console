# Codex Task — Wave 0B: Backend, Contracts and Database Foundation

## Goal

Реализовать стабильные backend contracts, PostgreSQL schema, ingest/read API и PostgreSQL-backed worker foundation.

## Required tables/domains

Core:
- source_nodes
- collectors
- collector_heartbeats
- volumes
- shares
- filesystem_objects
- object_path_history

Activity:
- change_events
- event_attributions
- event_evidence_links

Telemetry:
- metric_samples_1m
- metric_samples_1h
- metric_samples_1d
- diagnostic_bundles

Health:
- health_signals
- health_findings
- incidents
- incident_events
- health_policies
- policy_exceptions

Authorization:
- principals
- ad_groups
- group_memberships
- acl_templates
- acl_snapshots
- acl_aces
- acl_findings

Recovery:
- vss_snapshots
- backup_jobs
- backup_snapshots
- backup_verifications
- restore_tests
- recovery_policies

Hygiene:
- hygiene_snapshots
- scope_stats
- long_path_samples
- large_file_samples
- temp_artifact_stats
- duplicate_candidates

Discovery:
- discovery_jobs
- discovery_series
- discovery_schema_families
- digitization_candidates

Security:
- users
- roles
- user_roles
- audit_log

## Canonical identity

Drive letter не identity.

Unique filesystem object:
- volume_id
- file_id

Support current/historical mount aliases without duplicate logical volumes.

## Ingest contracts

Versioned Pydantic schemas:
- heartbeat
- telemetry
- changes
- events
- inventory
- ACL
- recovery
- hygiene
- diagnostics

Batch envelope:
- collector_id
- batch_id
- schema_version
- sent_at
- first_event_at
- last_event_at
- record_count

Duplicate batch_id idempotent.

## API foundation

Read:
- /api/v1/overview
- /api/v1/health/domains
- /api/v1/sources
- /api/v1/sources/{id}
- /api/v1/sources/{id}/freshness
- /api/v1/volumes
- /api/v1/shares

Ingest:
- heartbeat
- telemetry
- changes
- events
- inventory
- acl
- recovery
- hygiene

## Worker

PostgreSQL queue:
- FOR UPDATE SKIP LOCKED
- retries
- next_attempt_at
- status/error
- idempotency key
- advisory locks

## Constraints

Не реализовывать live USN/SSH/WinRM collectors в этой задаче.
Не хранить document content.
Не hardcode department names.

## Acceptance

1. Fresh DB migration PASS.
2. Duplicate batch idempotent.
3. Volume aliases map to one canonical volume.
4. volume_id + file_id unique.
5. Deleted object preserves last-known path.
6. OpenAPI generated.
7. Datetimes timezone-aware.
8. Worker concurrency test proves no double processing.
9. No secret leakage.
