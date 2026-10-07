# MVP three-stage execution ledger — A / B / C

Контрольный журнал к docs/tasks/mvp-003-004-three-stage-delivery-train.md.

**GATE A PASS. Stage B начат после terminal CI финальной публикации A; C не начат.**

## Known baseline

- PR #7: merged into main at code SHA 07fbb9fdc31603a6309887684805ffb98ec5a9db.
- Issues #5 and #6: require explicit reconciliation/closure with operator acceptance evidence.
- Post-merge CI: check fresh terminal result, never infer from PR green.
- Existing Windows Collector: foreground wheel/CLI, tested live inventory/heartbeat.
- Current dashboard capacity: tested in real pilot; production SHA must be revalidated against main.
- User attribution and USN Activity: not implemented/accepted at this point.
- GitHub repository is public: no operational secrets/paths or internal data in this ledger.

## Stage A — main and operating MVP

GATE A: PASS

~~~text
Source SHA: dda125d08f97fac78ccea466ec89fd0ad6f79776
Merged main SHA: dda125d08f97fac78ccea466ec89fd0ad6f79776 (PR #9)
Exact push CI run: https://github.com/BorisDruzak/storage-console/actions/runs/37686825905
Tests: Python 3.13/PostgreSQL 16: 590 passed, 50 platform/integration skips;
       deployment 54 passed; Ruff, mypy (92+6 files), OpenAPI drift,
       upgrade/check/downgrade/upgrade/check PASS in isolated test schema.
       Frontend: 121 Vitest + 12 Playwright PASS; API generation check,
       lint/i18n negative control, TypeScript strict and Vite build PASS.
       Exact merged-main CI independently repeats full backend/frontend,
       Windows installed-wheel/CLI (14), Compose, production and secret gates.
Central deployed SHA: dda125d08f97fac78ccea466ec89fd0ad6f79776
Backup/rollback evidence: fresh pre/post-deploy PostgreSQL custom archives
       checked with pg_restore --list and SHA256; both external private copies
       hash/size verified. Config rollback copies and previous release/images
       preserved. Production DB/state/volumes/credentials retained.
Real Overview/capacity/inventory proof: fresh authenticated HTTPS API + native
       Chromium desktop/mobile/reload PASS; 1 source, 1 NTFS volume, 10146 objects;
       heartbeat HEALTHY, inventory COMPLETE after >5 minutes within 7200s TTL;
       measured capacity totals/percentage/worst-volume state verified;
       integrity/domains/overall UNKNOWN, default Asia/Yekaterinburg and saved UTC;
       no page/console errors. Raw evidence remains private.
Issue #5 state/evidence: CLOSED; https://github.com/BorisDruzak/storage-console/issues/5#issuecomment-6046967331
Issue #6 state/evidence: CLOSED; https://github.com/BorisDruzak/storage-console/issues/6#issuecomment-6046968071
Exceptions/Sonar: six required jobs terminal SUCCESS; Sonar SKIPPED (external
       configuration absent), not reported as a successful Quality Gate.
Operator confirmation: previous live operator acceptance documented in
       docs/implementation-status.md; repeated central/browser observation
       on 2026-10-08 (Asia/Yekaterinburg), without FILESERVER changes.
       Repeated live checks were performed after the main deployment;
       a subsequent HEALTHY heartbeat proves continued real ingestion.
Pending/quarantine: collector state was not reopened or changed by Stage A;
       no new live local queue-status claim; current central freshness verified.
Installed collector package: unchanged; no package upgrade/re-enrollment.
Known limits: Service/reboot and USN not implemented or accepted by Stage A.
Documentation publication: PR #10 merged at ef78111c0d2e8f971cb16f7b64a40c3f7cffd716;
       exact push CI https://github.com/BorisDruzak/storage-console/actions/runs/37688827452
       terminal SUCCESS for all six jobs, Sonar SKIPPED.
Next stage authorized: YES (B only; C still requires GATE B PASS).
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
and pre-deploy runtime `f12b345…` are ancestors of exact main. The later main
commits through `e65c048…` only add delivery-train documentation. Fresh runtime
inspection confirmed OCI image/container revision, all four healthy services,
strict HTTPS/redirect, anonymous read rejection, Alembic check and inventory TTL.
Safe update to accepted main `dda125d…` completed through the existing runbook
after verified backup. Post-deploy revision/image/health/TLS/auth/Alembic/7200s
TTL checks, fresh heartbeat, preserved identities and repeated strict-TLS browser
acceptance all PASS. Pre/post archives and external copies verified separately.

### Resolution of the original CI wait

The original `e65c048…` main run `37681158835` remained live at Chromium
installation when the initial checkpoint was published. It was not declared
failed, cancelled or restarted solely because observation elapsed. Local tests
did not replace its missing terminal result.

Stage A [PR #9](https://github.com/BorisDruzak/storage-console/pull/9) final head
`caca737b3be28d0171db323fde300ccf32519bdd` passed all six jobs in
[PR CI 37684335711](https://github.com/BorisDruzak/storage-console/actions/runs/37684335711).
It was reviewed and merged normally into `dda125d…`; the trees are identical.
The subsequent **push** CI on that exact merged main SHA completed SUCCESS
for all six mandatory jobs, with Sonar SKIPPED. No check was disabled and no
runtime code change was needed for Stage A. Deployment and issue reconciliation
followed that exact-main result, not a substitute PR-only result.

Ruling: Source/deployed SHA above identifies the accepted runtime. Final
documentation-only publication has its own immutable PR head/merge checks;
verify those before starting B, without rewriting acceptance merely to reference
the commit that contains its own text. Do not claim central was deployed to a
later documentation revision unless it was actually observed.

Installed collector package/state and local pending/quarantine were not changed
or independently reopened during Stage A. Live FILESERVER freshness and inventory
were observed through the central API/browser. No FILESERVER SSH session, service
lifecycle, reboot, ACL/SMB/audit-policy/USN configuration changes were performed.
No Stage C work has started. No approval request for FILESERVER reboot is made
before a concrete Stage B implementation and its required native acceptance.

## Stage B — Windows Service

GATE B: BLOCKED — publication/exact-SHA CI and approved live handover/reboot pending

Baseline: `ef78111c0d2e8f971cb16f7b64a40c3f7cffd716`, exact main push CI
`37688827452` terminal SUCCESS (six jobs, Sonar SKIPPED). Deployed central
baseline remains `dda125d08f97fac78ccea466ec89fd0ad6f79776`, live accepted.
Scope/negative tests/risks and ordered execution:
[Stage B plan](../superpowers/plans/2026-10-08-windows-service-stage-b.md).
Design/RED phase; no real FILESERVER service installation or reboot authorized
or performed by this checkpoint.

Implementation verified before publication (not a gate verdict): native own-process SCM adapter,
thin dispatcher over existing Runtime, lifecycle CLI and read-only privileged
installation validation. LocalSystem/delayed start/one crash restart configured;
existing state/binding/auth suspension preserved. No new runtime dependency.

RED observed: service verbs rejected by old CLI; queued crash recovery falsely
reported as operator stop; external `.pth` dependency skipped by installation
checks; a nested venv's ancestor cache skipped the base interpreter; failed cleanup
could wait on a non-daemon thread; BaseException leaked across a ctypes callback.
Targeted corrections GREEN (32 lifecycle tests at this
checkpoint). Failed registration uninstall has a separate deletion path.

Verification history and final frozen-source evidence:
- Linux immutable source archive v1: SHA256
  `6b0b4055c6935f8e972381d7fca0303aa966bf5a156fc525eece401adb69ce2d`;
  Python 3.13/PostgreSQL 16 backend 615 passed / 56 skipped, deployment 54 passed;
  Ruff, mypy (96 + 6 source files), OpenAPI, migration upgrade/check/round-trip
  passed. Later corrections require the final full regression.
- Unchanged frontend tree: api:check, lint/i18n negative control, typecheck,
  121 Vitest tests, build and 12 Playwright tests passed.
- Owned local synthetic Windows fixtures (Python 3.14; target 3.13 still requires
  Windows CI): queried SCM configuration, disabled/idempotent registration,
  foreground lock rejection, actual LocalSystem token/DPAPI/strict TLS,
  outage/replay, stop/start binding/checkpoints, auth suspension preservation,
  one crash restart/no storm passed in targeted runs. Actual service → strict
  HTTPS API → isolated PostgreSQL persisted heartbeat and inventory. A fresh
  protected installed wheel outside checkout passed the operator CLI lifecycle
  including repeated install/start/status/stop/uninstall; config/binding retained.
- Immutable v2 follow-up: Linux Python 3.13/PostgreSQL 16 backend 620 passed /
  58 skipped; deployment 54 passed; quality checks and migration round-trip passed.
  Archive SHA256 `a55fc61ed01c22517fbd24f22458f7763386e45c5ce3b5d36ad61ff9e7a5f115`.
  Windows collector/native regression 314 passed / 5 skipped. The subsequent
  registered-custom-state CLI correction requires another final full regression.
- Installed-wheel rollback to accepted Stage A package (public source
  `ef78111c0d2e8f971cb16f7b64a40c3f7cffd716`) passed: service uninstall, previous
  wheel restore, foreground heartbeat, unchanged config/binding/checkpoints.
  Test-fixture dependency copying initially omitted pip's vendor directory; RED
  corrected and actual operator lifecycle/rollback GREEN (1 passed, 54.35 s).
- Extra optional Windows Python 3.14 all-backend run: 1 failed / 376 passed /
  13 skipped. Existing read-validity test's two-second window expired over remote
  PostgreSQL. Failure reproduced on Stage A source; API/test unchanged by B.
  Required Linux target full regression passed; this extra run is not represented
  as a success. No unrelated API change made to hide the timing failure.
- Independent fresh-context whole-stage review: no verified Critical/Important
  findings in all 13 files; reviewer ran 32 portable lifecycle tests and checked
  diff whitespace. Reviewer did not execute native/production acceptance.
- Final immutable v3 source archive: SHA256
  `a7319f5978c6d24404a2e7b7b8605abdf7e33b47052ac9e0f69792f1455a1129`.
  Python 3.13.16/PostgreSQL 16 full backend 622 passed / 58 skipped /
  59 warnings (296.10 s); deployment 54 passed. Ruff, mypy (96 + 6), OpenAPI,
  migration upgrade/check/downgrade/upgrade/check passed; Gitleaks 8.24.3 found
  no leaks. Linux skips are native Windows checks, covered by Windows acceptance.
  Final Windows collector/native regression completed successfully: 316 passed /
  5 skipped, two dependency deprecation warnings. SKIP: POSIX ACL/symlink/owner
  checks (4), unsupported-platform negative test on Windows (1). All new native
  SCM checks executed. No owned fixture services remain after cleanup.
- No native reboot or FILESERVER live handover performed. Synthetic fixtures
  create only their own private objects/registrations, not existing ACL changes.

Operator checklist/rollback:
[Windows Service](../pilot/windows-service-ru.md).
Next: separate draft PR/exact SHA CI/merge CI → concrete operator approvals and
live acceptance. Full frozen-source regression and independent review completed.
Stage C remains unauthorized until GATE B PASS.

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
