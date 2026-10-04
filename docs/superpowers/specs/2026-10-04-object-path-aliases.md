# Simultaneous object paths

## Purpose and boundary

Canonical section 7 requires path aliases and rename history. One volume/FileId
identifies one object even when several hard links are observed. The accepted
Windows metadata component currently reports MULTIPLE_LINKS instead of publishing
misleading history. This capability replaces that interim limitation after backend
acceptance. It does not accept the Windows Service, USN continuity, snapshot
deletions, large-tree performance, or a live pilot.

## Contract and compatibility

Add `FileObjectRecord.link_count: int | None`, a strict integer in 1..4294967295.
Only FILE records may provide it. Unknown and directory counts are omitted from
serialized data using Pydantic 2.13.5 Field.exclude_if; preserve all other existing
defaults and nulls. Omitted/explicit-null counts must reproduce the pre-upgrade
canonical batch digest and retained outbox bytes. Positive counts affect the
digest. Schema version remains 1; upgrade the backend before enabling new capture
payloads, since an older strict endpoint rejects the added field.
Native observation time is captured before the StandardInfo metadata query and
carried through deferred record publication. A positive native count without that
time fails explicitly; never give old count evidence a fresh publication timestamp.
Inventory dates describe observation boundaries; exact operation times require USN.

## Identity and temporal evidence

Store all observed aliases separately from the object's representative path.
Repeated observations extend an existing interval rather than close/reopen it.
The representative remains stable while active; when it ends, select the earliest
active interval (UUID breaks ties) and use that alias's name and known parent.
Do not copy the removed alias's parent into a replacement. With no active path,
retain the last known representative. Path removal does not prove whole-object
deletion: another link may exist outside approved scope. Set deleted_at only for
an explicit whole-object deletion no older than the last positive path evidence;
do not reinstate an old object tombstone after resurrection and a later alias-only
removal. Object metadata is updated only by observations at least as
new as its last metadata/event time; older independent alias evidence is still
processed.
Admitted older inventory also moves object first_seen_at to the earliest observed
inventory timestamp; its metadata and last_seen_at remain protected by newer evidence.

Maintain separate persistent positive and negative event-time watermarks per path.
A path is active only when its last positive observation is newer than its path
removal and whole-object deletion watermarks. Equal-time deletion wins. Negative
watermarks survive resurrection. A delayed observation cannot reopen a path ended
by newer evidence; a delayed observation of a different still-existing alias can
add it despite newer metadata for the first alias. Extend an active interval's
start backwards only within its latest proven removal boundary. Do not reconstruct
complete historical intervals from late observations of already closed paths.

An observed link_count=1 proves that the observed path was the sole link at that
time. Persist the latest sole-path proof separately from the latest link count;
close other aliases whose positive observations are no newer than that proof.
Suppress delayed other-alias observations at or before the proof. Never erase an
alias observed later than the proof. A positive count greater than one does not
prove any absent path exists and does not require discovering all links within an
approved scope. Persist an ever-observed-multiple flag: legacy unknown-count
records cannot overwrite established multiple-path facts. Before that flag is
set, legacy unknown-count inventory retains the existing single-path replacement
semantics, with the same dated sole-path proof to resist stale delivery.
Unknown-count observations before multiple-path evidence retain the legacy
object-level stale-record guard, including after a newer rename. Explicit counts
and unknown counts after multiple-path evidence use independent per-path ordering.
Equal-time legacy replacement cycles retain delivery-order behavior. Track
event_ended_at separately from inferred sole-path retirement: only an inferred
equal-time end may be reopened by legacy inventory; explicit rename/delete and
whole-object deletion still win ties. Contradictory explicit count-one proofs for
different paths at the same time reject the batch with SOLE_PATH_CONFLICT.

RENAME closes only old_relative_path and observes new_relative_path, preserving
other aliases; identical old/new paths are an observation, not an interval churn.
DELETE with old_relative_path ends only that path. DELETE without a path ends all
paths. WRITE/METADATA/SECURITY events do not implicitly move paths. Change events
remain append-only even if too old to alter current state. For changes arriving
before inventory, retain the existing event and hydrate its path transitions when
the first object is observed, using an indexed identity/event-time query. Do not
fabricate an object before inventory provides its required metadata.

## Persistence and migration

Create `object_path_states`: UUID identity, object FK, exact relative_path Text,
SHA-256 path_digest String(64), nullable parent_file_id/name, nullable seen_at and
ended_at/event_ended_at, nullable unique active_history_id FK to object_path_history. Unique
(object_id,path_digest) provides a bounded index for 32767-character paths.
Compare exact strings on every digest lookup and reject a collision with a bounded
IngestConflict; the digest is never an object identity. Existing source-row locks
serialize mutations, including uploads by distinct collectors on one source.

Add nullable link_count/link_count_at, sole_path_digest/sole_path_at, last_deleted_at
and non-null default-false multiple_paths_observed to filesystem_objects. Preserve
the existing current path and history table contract. Path state owns the one open
interval pointer; close an interval and clear its pointer atomically. Keep dates
timezone-aware and the positive count constrained in PostgreSQL too.

Migration 0005 backfills states using bounded UUID keyset pages of history rows,
merging per-path positive/removal watermarks. For the existing active representative
use the object's last_seen_at and known name/parent; other historical paths have
unknown parent. Existing deleted objects' remaining open intervals must close.
Initialize whole-object deletion watermarks from historical DELETE semantics
(all pre-upgrade DELETE events were whole-object deletes), including previously
resurrected objects. Preserve every receipt, event and identity. Add an event index
on source_node_id/volume_identity/file_id/occurred_at for first-observation hydration.
Downgrade refuses if multiple simultaneously active aliases would be lost; the
ordinary single-path migration round trip remains supported. No production
migration is authorized by tests against disposable schemas.

## Verification

Prove pre-upgrade golden serialization/digest, stored-receipt replay and raw
outbox replay; strict count validation; two aliases scanned twice with one object
and two open intervals; rename/remove one; count-one reduction; explicit object
deletion/resurrection; independently delayed aliases, stale removal and equal-time
deletion; unknown-count compatibility after known multiple paths; first-inventory
hydration; digest collision rollback; long Unicode paths; concurrent collectors;
existing-row migration/backfill/downgrade guard and metadata drift.

Actual Windows hard-link capture must emit both paths with identical FileId and
actual count. Actual strict-HTTPS/PostgreSQL delivery must preserve those paths
through repeated scans. Full Linux/PostgreSQL, migrations, types, lint, generated
OpenAPI/frontend, packaging, secrets and exact-source CI must pass. One fresh
whole-component review follows implementation; one fix pass for important findings.
