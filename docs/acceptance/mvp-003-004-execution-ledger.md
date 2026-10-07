# MVP three-stage execution ledger — A / B / C

Контрольный журнал к docs/tasks/mvp-003-004-three-stage-delivery-train.md.

**Stage A BLOCKED на обязательном exact-main CI. Переход к B/C запрещён.**

## Known baseline

- PR #7: merged into main at code SHA 07fbb9fdc31603a6309887684805ffb98ec5a9db.
- Issues #5 and #6: require explicit reconciliation/closure with operator acceptance evidence.
- Post-merge CI: check fresh terminal result, never infer from PR green.
- Existing Windows Collector: foreground wheel/CLI, tested live inventory/heartbeat.
- Current dashboard capacity: tested in real pilot; production SHA must be revalidated against main.
- User attribution and USN Activity: not implemented/accepted at this point.
- GitHub repository is public: no operational secrets/paths or internal data in this ledger.

## Stage A — main and operating MVP

GATE A: BLOCKED — нет terminal PASS обязательного exact-main CI.

~~~text
Source SHA: e65c04863a4311e478b0d08218603add412e94a8
Merged main SHA: e65c04863a4311e478b0d08218603add412e94a8
Exact push CI run: https://github.com/BorisDruzak/storage-console/actions/runs/37681158835
Tests: Python 3.13/PostgreSQL 16: 590 passed, 50 platform/integration skips;
       deployment 54 passed; Ruff, mypy (92+6 files), OpenAPI drift,
       upgrade/check/downgrade/upgrade/check PASS in isolated test schema.
       Frontend: 121 Vitest + 12 Playwright PASS; API generation check,
       lint/i18n negative control, TypeScript strict and Vite build PASS.
Central deployed SHA: f12b345ecd660618fce35f11ff4f3fb0dc05a529
Backup/rollback evidence: pre-deploy PostgreSQL custom archive checked with
       pg_restore --list and SHA256; external private copy hash/size verified.
       Config rollback copy and previous release/images preserved.
Real Overview/capacity/inventory proof: fresh authenticated HTTPS API + native
       Chromium desktop/mobile/reload PASS; 1 source, 1 NTFS volume, 10146 objects;
       heartbeat HEALTHY, inventory COMPLETE after >5 minutes within 7200s TTL;
       measured capacity totals/percentage/worst-volume state verified;
       integrity/domains/overall UNKNOWN, default Asia/Yekaterinburg and saved UTC;
       no page/console errors. Raw evidence remains private.
Issue #5 state/evidence: OPEN; awaiting exact-main CI before reconciliation.
Issue #6 state/evidence: OPEN; awaiting exact-main CI before reconciliation.
Exceptions/Sonar: backend/windows-pilot/compose-smoke/production-smoke/secrets
       SUCCESS; frontend IN_PROGRESS at Chromium installation; E2E pending.
       Sonar not terminal in this run; adjacent accepted main runs report
       SKIPPED, never counted as PASS for the current run.
Operator confirmation: previous live operator acceptance documented in
       docs/implementation-status.md; repeated central/browser observation
       on 2026-10-08 (Asia/Yekaterinburg), without FILESERVER changes.
Next stage authorized: NO
~~~

Stage A independent read-only source review: no Critical/Important findings.
Verified empty-data UNKNOWN, inventory/heartbeat independence, measured current
capacity, integrity independence, timezone/reload and revision ancestry. Minor:
inherited Markdown hard breaks in task documents; no runtime effect, unchanged.
Reviewer did not independently execute live acceptance; live proof above comes
from the separate repeated API/browser checks, not the source review.

RED→GREEN повторён без изменения runtime: одна и та же synthetic inventory
старше пяти минут и младше 7200 секунд даёт STALE на pre-dashboard baseline
`153662178058f3f5debc69f524ac521be75091c4` (RED) и COMPLETE на exact source
`e65c04863a4311e478b0d08218603add412e94a8` (GREEN). Local Python 3.14 portable
dashboard checks: 7 passed/12 PostgreSQL skips; полный PostgreSQL regression
выше выполнялся отдельно на целевом Python 3.13, без этих portable skips.

PR #7 MERGED at `07fbb9fdc31603a6309887684805ffb98ec5a9db`; both that revision
and current deployed `f12b345…` are ancestors of exact main. The later main
commits through `e65c048…` only add delivery-train documentation. Fresh runtime
inspection confirmed OCI image/container revision, all four healthy services,
strict HTTPS/redirect, anonymous read rejection, Alembic check and inventory TTL.
Update to exact main and post-deploy backup are pending terminal source CI.

### Exact blocker and resumption

At the checkpoint, main push run `37681158835` still reports frontend
`IN_PROGRESS` on `npx playwright install --with-deps chromium`, without a
terminal result. GitHub does not yet expose that running job's final log.
Do not infer a download/network failure or weaken/skip the installation gate.
Local Playwright PASS does not replace exact-main CI. Draft Stage A
[PR #9](https://github.com/BorisDruzak/storage-console/pull/9) preserves evidence;
its CI also must be accepted on its final head, not on an earlier revision.

Required next action: obtain terminal results of main push run `37681158835`.
If it fails, inspect its actual failure log, reproduce the cause and apply only
a scoped RED→GREEN correction or justified rerun; preserve all six required jobs.
If it succeeds, safely update central to accepted main after rechecking backup,
verify exact deployed image/container revision, strict HTTPS/auth/migration and
repeat live browser checks; create/verify post-deploy and external backup copies.
Only then reconcile Issues #5/#6 with evidence, finish the Stage A PR and verify
CI on its exact merged main SHA before marking GATE A PASS.

Installed collector package/state and local pending/quarantine were not changed
or independently reopened during Stage A. Live FILESERVER freshness and inventory
were observed through the central API/browser. No FILESERVER SSH session, service
lifecycle, reboot, ACL/SMB/audit-policy/USN configuration changes were performed.
Stages B/C have not started. No approval request for FILESERVER reboot is made
before a concrete Stage B implementation and its required native acceptance.

## Stage B — Windows Service

GATE B: PENDING

~~~text
PR:
Source SHA:
Merged SHA:
Exact push CI:
Installed wheel SHA/version:
Service name / start mode:
Service identity + DPAPI validation:
Install/stop/start/idempotency:
Foreground handover:
Network outage/backlog:
Controlled real service trial:
Real FILESERVER reboot approved:
Real FILESERVER reboot acceptance:
Rollback verified:
Next stage authorized:
~~~

Do not mark PASS without explicitly approved real reboot acceptance.

## Stage C — NTFS USN to real Activity

GATE C: PENDING

~~~text
PR:
Source SHA:
Merged SHA:
Exact push CI:
Win32 native USN tests:
JournalID/cursor durability:
Scope containment:
Create/Write/Rename/Delete evidence:
Ancestor rename and last-known delete path:
Replay/restart/gap acceptance:
GET /api/v1/activity API:
Russian Web/Playwright:
Measured real latency:
Operator-approved synthetic test folder:
Heartbeat/inventory regression:
Rollback:
Stop/development complete:
~~~

## Rules for updates

- Change only own gate after verifying relevant evidence.
- Describe failures as FAIL or BLOCKED, never ambiguous success.
- Cite exact action URLs/commit SHAs.
- Never paste real production filenames, credentials, raw paths or diagnostics.
- Separate disposable environment tests from live FILESERVER acceptance.
- Do not advance B without A PASS, or C without B PASS.
