# STORAGE-AUDIT-001 implementation plan

Execution: inline implementation; independent reviewer for each stage. The user
has supplied and authorized the design in `docs/tasks/storage-audit-001-windows-security-attribution.md`.

**Goal:** Independent minimal Windows Security evidence and explainable USN attribution.
**Architecture:** A separate own-process SCM service owns protected state, a strict
Security bookmark and an encrypted durable queue. Central immutable evidence and
versioned asynchronous candidate matching are additive to existing USN history.
**Tech stack:** Python >=3.13, native Win32 Event Log/SCM/DPAPI, PostgreSQL 16,
FastAPI/Pydantic 2, React/TypeScript/i18n.

## Constraints and review focus

- A PASS precedes B; B PASS precedes live C. CI alone is never live acceptance.
- No FILESERVER installation, policy/SACL/GPO changes or test file operations without
  separate explicit operator approval. No reboot, 5145, WEF, SIEM, restore or blanket audit.
- All fixtures synthetic; no private topology, identity, XML, paths or tokens published.
- Preserve Issue #22 history/RBAC and original USN-SOAK-001 FAIL.
- Review stale bookmarks/clear and reused IDs, scope aliases/reparse uncertainty,
  lost ACK and atomic cache/checkpoint, handle/logon reuse across boots,
  two users and missing client data. Missing proof remains UNKNOWN/AMBIGUOUS.

## A: independent collector (PR A)

Files: new `collectors/windows_audit/{events,scope,store,native,configuration,runtime,scm,service,cli}.py`,
`tests/backend/test_windows_audit*.py`, Windows CI selection, packaging entry point,
collector runbook and the acceptance ledger. Existing USN implementation is not changed.

- [ ] Write parser/privacy tests: named XML fields, 4660 without path, 4624 missing
  IP, 1102, unknown provider/version, Cyrillic and file versus registry; run RED.
- [ ] Implement `parse_event(xml, host_id, boot_id, generation) -> AuditEvent` and
  bounded scope/session/handle selection with no out-of-scope transmission.
- [ ] Write crash/restart/lost ACK and capacity tests; run RED. Implement an independent
  SQLite queue with encrypted bodies/cache and atomic bookmark advancement.
- [ ] Write strict native resume/clear/bounds tests; run RED. Implement bounded pull
  subscription with EvtCreateBookmark/EvtUpdateBookmark/EvtRender/EvtNext and strict
  EvtSubscribe; latch AUDIT_GAP rather than silently choosing a new generation.
- [ ] Write independent SCM/config tests; run RED. Implement separate service name,
  machine DPAPI credentials, protected installation/state, fixed-code diagnostics,
  installation/status/upgrade/rollback runbook and bounded shutdown.
- [ ] Read-only preflight; sanitized results only. Native disposable Windows CI:
  installed wheel, own SCM/LocalSystem, DPAPI and Security bookmark/replay.
- [ ] Run focused and relevant regression, lint/type/secret checks; independent
  Critical/Important review; separate draft PR; exact PR/main CI; record GATE A.

## B: central evidence and correlation (PR B; only after A PASS)

Files: additive contracts/models/ingest, minimal Alembic revision, indexed worker
correlation, admin-only read routes, separate stream freshness, generated API types,
i18n UI/tests. Re-read current main and Issue #22 before touching Activity/RBAC.

- [ ] RED immutable identity/replay/conflict/auth tests, then implement independent
  AUDIT_WINDOWS registration and `/api/v1/ingest/audit-events` on the existing source.
- [ ] RED 0/1/2 collector freshness matrix, then USN-only continuity and separate audit health.
- [ ] RED out-of-order/handle/logon/boot/multiuser/rename/delete tests, then versioned
  bounded asynchronous many-to-many matching with rejection reasons and provenance.
- [ ] RED admin/viewer 401/403/200 and secure POST filters, then evidence read API and
  Russian admin desktop/mobile UI distinguishing access from inferred actor.
- [ ] Migration roundtrip, 100k synthetic query plans, strict HTTPS/PG actual ingest,
  existing backend/Windows/Web regression and real Playwright; focused review and exact CI.
- [ ] Verified external backup and rollback before central deploy; confirm exact
  deployed SHA, preserved USN freshness; record GATE B.

## C: separately approved pilot (PR C / sanitized acceptance)

- [ ] Prepare private operator plan for one disposable folder, two accounts and two
  PCs, narrow Success SACL, effective GPO ownership, estimated volume, stop criteria,
  package/DB rollback and explicitly approved cleanup/service disposition.
- [ ] Without approval: GATE C BLOCKED; request exact authorization. No live changes.
- [ ] After approval only: each account performs SMB CREATE/WRITE/RENAME/DELETE;
  demonstrate real 4663/4624/4660 and USN, ambiguity and missing-client behavior,
  Audit restart/replay, unchanged existing USN, admin UI/RBAC and approved rollback.
- [ ] Record private evidence references and sanitized exact-SHA acceptance; STOP.
