# Audit and delivery recovery implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover the accepted scoped collectors without losing historical evidence, hiding gaps, or changing business file contents.

**Architecture:** Keep independent collector-push streams. Refresh blocked Audit diagnostics, derive proof freshness at the API boundary, and make protected status replacement tolerate bounded Windows sharing contention without weakening file validation. Diagnose inventory delivery and storage allocation before changing throughput or retention.

**Tech Stack:** Python 3.13, PostgreSQL, FastAPI/Pydantic 2, native Windows APIs, pytest.

**Spec:** `docs/tasks/storage-audit-001-windows-security-attribution.md`; existing acceptance ledgers.

## Global constraints

- Preserve accepted source payloads, native identity/session evidence, latched GAP and the original state/generation.
- Preserve parallel history and authorization work; no direct AI database queries or business file reads.
- No automatic rebaseline, invented attribution, weakened TLS/ACL validation, or destructive retention cleanup.
- Keep infrastructure evidence and exact SACL differences in excluded protected storage only.
- Keep the completed observation automation paused; repair is a separately requested operation.

## Review focus

- A stopped capture loop must not replay an indefinitely fresh readiness proof.
- A latched gap must survive successful later readiness and service restarts.
- Windows sharing contention must not relax hardlink/reparse/DACL checks; non-status access denial fails immediately.
- New proof projections must not rewrite stored heartbeat payloads or accepted correlations.
- Throughput/storage changes must preserve idempotency and dated path history.

## Task 1: Audit diagnostics and safe status publication

- [x] Add failing regression tests for blocked readiness refresh and protected status replacement under a genuine held Windows handle.
- [x] Implement bounded refresh while capture remains blocked, retaining GAP and never opening a subscription on an unproved scope.
- [x] Retry only transient sharing/lock failures when replacing an owned temporary status file; preserve validation and bounded failure.
- [x] Run native security, Audit runtime/service/readiness/delivery regressions.

## Task 2: API freshness fence

- [x] Add RED tests for a freshly received heartbeat carrying an old/future readiness timestamp.
- [x] Recompute readiness age in the response without modifying stored evidence; never promote stale proof to HEALTHY.
- [x] Verify legacy receipt compatibility, authorization, correlation and generated contracts.

## Task 3: Scope and resource root causes

- [x] Record the exact failed SACL objects and before/after metadata privately; diagnose physical allocation and queue work through permitted interfaces.
- [x] Reproduce throughput/storage defects with synthetic data before changing implementation.
- [x] Repair only proved causes; keep retention and existing history intact.

## Task 4: Publication and installed acceptance

- [x] Independent review, small logical PRs and exact-head/main CI before deployment.
- [x] Back up current state/configuration and verify rollback material before changing installed components.
- [x] Verify live API/UI, fresh proofs, independent USN continuity, queue progression and unchanged accepted witnesses.
- [x] Record observed acceptance and any remaining gate honestly in the ledgers; stop after acceptance.

## Rulings

- Ruling: native Windows replacement can return WinError 5 for a reader denying share-delete, not only 32/33. Retry that ambiguous code only for `audit-status.json`, revalidating destination and temporary file each time, with ten total attempts. Other filenames fail immediately on access denial. This preserves integrity and bounds a persistent denial to 450 ms of retry waits.
- Ruling: retain legacy heartbeat schemas and stored receipts. API freshness changes are response projections; accepted correlations and history are not recalculated.
- Ruling: Context7 quota was unavailable. Pinned library versions and installed API contracts remain authoritative; no dependency version changes are included.
