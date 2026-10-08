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

GATE B: BLOCKED — approved live service trial completed; separate real reboot approval/acceptance pending

Code checkpoint: [PR #11](https://github.com/BorisDruzak/storage-console/pull/11)
merged as `c28ef069236a67da2f03bbaa5637fa29e7b88002`.
[Corrected head CI 37702270249](https://github.com/BorisDruzak/storage-console/actions/runs/37702270249)
on `60ad7a8a3980b726d47be57c42a4ddb3e8a9a08a` and
[exact merged-main push CI 37702965026](https://github.com/BorisDruzak/storage-console/actions/runs/37702965026)
on `c28ef069236a67da2f03bbaa5637fa29e7b88002`: all six required jobs SUCCESS;
Sonar SKIPPED (external configuration absent). Main CI: backend 622 passed /
58 skipped / 79 warnings (coverage run, 251.59 s), deployment 54 passed;
frontend 121 Vitest + 12 Playwright; Windows Python 3.13 installed CLI14 and
SCM/runtime/real HTTPS/PostgreSQL43 passed, no Windows-native skips.

Release artifact built with Python 3.13 from this exact merged main:
`storage_console-0.1.0-py3-none-any.whl`, 123630 bytes, SHA256
`6cbdfffb64fb84fcbd9e7fc3b2a8969f37da50ba11bcbb8ad482d34bff86657a`.
All 98 Python modules byte-equal committed main source. Source archive SHA256
`57faf35ad15b01c8fb67b6a2ed8686781a42baa3ec18d379060de47b3493a952`.
Rollback artifact from accepted Stage A `ef78111c0d2e8f971cb16f7b64a40c3f7cffd716`:
113091 bytes, SHA256 `86caf133b2de1b7e6cb18a7f08943858c4d549bb0c656ef53c58432e9d8698f8`.
These exact final files passed installed protected-wheel operator CLI lifecycle
→ uninstall → previous wheel → foreground rollback, with setup-python alias
configuration reproduced in an owned directory (1 passed, 61.03 s). Config,
credential binding, identity and heartbeat continuity retained. Local native
artifact probe used Python 3.14; target Python 3.13 additionally passed main CI.

The final Stage B artifact is now installed on FILESERVER after the user's explicit
handover instruction; the Stage A rollback artifact and previous actual installed
runtime are retained. Current central runtime stays
accepted Stage A `dda125d08f97fac78ccea466ec89fd0ad6f79776`; API/OpenAPI/schema
unchanged by B, no central deployment needed. Live handover, stop/start, pending/
quarantine/freshness are verified below. No-login boot recovery remains NOT VERIFIED.
Actual previous live interpreter/package and a protected SQLite rollback copy
were retained before the handover.
Read-only central recheck at the B code checkpoint: four existing services
healthy, API APP_RELEASE and API/web image tags still the accepted Stage A SHA.
Prepared sanitized operator bundle `issue8-stage-b-operator-c28ef06.zip`, SHA256
`8a26b643ee03a1a8c83637b2b7dfa7b6688437b28f087c0f897e4d9f9901f26b`:
final/rollback wheels, pinned requirements, manifest and Russian instructions;
no production state/CA/credentials/data. Its sealed manifest records the original
pre-installation code checkpoint; use this ledger for the subsequent live verdict.

Baseline: `ef78111c0d2e8f971cb16f7b64a40c3f7cffd716`, exact main push CI
`37688827452` terminal SUCCESS (six jobs, Sonar SKIPPED). Deployed central
baseline remains `dda125d08f97fac78ccea466ec89fd0ad6f79776`, live accepted.
Scope/negative tests/risks and ordered execution:
[Stage B plan](../superpowers/plans/2026-10-08-windows-service-stage-b.md).
Design/RED phase; no real FILESERVER service installation or reboot authorized
or performed by this checkpoint.

Implementation merged/verified (not a live gate verdict): native own-process SCM adapter,
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
- Publication candidate: [PR #11](https://github.com/BorisDruzak/storage-console/pull/11),
  branch `codex/issue8-stage-b-service` → `main`, implementation source
  `00d66e179a6e0c73aff79c5d83e2b7ab78a67925`.
  [Exact head CI 37700362175](https://github.com/BorisDruzak/storage-console/actions/runs/37700362175)
  FAILED: backend/frontend/compose-smoke/production-smoke/secrets succeeded;
  Windows protected-interpreter fixture rejected setup-python's root
  `python3.exe` reparse alias. Sonar SKIPPED (external configuration absent).
  Narrow fixture correction skips only unused root versioned aliases; actual
  `python.exe`/all other reparse points remain rejected. Independent correction
  review found no Important defect. The subsequently completed v4 regression and
  corrected-head/main CI are recorded separately above. No live CI job was
  cancelled/restarted on an observer timeout.
  Setup-python alias configuration reproduced in a new owned interpreter source
  with both versioned symlinks: exact-artifact lifecycle/rollback GREEN
  (1 passed, 60.90 s). Actual base interpreter and existing ACLs untouched.
- Post-correction immutable v4 source archive SHA256:
  `f773b689a9a075f66091ab1fd231c710acb19baa828d9d05d307deba15810c81`.
  Full Linux Python 3.13.16/PostgreSQL 16 backend 622 passed / 58 skipped /
  59 warnings (296.00 s); deployment 54 passed; Ruff/mypy/OpenAPI and migration
  round-trip/check passed. Gitleaks 8.24.3 found no leaks. Complete Windows
  collector/native follow-up: 316 passed / 5 skipped / 2 warnings (565.64 s).
  SKIP reasons unchanged: four POSIX checks and one unsupported-platform test.
  No owned fixture service registration remains. Code/tests/CI equal v4 frozen
  bytes; only this evidence text was updated after regression.
- Python 3.13-built candidate wheel `0.1.0`, source `00d66e179a6e0c73aff79c5d83e2b7ab78a67925`:
  SHA256 `0b6b8c8d053199b52f61558f802e30d093ff79bb11ab709aeccb977990394485`.
  All 98 Python modules equal committed source bytes. Rollback wheel from accepted
  Stage A `ef78111c0d2e8f971cb16f7b64a40c3f7cffd716`: SHA256
  `788790267ccf99fdf7ba0843c2219cc0a4d865cf629b929b673a39d439457857`.
  These exact artifact files passed owned installed-wheel CLI lifecycle → uninstall
  → previous wheel → foreground rollback (1 passed, 56.08 s), config/binding kept.
  Artifacts are candidates until accepted source ancestry/exact-main CI verified;
  neither artifact has been installed on FILESERVER.
- No native reboot or FILESERVER live handover performed. Synthetic fixtures
  create only their own private objects/registrations, not existing ACL changes.

Operator checklist/rollback:
[Windows Service](../pilot/windows-service-ru.md).

### Approved live service trial — 2026-10-08 (Asia/Yekaterinburg)

The user explicitly instructed Codex to transfer the package to FILESERVER and
check it using the available access. This authorizes the controlled foreground
handover/service trial; it does not authorize reboot.

- Confirmed administrative access, existing foreground PID/creation time and
  unchanged enrolled state. Before handover: HEALTHY, one source/volume/collector,
  10,146 inventory objects, pending=0/quarantine=0, auth not suspended.
- Transferred the sealed operator ZIP and verified its SHA256, both wheel hashes
  and pinned installed dependency versions. The existing interpreter directories
  failed the stricter privileged-code protection boundary; no existing ACL was
  repaired. Prepared a separate standalone Python 3.13.15 installation with
  protected security attributes on new owned objects only. Read-only production
  installation validation PASS; all 98 installed Python modules equal the exact
  accepted wheel. Test-coverage startup instrumentation was excluded from this
  standalone installation. Original interpreter/package remain unchanged.
- Checked the exact old process identity and console membership. A temporary
  interactive-session helper sent normal Ctrl+C: runtime exit 130, old process
  tree exited. No forced process termination or runtime-lock deletion. The owned
  helper task was removed after success.
- Before SCM install, retained unchanged config/CA and a protected SQLite backup
  on FILESERVER; SQLite integrity/hash verification PASS. Private identity,
  binding, checkpoints and installation hashes remain outside public Git.
- Installed `SosnadminStorageCollector`: Automatic (Delayed), actual process token
  LocalSystem, one restart after 10 seconds then NONE. Idempotent install/start
  retained the running PID. Actual SYSTEM DPAPI/strict HTTPS ingestion succeeded.
- Three post-handover central API observations at 09:28:25, 09:29:24 and 09:30:28
  confirmed HEALTHY, newer collector observations, same source and one collector,
  and visible unchanged inventory. The startup queue drained to pending=0 and
  quarantine=0 without clearing batches/leases.
- Controlled service stop/start PASS: stop 1.151 seconds, STOPPED/PID=0 confirmed,
  new running PID after start. Real restart backlog drained in 102.58 seconds
  (35 read-only observations) to pending=0/quarantine=0; auth remains unsuspended.
  New heartbeat confirmed; config bytes, collector identity, credential binding
  and previous installed module hashes unchanged. Heartbeat sequence advanced
  1205 before install to 1217 at final validation; inventory remains complete.
- Read-only before/after comparison: existing installation/state/scope-root ACLs,
  SMB server configuration, audit policy and boot time unchanged. No USN Journal
  configuration operations were performed. One service runtime, no competing
  foreground. A 30-second steady service-process sample measured 0.208% of total
  CPU capacity and 39,526,400 bytes working set; this is a bounded sample, not a
  fleet/performance or SMB workload acceptance claim.
- A fresh browser login hit existing HTTP 429 after repeated acceptance logins.
  Read-only authenticated API evidence above passed. No rate-limit/authentication
  configuration was changed. After the normal 10-minute account window, one
  browser retry at 09:42 passed: real login, source HEALTHY, one source/volume,
  10,146 filesystem objects, volume detail/reload, no page errors and verified
  strict TLS. Private screenshots retained; no mocks/TLS bypass used.

Next: separate reboot permission/maintenance window and actual no-login boot
acceptance. Full regression/review/head+main CI completed.
Stage C remains unauthorized until GATE B PASS.

~~~text
PR: https://github.com/BorisDruzak/storage-console/pull/11 (MERGED)
Source SHA: c28ef069236a67da2f03bbaa5637fa29e7b88002 (final artifact source)
Implementation commits: 00d66e179a6e0c73aff79c5d83e2b7ab78a67925, 60ad7a8a3980b726d47be57c42a4ddb3e8a9a08a
Merged SHA: c28ef069236a67da2f03bbaa5637fa29e7b88002
Exact push CI: https://github.com/BorisDruzak/storage-console/actions/runs/37702965026 SUCCESS; Sonar SKIPPED
Prepared wheel SHA/version: 6cbdfffb64fb84fcbd9e7fc3b2a8969f37da50ba11bcbb8ad482d34bff86657a / 0.1.0
Installed FILESERVER wheel SHA/version: 6cbdfffb64fb84fcbd9e7fc3b2a8969f37da50ba11bcbb8ad482d34bff86657a / 0.1.0; 98 installed modules verified
Service name / start mode: SosnadminStorageCollector / Automatic (Delayed), actual FILESERVER PASS
Service identity + DPAPI validation: LocalSystem, actual native + FILESERVER HTTPS ingestion PASS
Install/stop/start/idempotency: PASS disposable + approved FILESERVER trial
Foreground handover: PASS approved FILESERVER Ctrl+C, old runtime exit 130
Network outage/backlog: 503 replay + retained 401 suspension PASS disposable
Pending/quarantine/freshness: actual FILESERVER drain 0/0 + new heartbeat/inventory HEALTHY
Controlled real service trial: EXPLICITLY AUTHORIZED/RUN/PASS; reboot remains separate
Real FILESERVER reboot approved: NO explicit approval/window received
Real FILESERVER reboot acceptance: NOT RUN, no-login auto-start NOT VERIFIED
Rollback verified: PASS exact final artifact files, existing config/binding preserved
Deployed central SHA: dda125d08f97fac78ccea466ec89fd0ad6f79776 (accepted Stage A)
Next stage authorized: NO
~~~

Do not mark PASS without explicitly approved real reboot acceptance.

## Stage C — NTFS USN to real Activity

GATE C: BLOCKED — GATE B PASS required; Stage C NOT STARTED

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
