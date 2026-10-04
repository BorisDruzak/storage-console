# Wave 1 source management implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline task-by-task. No per-task
> implementer/reviewer agents; one fresh whole-feature review at the end.

**Goal:** Let administrators register sources and enroll, rotate and disable collectors
through the authenticated console, with working existing heartbeat/inventory ingest.

**Architecture:** Typed control contracts feed a transactional registry on the existing
source/collector tables. User-session permission/CSRF protects writes, separate bearer
authentication protects ingest. The console keeps one-time credentials only in memory.

**Tech Stack:** Python3.13, FastAPI0.142.2, Pydantic2.13.5, SQLAlchemy2.0.54, PostgreSQL16,
React/TypeScript and repository Playwright (versions from lockfiles).

**Spec:** `docs/superpowers/specs/2026-10-04-source-management.md`; canonical §6–10/25/26/34.

## Global constraints

- Main/inline execution and publication already authorized for the canonical specification.
- Preserve evidence/freshness semantics, immutable identity, RU/en-US and collector auth boundary.
- No web filesystem access, provider mutations or autonomous remediation.
- Secrets/internal topology stay outside public Git; generic errors, no-store, bounded input.
- Consult Context7 for external APIs; GitNexus lacks this repository (live checked).
- Primary runtime cutover, live AD/DNS/observability and remaining Waves1–8 stay separate gates.

## Review focus

1. Lost enrollment/rotation response: explicit subsequent rotation, no token replay store.
2. Concurrent ingest and rotate/disable: consistent locking and no revoked-token resurrection.
3. Role/session changes with open credential panel: clear memory and gate stale operations.
4. Unicode/control/oversized or chunked input: bounded generic rejection without input echo.
5. Database audit failure: rollback mutation and return generic503; no unaudited success.

## Task1 — Control contracts

Files: create `packages/contracts/sources.py`, `tests/backend/test_source_contracts.py`.
Interfaces: CreateSource(source_type,hostname,fqdn,instance_id,expected_cadence_seconds);
SourceRegistration(identity/metadata/cadence/created_at); CreateCollector(collector_type);
CollectorView(id,source_node_id,collector_type,version,enabled,created_at,last_seen_at);
CollectorCredential(CollectorView,token:SecretStr); RotateCollector(empty); SetCollectorEnabled(enabled).

- [x] Write failing tests for unsupported enums/extra fields, strict cadence1..86400 and bool,
  bounded text/control/Unicode, UTC, no credential in views/repr/Python dumps and JSON-only token.
- [x] Run `.venv/Scripts/python -m pytest tests/backend/test_source_contracts.py -q` (RED).
- [x] Implement bounded typed contracts, JSON-only serializer and no coercion of enabled/cadence.
- [x] Run contract tests plus existing contracts (GREEN), Ruff/mypy and OpenAPI check.
- [x] Inspect complete diff/check; commit `feat(sources): define source management contracts`.

## Task2 — Registry and authenticated HTTP boundary

Files: create `apps/api/source_control/{__init__,registry,routes,transport}.py`,
`tests/backend/test_source_registry.py`, `tests/backend/test_source_control.py`;
modify `apps/api/main.py`, `tests/backend/test_openapi.py`, generated OpenAPI/TS files via
`apps/web/scripts/generate-api.mjs` (confirm actual generator entrypoint before invoking).
Consumes Task1 contracts; existing Engine, Actor, require_permission/require_csrf and token_hash.
Registry functions: register_source(engine,actor,data)->SourceRegistration;
enroll_collector(engine,actor,source_id,data)->CollectorCredential;
rotate_collector(engine,actor,id)->CollectorCredential;
set_collector_enabled(engine,actor,id,data)->CollectorView;
list_collectors(engine,source_id,limit,offset)->Page[CollectorView]. RegistryError(status,detail).

- [ ] RED PostgreSQL tests: UUID/immutable natural identity duplicate+concurrency, type pairing,
  missing resources, hash-only persistence/audit-empty-details, failed audit rollback,
  rotation/replayed batch rejection, disabled explicit re-enable, concurrent ingest serialization.
- [ ] Implement transactional registry/locks, fixed audit actions, PG conflict returning semantics.
- [ ] RED HTTP tests with real sessions: all read roles/admin writes, bearer401/viewer403,
  Origin/CSRF negatives/current roles, actual streamed16KiB/415/422/no-store, safe database503.
- [ ] Implement router/transport with exact spec endpoints, dependency admission and error mapping.
- [ ] Generate/check OpenAPI/types; test UserSession security and response token separation.
- [ ] GREEN full Linux3.13/PG16 suite/migration roundtrip/check, Ruff/mypy/pipcheck;
  inspect diff and commit `feat(sources): add audited source and collector management`.

## Task3 — Console lifecycle and final acceptance

Files: modify `apps/web/src/pages/SourcesPage.tsx`, `apps/web/src/api/client.ts`;
create `apps/web/src/sources/{client,SourceRegistrationForm,CollectorControls}.tsx/ts`
and focused adjacent tests; modify `packages/i18n/{ru-RU,en-US}.json`,
`tests/deployment/browser_auth.mjs`, `tests/deployment/smoke_production.py`,
`docs/implementation-status.md`, `docs/tasks/README.md`, this plan.
Consumes generated types and current session Actor, query invalidation/client401 semantics.

- [ ] RED translated admin forms, other-role metadata-only, create/enroll/rotate/disable,
  pending/resubmit/failure, one-time token close/unmount/session changes and stale response tests.
- [ ] Implement focused components; token never in query cache/browser storage/logs.
- [ ] GREEN frontend tests/typecheck/lint/i18n/build/APIcheck/npm audit and existing E2E.
- [ ] Extend strict-TLS disposable browser acceptance: register/read/enroll/ingest heartbeat,
  rotate old/new bearer checks, disable/re-enable, source fresh, token closed before screenshots.
- [ ] Full backend/deployment/migrations/typing, frontend and secrets checks; one fresh whole-feature
  review, meaningful RED→GREEN fixes only; publish main and verify exact terminal required CI.
- [ ] Update actual acceptance/remaining Wave1 runtime work and commit
  `feat(web): manage sources and collector credentials in console` (split independent fixes).

## Rulings and execution evidence

Approved full scope already permits these reversible source changes and main pushes. This
plan elaborates Wave1; no new approval loop is needed. New collector runtime/outbox/Windows,
PVE and PBS inventory will have separate subsystem plans after this management deliverable.

Task1 RED missing-module collection → GREEN66 contract tests on Linux3.13 and localPython3.14. Ruff public apps/packages/tests PASS; Linux mypy68/pipcheck and frontend api:check PASS. JSON secret serializer verified against pinned Pydantic2.13.5; no new API route or source registry runtime yet.
