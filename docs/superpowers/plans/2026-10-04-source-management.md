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
`tests/backend/test_source_transport.py`, `apps/web/src/api/source-contracts.test.ts`;
modify `apps/api/main.py`, `tests/backend/test_openapi.py`, generated OpenAPI/TS files via
`apps/web/scripts/generate-api.mjs` (confirm actual generator entrypoint before invoking).
Consumes Task1 contracts; existing Engine, Actor, require_permission/require_csrf and token_hash.
Registry functions: register_source(engine,actor,data)->SourceRegistration;
enroll_collector(engine,actor,source_id,data)->CollectorCredential;
rotate_collector(engine,actor,id)->CollectorCredential;
set_collector_enabled(engine,actor,id,data)->CollectorView;
list_collectors(engine,source_id,limit,offset)->Page[CollectorView]. RegistryError(status,detail).

- [x] RED PostgreSQL tests: UUID/immutable natural identity duplicate+concurrency, type pairing,
  missing resources, hash-only persistence/audit-empty-details, failed audit rollback,
  rotation/replayed batch rejection, disabled explicit re-enable, concurrent ingest serialization.
- [x] Implement transactional registry/locks, fixed audit actions, PG conflict returning semantics.
- [x] RED HTTP tests with real sessions: all read roles/admin writes, bearer401/viewer403,
  Origin/CSRF negatives/current roles, actual streamed16KiB/415/422/no-store, safe database503.
- [x] Implement router/transport with exact spec endpoints, dependency admission and error mapping.
- [x] Generate/check OpenAPI/types; test UserSession security and response token separation.
- [x] GREEN full Linux3.13/PG16 suite/migration roundtrip/check, Ruff/mypy/pipcheck;
  inspect diff and commit `feat(sources): add audited source and collector management`.

## Task3 — Console lifecycle and final acceptance

Files: modify `apps/web/src/pages/SourcesPage.tsx`, `apps/web/src/api/client.ts`;
create `apps/web/src/sources/{client,SourceRegistrationForm,CollectorControls}.tsx/ts`
and focused adjacent tests; modify `packages/i18n/{ru-RU,en-US}.json`,
`tests/deployment/browser_auth.mjs`, `tests/deployment/smoke_production.py`,
`docs/implementation-status.md`, `docs/tasks/README.md`, this plan.
Consumes generated types and current session Actor, query invalidation/client401 semantics.

- [x] RED translated admin forms, other-role metadata-only, create/enroll/rotate/disable,
  pending/resubmit/failure, one-time token close/unmount/session changes and stale response tests.
- [x] Implement focused components; token never in query cache/browser storage/logs.
- [x] GREEN frontend tests/typecheck/lint/i18n/build/APIcheck/npm audit and existing E2E.
- [x] Extend strict-TLS disposable browser acceptance: register/read/enroll/ingest heartbeat,
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

Task2 registry RED missing module → PostgreSQL9 GREEN; HTTP13 RED (absent routes) →24 GREEN
including lock/role/CSRF/replay/atomic audit tests, then stable pagination and duplicate Origin.
Full Linux3.13/PostgreSQL16 backend286 PASS, migration base→head/check→base→head/check,
deployment46/Ruff/mypy72/pipcheck PASS. Final schema/frontend generation changes: selected85
backend PASS, frontend84/typecheck/lint/build/APIcheck PASS. Standalone token validator RED
(absent exports, then unbounded string) → GREEN after management-tag inclusion and explicit
43-character token schema. Namespace transport RED intercepted similar prefix → five GREEN;
latest Linux selected transport/HTTP/OpenAPI22 and Ruff/mypy72 PASS. Gitleaks1.16MB PASS.
All pre-existing OpenAPI operations and schemas compared equal; five new management operations.
Windows mypy reports POSIX-only auth APIs; authoritative Linux typing passes without bypass.
Task2 опубликован в `adc8ad20088d26f2595b2132702ab81780c2ecbe`.
[CI37176997771](https://github.com/BorisDruzak/storage-console/actions/runs/37176997771)
terminal SUCCESS: все пять обязательных jobs; Sonar SKIPPED (внешний gate).
Финальные CI logs подтверждают backend291/deployment46/mypy72/strict deploy6,
OpenAPI match и Alembic check.

Ruling: include generated response validators in Task2 alongside API types — future controls
must consume bounded, typed credentials rather than an unvalidated wire string. Cost: small
additional browser bundle until Task3 uses these management validators; no new dependency.

Task3 console: client RED missing import/promised identity errors → GREEN9; initial
components RED absent imports → GREEN5, extended authority/session/race coverage →112.
Whole-feature review: two Important. First committed enrollment/source registration with
lost response leaves a cached empty list; second newly issued key lacks its matching UUID
when the collector is outside the current page. Three regression tests RED → GREEN31
focused source tests, full frontend115 PASS. Uncertain results now refresh only metadata
GETs; credential issuance is never retried. The key panel displays its returned collector UUID.
Linux3.13/PG16 backend291, migration round-trip/check, deployment46, Ruff/mypy72/strict deploy6,
OpenAPI/pipcheck PASS. Frontend types/lint/i18n/build/APIcheck/audit0, shell E2E11,
Gitleaks and eight ShellCheck scripts PASS. Fresh disposable strict-TLS production/browser
acceptance includes a real committed enrollment with its response deliberately discarded,
metadata reconciliation and explicit rotation, then old401/new202/disable401/re-enable202,
source freshness/reload/mobile/auth/session/backup/restore. Controls screenshots contain no keys.
Final new main publication and exact terminal CI remain pending until observed.

Ruling: out-of-band role changes are learned through session restore/events or denied writes;
known role changes clear keys and every write enforces current server permissions. No new
background role polling is introduced here. Cost: an already-issued key may remain displayed
until the client learns of the change; rotation/disable independently revoke collector access.
Ruling: absent Storage Console GitNexus index means source/contracts/tests are authoritative;
no index/group synchronization is fabricated. Cost: indexed impact proof is unavailable.
Primary deployment/live AD/DNS and full runtime/outbox/Waves1–8 remain required later gates.
Deferred minor: collector last_seen_at currently has a heartbeat label even though any ingest
updates it. It is metadata, not the source freshness calculation; no health behavior was changed.
