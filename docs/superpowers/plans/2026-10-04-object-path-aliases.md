# Simultaneous object paths implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline with one fresh
> whole-component review at the end. Existing full canonical execution and direct
> main publication authorization applies; no repeated method-approval loop.

**Goal:** Preserve simultaneous paths and their dated transitions for one FileId.
**Architecture:** Backward-compatible count DTO; persistent per-path watermarks
and interval pointers under existing source locks; native metadata emits real counts.
**Tech Stack:** Python 3.13, Pydantic 2.13.5, SQLAlchemy 2.0.54, Alembic 1.20.0,
PostgreSQL 16, Windows ctypes.
**Spec:** `docs/superpowers/specs/2026-10-04-object-path-aliases.md`.

## Global constraints

- Count is optional, strict 1..4294967295 and FILE-only; None is omitted, only for
  this newly introduced field. Preserve old canonical digests and retained bytes.
- FileId/volume identity never derives from a path. Exact path comparison guards
  hash lookup collisions. Full paths remain Text up to 32767 characters.
- Per-path removals and object/sole-path watermarks survive resurrection; older
  independent aliases remain admissible when no newer negative proof excludes them.
- No file-content reads, new dependencies, live service/AD/DNS changes or guessed pilot.
- Use disposable PostgreSQL and native temporary Windows fixtures. Backend/schema
  upgrades precede collector activation; full Windows runtime gates remain open.

## Review focus

1. An old accepted receipt must replay after upgrade without a 409 hash conflict.
2. Two collectors delivering independent aliases out of order must not lose one.
3. Stale inventory after deletion/resurrection must not reopen removed aliases.
4. Long paths and forced digest collisions must not bypass uniqueness or rollback.
5. Existing deleted/history rows and unsafe downgrade must retain reliable evidence.

## Task 1 — Compatible inventory count

Files: `packages/contracts/inventory.py`, create
`tests/backend/test_path_alias_contracts.py`, generated OpenAPI/frontend contract
files located through the existing generation scripts. Existing ingest digest and
outbox algorithms remain unchanged.
Interface: `FileObjectRecord.link_count: int | None`, omitted on None, FILE-only.

- [x] RED golden old record/envelope canonical JSON and SHA-256 against literal
  pre-upgrade fixtures; omitted/null count serialize identically. Positive counts
  serialize and alter digest. Reject bool/string/float/zero/overflow/directory count.
- [x] Implement only the additive field and validator; rerun the same tests GREEN.
- [x] Run existing contracts and outbox suites, strict DTO types, Ruff, and generated
  OpenAPI/frontend drift checks. Inspect full diff and commit the coherent DTO change.

## Task 2 — Per-path persistence and transitions

Files: `packages/shared/models/core.py`, `packages/shared/models/activity.py`,
create `migrations/versions/0005_object_path_aliases.py`, create
`packages/shared/ingest/paths.py`, modify `packages/shared/ingest/core.py`, create
`tests/backend/test_path_alias_ingest.py`, `tests/backend/test_path_alias_migration.py`.
Update schema/metadata exports if necessary.
Interfaces: `paths.observe(connection, object_id, path, at, *, name, parent_file_id, legacy_tie=False)`;
`paths.end(connection, object_id, path, at)`; `paths.sole(connection, object_id, path, at, *, strict=True)`;
`paths.delete(connection, object_id, at)`; `paths.representative(connection, object_id)`.
Helpers do not own transactions; conflicts roll back the existing ingest transaction.

- [x] RED actual PostgreSQL two aliases/two scans: one object, two active intervals;
  rename-one, path-delete, count1, whole-delete/resurrection, unchanged-path resurrection.
- [x] Implement state table/object watermarks, bounded migration/backfill and helper
  transitions; integrate inventory/change without global-old-alias discard. GREEN.
- [x] RED delayed independent aliases, equal-time deletion, stale changes and sole
  proofs, legacy unknown after explicit multiple, pre-inventory changes hydration.
  Implement event index/hydration and dated guards; rerun GREEN.
- [x] Verify stored pre-upgrade receipt replay, changed-count same-ID conflict, distinct
  collectors concurrent upload, forced digest collision rollback, 32767-char paths.
  Fix only demonstrated defects and rerun GREEN.
- [x] RED existing active/closed/deleted/resurrected migration rows; verify bounded backfill,
  safe round trip and unsafe-multipath downgrade refusal. Implement guards, GREEN.
- [x] Run full Linux/PostgreSQL backend/deployment, base/head/check migration checks,
  strict types/Ruff/OpenAPI. Inspect full diff and commit backend/schema capability.

Task2 evidence: actual Linux3.13/PostgreSQL16 full498 passed/17 native-only skips,
deployment46 passed, migration round trips/check, mypy84 source/7 deployment helpers,
Ruff/OpenAPI passed. Twenty-two PostgreSQL alias/temporal/replay/conflict cases and
three existing-row/keyset/downgrade cases passed. Golden DTO/outbox compatibility
passed. Initial alias cases, hydration, legacy ties/stale records, first-seen
chronology and object-delete inference were demonstrated RED before their fixes.
Path-only removal retains last-known identity without claiming whole-object deletion.
Native count publication, real Windows HTTPS acceptance and final review remainTask3.

## Task 3 — Native capture, delivery and acceptance

Files: `collectors/windows/native.py`, native/provider/integration tests, Windows
README and implementation/task status docs. Keep MULTIPLE_LINKS accepted in old
error/checkpoint contracts; stop emitting it solely for ordinary hard links.
Interface: native FileObjectRecord carries actual StandardInfo.NumberOfLinks.

- [ ] RED actual native hard-link fixture emits both paths/count2/same FileId;
  unlink-one gives count1 without opening file contents or traversing reparses.
- [ ] Remove the interim multi-link rejection and emit validated real FILE counts;
  rerun actual native/privacy/scope tests GREEN.
- [ ] RED actual strict-HTTPS/PostgreSQL repeated hard-link scans and unlink-one:
  one identity, stable active intervals, independent alias preservation. GREEN.
- [ ] Run full backend/deployment/migrations/types/lint/OpenAPI/frontend, installed
  packaging, public-source secrets checks. Document exact evidence and pending gates.
- [ ] One fresh whole-component review, re-grade, one RED/GREEN fix pass for important
  defects, no second review. Inspect and commit coherent capture/fix changes.
- [ ] Publish authorized main; verify exact remote SHA, clean status and all required
  exact-source CI jobs. Record acceptance without treating this as full Wave 1.
