# MVP three-stage execution ledger — A / B / C

Контрольный журнал к docs/tasks/mvp-003-004-three-stage-delivery-train.md.

**GATE A PASS. GATE B PASS. GATE C PASS: exact code SHA/CI, deployment, controlled live acceptance, privacy, rollback and operator-consented cleanup verified. After C — STOP.**

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

GATE B: PASS — exact head/main full CI, native and real service/reboot acceptance confirmed

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
quarantine/freshness and no-login boot recovery are verified below.
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

### Documentary publication CI history

[PR #14](https://github.com/BorisDruzak/storage-console/pull/14) initial head
`98dd2903a6a38be6db0b23f59c15ab4a072ad413`,
[CI 37730844343](https://github.com/BorisDruzak/storage-console/actions/runs/37730844343):
FAIL in Windows native synthetic 503 → stop/start → backlog-drain acceptance:
`SERVICE_ACCEPTANCE_TIMEOUT` at the unchanged 105-second drain predicate;
42 other native checks passed, five other required jobs SUCCESS; Sonar SKIPPED.
This did not invalidate the observed FILESERVER reboot; publication/transition
was held until fresh native/full CI below. No failed/live CI run was cancelled or restarted.

Unchanged local native reproduction passed (1 passed, 48.75 seconds). Its read-only
synthetic timing observations showed separate retry/lease scheduling; the actual
CI failure cause is not established. Added bounded failure-only synthetic
queue/SCM snapshots, preserving the predicate and its post-start 105-second deadline.
No runtime/installed artifact change or increased timeout. Independent diagnostic
review: no Important findings. Exact updated-worktree native check passed
(1 passed, 94.23 seconds); Ruff/diff-check passed.

Fresh head `fda8a7597ee665e48f78875ba7b9f668278066d8`,
[CI 37732147714](https://github.com/BorisDruzak/storage-console/actions/runs/37732147714):
all six required jobs terminal SUCCESS, Sonar SKIPPED. Backend 622 passed /
58 skipped / 79 warnings (255.37 s), Windows installed CLI 14 passed and native
SCM/LocalSystem/runtime/HTTPS/PostgreSQL 43 passed (236.13 s); no native skips.
The initial failure did not recur; its cause remains unestablished. Diagnostic
instrumentation is not claimed as a fix. Retain bounded diagnostics if it recurs;
no product behavior, acceptance predicate or timeout was weakened.
Final evidence head `7d957032ef5d7ffbb1c086e2c247319b5c41a217`,
[CI 37732725825](https://github.com/BorisDruzak/storage-console/actions/runs/37732725825):
FAIL in a different native test, queue-pressure/lost-ACK runtime integration:
`OutboxError: STATE_UNAVAILABLE` while reading local outbox status. The service
503/replay test was among the 42 passing native checks; five other required jobs passed;
Sonar SKIPPED. No root cause is inferred from this generic error. Added bounded
synthetic failure-chain metadata to that test, without retry/suppression or changed
predicate/timeout; original error is re-raised. No installed runtime change.
Exact updated-worktree native/strict HTTPS/disposable PostgreSQL check passed
(1 passed, 67.17 s); Ruff/diff-check and independent diagnostic review passed.
Diagnostic head `54f83b34acabb42fcab6d912a63866fc1c47b272`,
[CI 37733855050](https://github.com/BorisDruzak/storage-console/actions/runs/37733855050):
FAIL in the same native queue-pressure observer; 42 other native checks and five
other required jobs passed, Sonar SKIPPED. Bounded metadata proves underlying
SQLite `SQLITE_BUSY` (numeric code 5) on `BEGIN IMMEDIATE`, busy budget 1 second.
The test observer used the runtime's writable outbox to read status, competing
for the producer/delivery writer lock. This is distinct from the initial service
503/replay timeout, whose cause is still not established.

Correction is test-only: separate read-only Outbox observer with the same path,
collector identity and limits; real runtime/capture/delivery keep the writable
outbox. A deterministic owned reserved-writer-lock check fails RED with the old
observer (`STATE_UNAVAILABLE`, 1 failed, 17.58 s). The read-only observer must pass
that check and the unchanged actual native HTTPS/PostgreSQL queue-pressure,
lost-ACK, duplicate, pending-zero and checkpoint acceptance. GREEN observed:
1 passed, 64.85 s, same busy/deadline/predicate; Ruff/diff-check passed. No retries, skips,
longer timeouts or production runtime changes. Final exact head and merged-main
CI remain required; C is held.

Corrected PR #14 head `cdd48fd82e8617919e0e35aacdc3600ddc23e49e`,
[CI 37734822496](https://github.com/BorisDruzak/storage-console/actions/runs/37734822496):
all six required jobs SUCCESS, Sonar SKIPPED; native 43 passed, installed CLI 14
passed, backend 622 passed / 58 skipped, frontend 121 passed / 12 Playwright passed.
Merged as `8e7eb05f96b43fad0ab11c7cefb61f42bcb7f2e1`; exact merged-main
[CI 37735548662](https://github.com/BorisDruzak/storage-console/actions/runs/37735548662)
FAIL: native 41 passed / 2 failed; five other required jobs SUCCESS, Sonar SKIPPED.
The successful head run does not substitute for failed merged-main acceptance.

Bounded failure metadata established two additional fixture conditions:

- Service replay timeout: all original outage batches and inventory were already
  acknowledged. Only two newly generated, unattempted heartbeat batches remained;
  service RUNNING, sequence 23, no quarantine or authentication suspension. The
  five-second fixture cadence kept replenishing the queue under slower delivery.
- Read-only integration observer: SQLite BUSY (code 5) occurred at
  `PRAGMA synchronous=FULL`, before BEGIN, with a one-second budget. Read-only mode
  removed the reserved-writer conflict but cannot bypass a bounded exclusive lock.
  CLI uses the configured one-second budget too; a five-second test monitor is
  not claimed as CLI parity or a product fix.

Additional RED -> GREEN checks use actual Windows/native execution:

- Owned exclusive writer holds the synthetic database for two seconds. Existing
  one-second observer fails RED (`STATE_UNAVAILABLE`, 1 failed, 18.09 s). Separate
  read-only monitor uses the existing Outbox default five-second busy budget;
  production/runtime writer settings remain one second. GREEN: 1 passed, 67.16 s,
  including reserved/exclusive locks, strict HTTPS/disposable PostgreSQL, original
  five-second queue pressure, lost-ACK replay, duplicate count, pending zero,
  heartbeat/inventory and durable checkpoint assertions. No errors suppressed.
- Controlled successful HTTPS receipt drips for approximately 5.7 seconds, inside
  the existing 15-second transport deadline. Five-second heartbeat cadence fails
  the unchanged 105-second pending-zero/freshness predicate RED (1 failed,
  124.89 s): retained backlog gone, only new heartbeats pending. Lifecycle/replay
  fixture now uses the production-default 30-second cadence; dedicated pressure
  and other native fixtures retain five seconds. Authentication-suspension wait
  derives from that cadence plus transport deadline plus one second. Drain
  deadline, zero-pending requirement, suspension persistence and cleanup remain.
  GREEN: 1 passed, 55.57 s, including slow receipt, unchanged drain and retained
  auth-suspension checks. Independent review of both test changes found no
  Important findings; reviewer did not claim native execution. Local full Windows
  installed CLI/native SCM/LocalSystem/runtime/strict HTTPS/disposable PostgreSQL
  regression: 57 passed, 2 dependency warnings, no skips (254.24 s, Python 3.14.3).
  Ruff, diff-check and Gitleaks public-file scan PASS. Fresh full required CI on
  exact head plus merged-main, including target Python 3.13, remain required.

No collector, installation artifact, backend, frontend or CI workflow is changed.
C remains NOT STARTED until all required final publication checks pass.

### Final native capture diagnostic checkpoint

[PR #15](https://github.com/BorisDruzak/storage-console/pull/15) head
`a4333e3f4017f13ff9f07c33363f1b985eef0372`, exact
[CI 37738636490](https://github.com/BorisDruzak/storage-console/actions/runs/37738636490):
all six required jobs SUCCESS, Sonar SKIPPED. Target Python 3.13 installed CLI
14 passed, native 43 passed without skips (330.03 s); backend 622 passed / 58
skipped / 79 warnings, deployment 54 passed, frontend 121 / Playwright 12 passed.
Merged as `30ac6c69acff0828203479422c3f6fad48a5d90d`, tree equal to accepted head.
Exact merged-main
[CI 37739444011](https://github.com/BorisDruzak/storage-console/actions/runs/37739444011):
FAIL, native 42 passed / 1 failed (407.56 s); five other required jobs SUCCESS,
Sonar SKIPPED. Service slow-receipt/replay passed. Integration's original
completion assertion failed: inventory `NATIVE_FAILED`, 6 records / 3 batches,
pending=0 / quarantine=0. No observer BUSY diagnostic appeared.

Partial counts prove failure inside inventory capture after successful flushes;
worker initialization, nonzero exit and report-decode failures would have zero
counts. Underlying Outbox, native iterator or other producer error is not yet
established. Do not infer writer contention from the generic native code.

Added test-only diagnostic entrypoint for that exact owned installed capture
worker command. It keeps isolated Python, installed modules, private stdin,
strict stdout report, Job assignment and settings. Standard-library runpy invokes
the same installed worker; narrow exception tracing retains the last 24 events
with class/function/line and bounded numeric errno/winerror/SQLite codes. No
exception text, frame locals, filenames, records, identities or credentials.
Expected CAPACITY/iterator-control exceptions do not consume the diagnostic cap.
Metadata lives in a separate synthetic temporary file; callback/write failures
do not change worker behavior, and original acceptance assertions remain.
Other native checks retain the ordinary uninstrumented `-I -m` entrypoint.

This is instrumented installed-wheel diagnostic execution, not a runtime fix.
Local actual Windows/strict HTTPS/disposable PostgreSQL diagnostic execution:
1 passed, 67.89 s. Bounded callback probe captures the numeric SQLite error without
SQL text, preserving exit/stdout/stderr. Final capped-source native regression,
independent review and exact head plus merged-main CI remain required. Runtime,
installed artifacts, budgets, monitoring cadence and deadlines are unchanged.
C remains NOT STARTED; real FILESERVER reboot acceptance remains independently PASS.

Independent review identified one Important diagnostic issue: first-event cap
could fill with routine handled sidecar FileNotFound/FileExists probes before
the actual midscan failure. Controlled 100-probe noise followed by numeric SQLite
error reproduces RED: root event absent. A bounded deque of the last 24 events
passes GREEN: root code retained, 24 records / 1810 bytes, no SQL/message text,
original exit/stdout/stderr unchanged. No blanket missing-file filter conceals
real DB/native disappearance. Fresh reviewer verification: no Important findings.
Permanent portable pytest regression reproduces first-cap RED (1 failed, 0.56 s,
root code absent), then last-event-buffer GREEN (1 passed, 0.15 s); it also verifies
bounded metadata, absent SQL/message text and unchanged binary stdout/exit.
Local native job before the tail-buffer correction: 43 passed, 2 dependency
warnings, no skips (245.34 s). Final corrected-tail actual Windows/strict HTTPS/
disposable PostgreSQL integration: 1 passed, 2 dependency warnings (67.58 s).
Full target Python 3.13 exact-head/main CI remain required, not substituted by
the portable diagnostic regression or local Python 3.14.3 checks.

### Final GATE B confirmation — 2026-10-08

[PR #16](https://github.com/BorisDruzak/storage-console/pull/16) final diagnostic
head `68557b21947c18185794579dd8974fc0e1345499`,
[exact head CI 37742061754](https://github.com/BorisDruzak/storage-console/actions/runs/37742061754):
terminal SUCCESS, all six required jobs. Target Python 3.13 native 43 passed /
no skips (287.15 s), installed CLI 14 passed; backend 623 passed / 58 platform
skips / 79 warnings, deployment 54 passed, frontend 121 / Playwright 12 passed.
Sonar explicitly SKIPPED, not Quality Gate PASS.

Merged as `8a1916d96aaca75287ff9b0865c9b5b98c8454ec`, tree equal to reviewed head.
[Exact merged-main push CI 37742833424](https://github.com/BorisDruzak/storage-console/actions/runs/37742833424):
terminal SUCCESS, all six required jobs; no failed/cancelled/timed-out steps.
Target Python 3.13 native 43 passed / no skips (224.85 s), installed CLI 14 passed;
backend 623 passed / 58 platform skips / 79 warnings, deployment 54 passed,
frontend 121 / Playwright 12 passed; Sonar SKIPPED.

Fresh live read-only verification at 12:21:45 (Asia/Yekaterinburg): automatically
started SYSTEM service still RUNNING, no manual post-boot start. Heartbeat sequence
1546, pending=0 / quarantine=0 / auth unsuspended. Identity/binding/config and all
98 installed modules unchanged. Actual source HEALTHY with new heartbeat;
one current volume quality COMPLETE, latest inventory 12:00:25, 10,146 objects.
Thus complete/fresh inventory is confirmed independently of queue-zero evidence.
Prior real delayed autostart/no human login, strict browser/TLS, policy-invariant
and rollback proofs above remain applicable to the unchanged installed artifact.

Independent final review: no Important findings; verified diagnostic-cap issue
was corrected RED -> GREEN. Ordinary uninstrumented installed capture entrypoint
is exercised by separate native checks; pressure test is explicitly instrumented.
The historical partial-capture NATIVE_FAILED did not recur in either final run.
Its underlying cause is still unestablished; neither diagnostics nor passing
runs are claimed as a runtime fix or elimination of intermittence. Instrumentation
can affect timing; acceptance does not guarantee complete capture under every
load. If this symptom recurs or a real runtime defect is identified, reopen the
gate for a bounded correction. No product/installed artifact change was made.

GATE B now PASS for this bounded pilot; Stage C implementation is authorized.
Live C must still use a dedicated folder inside approved scope. The user replied
“создай сам” to the folder-path request, explicitly delegating its creation to
Codex for the controlled scenario; no real department files are authorized targets.

### Operator-performed reboot acceptance — 2026-10-08

The user stated “отправил в ребут проверяй”. The operator performed the reboot;
Codex issued no reboot, service start/run/install or interactive login command
while verifying automatic startup. Read-only administrative SSH probes were used.

- New boot observed at 09:57:47 (Asia/Yekaterinburg). At +54 seconds, delayed-start
  service was still STOPPED and Console showed OBSERVE with retained inventory;
  this intermediate observation was not represented as HEALTHY.
- Automatic service process began at 10:00:06, approximately 139.36 seconds after
  boot, session 0. Registered Automatic (Delayed), LocalSystem and bounded
  recovery configuration preserved; actual process token is SYSTEM. No competing
  foreground runtime or leftover temporary console helper task.
- Successful logon auditing was already enabled and remained unchanged. Read-only
  Security 4624 and active-session checks found no human interactive logon since
  boot, including before service startup; 151 successful logon events observed at
  final probe. Service/system logons were excluded from human-interactive counts.
- Console API at 10:00:22 confirmed HEALTHY with new collector observation
  10:00:15: approximately 155.32 seconds boot-to-observed-HEALTHY. Another API
  observation at 10:06:26 confirmed continued HEALTHY/new heartbeat. Same one
  source, one volume, one collector and 10,146 inventory objects.
- Post-boot queue drained to pending=0/quarantine=0; auth not suspended. Heartbeat
  sequence 1266 then 1274, newer than last saved pre-reboot acceptance checkpoint
  1217; that checkpoint is not claimed as the immediate reboot cursor. Inventory
  checkpoint remains complete at sequence 20. Identity, credential binding and
  config bytes unchanged; all 98 installed modules equal the accepted wheel,
  original installation unchanged and protected rollback backup hash verified.
- Continued read-only check at 11:28:37 confirms the same automatically started
  SYSTEM service process, heartbeat sequence 1440, queue 0/0, unchanged config,
  identity and 98 installed modules; API HEALTHY with fresh heartbeat and the
  same 10,146 objects. This required no manual service start or further reboot.
- Existing state/installation/scope-root ACLs, SMB configuration and audit policy
  compare unchanged against pre-handover evidence. No USN configuration operation
  was performed. Boot changed through the operator's action only.
- Fresh strict-TLS browser acceptance after reboot PASS: actual login, HEALTHY
  source, one source/volume, 10,146 objects, volume detail and reload, no page
  errors. Private post-boot evidence/screenshots retained outside public Git.

Full regression, independent source review and exact code head/main CI already
completed above. This documentary checkpoint requires its own fresh independent
review/head and merged-main CI before starting C. C remains NOT STARTED here.

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
Controlled real service trial: EXPLICITLY AUTHORIZED/RUN/PASS
Real FILESERVER reboot approved: operator performed reboot; user requested verification
Real FILESERVER reboot acceptance: PASS; auto-start/no human login, fresh heartbeat, queue 0/0
Rollback verified: PASS exact final artifact files, existing config/binding preserved
Deployed central SHA: dda125d08f97fac78ccea466ec89fd0ad6f79776 (accepted Stage A)
Final acceptance head SHA: 68557b21947c18185794579dd8974fc0e1345499
Final merged-main SHA: 8a1916d96aaca75287ff9b0865c9b5b98c8454ec
Final exact push CI: https://github.com/BorisDruzak/storage-console/actions/runs/37742833424 SUCCESS; Sonar SKIPPED
Next stage authorized: YES; bounded read-only USN/Activity C only
~~~

B acceptance is limited to the reviewed code, installed artifact and actual pilot.
Measured delayed startup latency is an observation, not a guaranteed fixed timeout.

## Stage C — NTFS USN to real Activity

Historical checkpoint — GATE C was BLOCKED pending exact-SHA CI/release/live acceptance.
Final result is recorded in “Stage C — corrected live acceptance” below.

Baseline main SHA: `8a1916d96aaca75287ff9b0865c9b5b98c8454ec`.
Baseline exact-main CI: `37742833424`, all six required jobs SUCCESS, Sonar SKIPPED.
Central remains accepted Stage A `dda125d08f97fac78ccea466ec89fd0ad6f79776`;
FILESERVER remains accepted Stage B wheel `6cbdfffb64fb84fcbd9e7fc3b2a8969f37da50ba11bcbb8ad482d34bff86657a`.
No C runtime deployment or journal configuration change has occurred.

### Preparation and initial RED -> GREEN — 2026-10-08

User delegated dedicated-folder creation with “создай сам”. A unique empty
synthetic folder was created inside the existing approved monitored root after
resolved-path/reparse checks; no existing files modified. Native read-only
`fsutil usn queryjournal` of that volume succeeded. Raw root/folder/journal
evidence stays private; no journal enable/resize/delete operation was issued.

Plan: `docs/superpowers/plans/2026-10-08-usn-activity-stage-c.md`.
Portable parser RED: required module absent; GREEN: 14 passed. Actual isolated
Windows NTFS QUERY/READ/CRUD RED: native module absent; GREEN: 1 passed, no skip;
CREATE/WRITE/RENAME_OLD/RENAME_NEW/DELETE correlate with inventory FileId.
Journal ID/maximum size/allocation delta unchanged. Combined parser/native and
existing native inventory: 32 passed, 2 dependency warnings (0.38 s).

Atomic multi-checkpoint/cursor/batch transitions RED: four missing-interface
failures; GREEN with existing Outbox/delivery/priority regressions: 82 passed,
4 platform skips, 2 dependency warnings (3.20 s). Mixed-key validation separately
RED: leaked TypeError before transaction; correction validates keys before sort;
atomic-state GREEN: 5 passed, 2 dependency warnings (0.26 s).
Scoped normalization initial RED: required module absent; GREEN: 6 passed.
Partial-pair status/unpaired NEW/no invented rename regressions RED: 3 failed,
5 passed; GREEN combined four new USN files: 28 passed, 2 dependency warnings
(1.41 s), including real native CRUD. Ruff and Linux-target mypy of new modules
PASS. Windows-target mypy also exposes pre-existing `os.geteuid` portability
annotations in Outbox; the canonical target is checked separately.
These are isolated implementation checks, not full regression, independent
Stage C review, final exact-SHA CI or live/operator Activity acceptance.

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

### Stage C current development checkpoint (not Gate C acceptance)

At this development checkpoint, product changes remained uncommitted on the Stage C branch based on
`a756654bb0e868fd1f200e4d327e003097b3c6fd`; no Stage C PR, exact CI, deployed
candidate or live CRUD acceptance exists yet. The delegated dedicated folder is
created, but still has no controlled test files. Accepted B runtime remains installed.

- Protected USN activation RED five failures -> GREEN with existing configuration:
  19 passed. Default disabled; enable/disable survives restart without changing
  config bytes or credential binding; invalid/duplicate-key/scope-mismatched sidecar
  fails explicitly. CLI includes stopped-state enable/disable/rebaseline operations.
- Independent runtime RED two missing-interface failures -> GREEN. Subsequent
  inventory-stop exception review reproduced a skipped USN stop, then correction
  ensured sibling cleanup and lock release. Configuration/CLI/runtime regression:
  36 passed at that checkpoint, before the later progress-age additions.
- Bootstrap review found enumeration/cursor ancestry race. Portable mutation test
  RED -> fenced bootstrap GREEN, including native NTFS capture. No cache commits
  when an approved object or parent changes during enumeration; outside-only volume
  noise is read without persisting its names. Prior WRITE/move-in findings were
  closed by independent component re-review.
- Native QUERY/READ terminal errors initially cleared on the next successful query:
  five PostgreSQL-independent failures reproduced this. They are now latched in
  protected state; relevant bootstrap/error/native capture checks: eight passed.
- Cache capacity and explicit rebaseline each had RED -> GREEN: seven atomic-state
  checks passed. Capacity rolls back cursor/cache/batch together; heartbeat retains
  independent checkpoints. Rebaseline keeps queued bytes/receipts and credentials.
- Installed isolated `-I` USN worker built from current source: one actual Windows
  native test passed in 10.54 seconds; scoped Cyrillic CRUD, durable cache reopen,
  stable FileId and no logical reread duplication. Local interpreter is Python 3.14,
  not substituted for the required Windows Python 3.13 CI gate.
- Full frontend regression: 125 Vitest passed; API generation/check, TypeScript
  build, ESLint and i18n gate passed. Activity now uses typed API, five-second polling,
  preserved absolute evidence expiry, source/type filters, bounded paging, FileId,
  USN provenance and explicit unknown continuity/path/actor/client/confidence.
- Outbox/delivery/priority regression after cache bounds: 84 passed, four existing
  platform skips. Ruff passed before subsequent test additions; mypy Linux-platform
  check passed on 22 affected source files. Final whole-source checks remain required.
- Whole-source review exposed partial RENAME ingest assertion. Actual PostgreSQL
  RED reproduced it for a known object; proven-side-only alias update corrected it.
  Activity/dedup/alias regression: 40 selected checks completed successfully, including
  move-out/move-in before and after inventory hydration. Later freshness checks add
  two more cases; full final regression is still pending.
- Whole-source review exposed fresh heartbeat falsely retaining continuous USN after
  a blocked worker. RED -> GREEN with independent progress age and bounded child
  deadline. Backlog beyond eight raw transitions also reproduced false completion;
  now returns USN_LAG. Combined bootstrap/native/runtime checks: 13 passed.
- Actual PostgreSQL freshness RED showed a 35-second lifetime exceeding the USN proof
  interval. New typed cursor carries an absolute progress timestamp; API proof age
  and its evidence lifetime are bounded to 15 seconds. Fresh, aged and existing
  projection/filter checks: three passed in 27.50 seconds.

- Default 30-second heartbeat exceeded the 15-second proof lifetime: a targeted
  runtime test reproduced the mismatch RED. USN activation now bounds publication
  to five seconds without rewriting config; five runtime cases GREEN. Installed
  native USN -> strict HTTPS -> PostgreSQL -> Activity with default settings,
  byte-identical lost-ACK replay and logical dedup: one passed in 59.68 seconds.
  Four five-second Activity polls stayed COMPLETE beyond one proof lifetime.
- New Windows USN parser/native/cache/scope/bootstrap/activation/runtime/installed
  worker checks: 56 passed, no skips, 17.17 seconds on local Python 3.14. Playwright
  regression: 12 passed, 12.6 seconds; these use controlled API fixtures and do not
  replace live browser acceptance. Adaptive oversized transitions passed 17
  relevant checks without advancing beyond unconsumed records.
- Immutable accepted B wheel reader/writer on owned state passed; C replay reopened
  with unchanged pending bytes and credential binding. B deliberately rejects
  partial C RENAME payloads. The runbook requires C delivery before package rollback
  or preservation for C recovery; shared SQLite schema alone is not event compatibility.
- Independent source/component review found no remaining verified Critical/Important
  after cadence and partial-rename corrections. Full first target-version regression
  failed seven legacy migration checks (682 passed, 66 skipped): they pinned 0005
  before checking against new 0006 head. All original path/downgrade assertions remain;
  updated migration suite passed nine checks. Corrected full regression is running.
  Ruff, mypy 101 source plus six deployment modules, runtime OpenAPI check and 54
  deployment checks passed. Public candidate Gitleaks scan reported no leaks.

- Corrected canonical Python 3.13.16/PostgreSQL full regression: 689 passed,
  66 Windows-only skipped, 59 warnings, 349.34 seconds. Migration upgrade/check,
  downgrade to base, upgrade/check passed. Candidate archive SHA256:
  `bc0af43ebe66e25db23d5acef4772936be5108b586a7191f0c267f7945a4567e`.
  Existing local Windows CLI/native/inventory/runtime regression: 45 passed,
  no skips, 344.10 seconds. Disposable source verification does not close live gates.

Still pending: browser real-API acceptance; separate Stage C PR and exact-head/main CI;
immutable artifacts/backups/deployment; controlled live folder scenario, measured
latency, restart/network loss/replay, invariants and rollback. Gate C remains open.

Final ancestry review before publication reproduced two additional path-integrity
failures: a descendant renamed while its ancestor was outside retained its old
name after re-entry; a pending WRITE used renamed ancestry under its earlier time.
Both RED failures were corrected. Outside descendants become redacted tombstones
without losing pending inside WRITE/OLD evidence. WRITE keeps its first parent and
path digest; changed or unproven historical ancestry yields an unknown path.
Restart/pending-pair/re-entry-descendant/cross-parent controls passed; independent
review found no remaining verified Important. Latest combined native USN/runtime/
installed-worker/HTTPS/PG/Activity checks: 62 passed, no skips, 77.37 seconds.
The previous 689/692 full-pass snapshots predate these last corrections. Final
frozen-source Python 3.13.16/PostgreSQL regression: 694 passed, 66 Windows-only
skipped, 59 warnings, 342.83 seconds. Ruff, mypy 101+6, runtime OpenAPI, 54 deployment
checks and complete migration upgrade/check/downgrade/upgrade/check passed.
Final test archive SHA256:
`41b9ca845fa4ab7c416c74e5538a32596e78560f1d934ce2e53fe62ffd131931`.
Gitleaks on that public archive reported no leaks. Immutable B compatibility/C byte
recovery was rerun successfully. These checks preceded the first live C attempt.

### Stage C first live attempt — historical FAIL, superseded by corrected acceptance

- Draft [PR #17](https://github.com/BorisDruzak/storage-console/pull/17), source
  `b771db2659aa01b1896a8c99c4a46c39321df99b`,
  [exact-head CI](https://github.com/BorisDruzak/storage-console/actions/runs/37759319009):
  all six required jobs SUCCESS; Sonar SKIPPED. Not merged; no C exact-main acceptance.
- Immutable wheel SHA256
  `dfd179188b84f2691152f11af96b3fa3a0febcc8fb5beb4ec17dfe3d0da77ba1`:
  139173 bytes; all 103 Python modules byte-equal source. Operator ZIP SHA256
  `adf8e30da7c3810f0768509e5ee042f3a1b531a52c6084514c9f34244099a78d`.
  Accepted B rollback wheel retained unchanged. Actual owned SYSTEM service with
  strict HTTPS/PostgreSQL completed immutable C -> B -> C acceptance: one passed,
  96.23 seconds; cursor, config, binding retained. This is isolated artifact proof.
- Central was deployed to exact C source after verified database backup SHA256
  `eac0fd51335ee3443b7a8fb5c51f96158d4402cfaf53feb28e84b63c4b02d868`.
  API/worker/web/PostgreSQL healthy; revision checks, migration/check, strict TLS,
  auth/redirect, inventory threshold 7200 seconds and post-backup verification PASS.
- Real collector C installation verified all 103 modules and LocalSystem service.
  Offline SQLite backup SHA256
  `e1052fa31b0fcf7fff7559b69c3a07e44919b611e8557b4ab816875de0e7a699`.
  Existing config/identity/binding preserved; no reboot or journal mutation.
  User delegated creation of the dedicated disposable folder inside approved root.
  USN baseline became COMPLETE / CONTINUOUS_SINCE_BASELINE; queue/quarantine 0/0.
- Controlled live create/write/file rename/parent rename/delete generated stable
  FileId and correct known paths, including DELETE after parent rename. However,
  both renames also produced a redundant partial RENAME for CLOSE|NEW (0x80002000)
  after the complete OLD/NEW pair (0x00003000). GATE C FAIL; no latency/UI PASS claimed.
  Existing synthetic checks had checked event-ID dedup but missed this semantic
  duplication. Native installed-worker assertion now requires exactly one RENAME.
- Independent review confirmed the blocker. Two focused tests reproduced RED;
  correction persists proof of emitted NEW within the current reason cycle,
  suppresses matching parent/name accumulated NEW summaries without pending OLD,
  and clears proof after CLOSE. Markerless orphan NEW, subsequent real rename,
  restart/buffer boundaries and DATA on CLOSE remain observable. See Microsoft
  [USN_RECORD_V2 reason semantics](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-fscc/d2a2b53e-bf78-4ef3-90c7-21b918fab304).
  First correction focused scope/installed native worker GREEN: 22 passed.
  Independent review then reproduced repeated NEW|DATA before CLOSE; matching
  NEW is now suppressed throughout the proven open reason cycle while DATA still
  accumulates. Any destination cache change invalidates proof. The earlier
  CLOSE-only snapshot passed 698 backend checks and 66 native checks, but these
  results do not verify the final reason-accumulation correction. Full corrected regression,
  independent review, updated exact-SHA CI/artifact and fresh live acceptance pending.
- Browser verification helper used UI aliases instead of raw API relative-path
  fields; its failed attempt is not acceptance evidence. Correct the helper and
  measure a fresh creation in an actual polling UI after the product correction.
- After draining C events, actual live service rollback to unchanged accepted B
  succeeded without re-enrollment/config/binding changes. Central C ingest stays
  available for already-delivered C events. Existing historical test events are
  retained; future corrected acceptance must use a fresh bounded time window.
  Cleanup, network replay, restart, final invariants and Gate C remain open.

Final corrected reason-cycle source verification (not live acceptance):
Python 3.13.16/PostgreSQL full regression 700 passed, 66 Windows-only skipped,
59 warnings, 336.88 seconds. Ruff, mypy 101 source + six deployment modules,
runtime OpenAPI, 54 deployment checks and upgrade/check/downgrade/upgrade/check
PASS. Snapshot SHA256:
`33e828337cbab14ead73f455623122b4280c693d3de6c72bf41c4d5765eed558`.
Actual local Windows USN/installed worker/HTTPS/PostgreSQL/Activity regression:
68 passed, no skips, 77.86 seconds. Independent review of the final correction
reported no remaining verified Critical/Important. Updated exact-head/main CI,
immutable artifact and fresh controlled live acceptance are still pending.

- Change only own gate after verifying relevant evidence.
- Describe failures as FAIL or BLOCKED, never ambiguous success.
- Cite exact action URLs/commit SHAs.
- Never paste real production filenames, credentials, raw paths or diagnostics.
- Separate disposable environment tests from live FILESERVER acceptance.
- Do not advance B without A PASS, or C without B PASS.

## Stage C — corrected live acceptance (2026-10-08)

GATE C: PASS. Exact merged-main CI and post-merge runtime verified; this section
records final evidence. The acceptance follow-up contains tests/documentation only;
no further product development is authorized by this gate.
Source: `385f427e18f93051eb98bc10c7f23089326b3792`.
[PR #17](https://github.com/BorisDruzak/storage-console/pull/17) merged as
`22667a67b6c5faceb914a114197e92b3a7bac2b7`; its tree equals the reviewed source.
[Exact-head CI](https://github.com/BorisDruzak/storage-console/actions/runs/37764490272):
six required jobs SUCCESS; Sonar SKIPPED (unconfigured).
[Exact merged-main CI](https://github.com/BorisDruzak/storage-console/actions/runs/37767139793): six required jobs SUCCESS; Sonar SKIPPED.

- Final RED→GREEN includes accumulated NEW|DATA before CLOSE, paired/orphan NEW,
  durable reopen/buffer boundaries, destination changes and retained DATA.
  Full Python 3.13/PostgreSQL regression: 700 passed, 66 Windows-only skipped;
  Windows native/installed-worker/HTTPS/PostgreSQL: 68 passed, no skips.
  Ruff/mypy/OpenAPI, deployment 54 and migration cycle PASS; frontend 125 Vitest,
  types/build/lint/i18n and 12 Playwright PASS. Independent final source review
  reported no verified Critical/Important findings.
- Immutable wheel: 139361 bytes; SHA256
  `8c770a4c6471d75373216ce603a807cd28c47d4bd4288f03322bcc6d558ddd89`.
  All 103 installed modules byte-equal source. Operator ZIP SHA256
  `d286352fc79ccdc976788869cb655d8de9e3d848b250c1973c2f095b26c988d1`.
  Accepted B wheel retained unchanged. Actual owned SYSTEM C→B→C service
  acceptance with strict HTTPS/PostgreSQL: 1 passed, 83.51 seconds; exactly one
  native file rename, retained cursor/config/binding and honest B Activity UNKNOWN.
- Corrected central deployment and FILESERVER LocalSystem service verified;
  config/enrollment/binding unchanged, no foreground competitor. Private pre/post
  database and offline collector-state backups were hash/integrity verified.
  The accepted operator reboot belongs to Stage B; Codex initiated no reboot.
- Actual FILESERVER create→write→file rename→parent rename→delete passed twice,
  before and after controlled service restart/API outage. Fresh bounded window:
  two stable FileIds, ten file events, all four types, exactly one RENAME per file,
  no logical duplicate IDs, accurate old/new and DELETE-after-parent-rename paths.
  Actor/client/confidence remain null, provenance NTFS_USN.
  Earlier failed-candidate historical events remain retained; the fresh proof
  does not claim those earlier duplicate rename summaries never occurred.
- Actual authenticated Russian Chromium UI, strict TLS with trusted CA, source/type
  filters, Asia/Yekaterinburg display, reload and mobile passed without page errors.
  Measured CREATE `10:47:07.661885Z` → rendered `10:47:21.605Z`:
  **13.944 seconds**, including normal collector delivery and UI polling, below 60s.
- Controlled SYSTEM service stop/start passed with advanced heartbeat and unchanged
  config/binding. Brief HTTPS loss was simulated by stopping only the owned central
  API; capture continued. After restoration, **23 original queued batches** matched
  their original byte SHA256 in actual receipts; queue/quarantine 0/0, auth not
  suspended. Fresh source HEALTHY; inventory and Activity COMPLETE,
  CONTINUOUS_SINCE_BASELINE. Overview/capacity continued.
- Privacy qualification: FILESERVER existing-journal native experiment used an
  isolated narrower scope within the delegated synthetic directory. A sibling
  marker outside that experimental scope was absent from outgoing payload and
  SQLite bytes; all four in-scope types present, journal configuration unchanged.
  **That experiment did not upload** or change the actual enrollment scope.
  Previously executed native HTTPS/PostgreSQL integration proved positive delivery,
  not sibling exclusion. Independent review caught that documentary overclaim.
  The strengthened installed-worker HTTPS/PostgreSQL test now also performs
  outside sibling CRUD and verifies its marker and native FileId are absent from
  actual request bytes, all persisted change rows and Activity API. In-scope CRUD
  proves nonempty delivery and traversal past those sibling operations. Actual
  Windows execution PASS: 1 passed, 2 warnings, 59.61 seconds; final independent
  review reports no verified Critical/Important. Product source unchanged.
  The FILESERVER experimental sibling remains inside the real approved root
  and may legitimately appear in the real full-scope stream.
- Existing ACL, SMB and audit-policy invariants unchanged; existing journal only
  QUERY/READ. Same operator-accepted boot (CIM timestamp jitter bounded under 1s),
  no competing collector or helper scheduled task. No production contents collected.
- Explicit operator consent received for cleanup. Only the dedicated synthetic
  folder was removed at `2026-10-08T10:54:56.8713081Z`: resolved absolute path and
  approved parent checked, no reparse points, six synthetic remaining entries,
  parent preserved. No real department files touched.
- Rollback: drain C payloads through compatible C ingestion before switching to B,
  or retain exact queued bytes for C recovery; preserve cursor/cache and binding.
  Actual immutable C→B→C proof and earlier live C→accepted-B rollback passed.
  Central rollback requires a compatible verified database snapshot or retained C
  API; downgrading indexes alone is insufficient. New reason-cycle cache must not
  be handed to the superseded C reader.

All raw security evidence, production paths, identities, screenshots and credentials
remain private. Sonar SKIPPED is not a Quality Gate PASS.
After final GATE C PASS: STOP; attribution, SMB/VSS/ACL, PVE/PBS, Diagnostics and
Discovery remain outside this issue.

Post-merge deployment verification: central exact SHA
`22667a67b6c5faceb914a114197e92b3a7bac2b7`; four services healthy,
revision labels, strict TLS/auth, Alembic check and 7200s inventory threshold PASS.
Actual API image: `sha256:eedd91a40e43e0e41463304deb0e9ba0c017f34cd88d2062ad4cca1a1068470b`;
web image: `sha256:b9e0632b3f0da67e9ff06cef349569983ce5ba8ccfa88242328fa0fd2cd58724`.
Verified pre/post database backup SHA256:
`69cf0902df39d9688ea6a9deb64839596fbf07b7975cde521bc3dc1322a21ce9` /
`69d790ba74ccdf0a89cc470fc6479f5c1aaf08bae5aaade17bfd3996c647ba85`.
Collector artifact remains source385, all modules identical to the merged source;
no reenrollment/restart/reboot for this central publication. Post-merge real
API/browser inspection of the existing corrected evidence PASS: all four types,
stable FileId, one rename, Russian filters/timezone/reload/mobile/strict TLS.
This read-only repetition is not a second latency measurement. Queue/quarantine
0/0, auth active, SYSTEM running, config/binding unchanged. Source HEALTHY,
Activity COMPLETE / CONTINUOUS_SINCE_BASELINE; inventory remains within accepted
7200s TTL. Cleanup does not claim an immediate full inventory recount.

Final GATE C checklist: all sixteen requirements PASS, with evidence above for
approved scope; existing-journal QUERY/READ only; native four types; canonical
volume/stable FileId/cache; atomic durable cursor/outbox; explicit gap regressions;
privacy including transported sibling exclusion; actual HTTPS/PG replay; bounded
authenticated Activity API; Russian real-event UI/no actor inference; measured
13.944s latency; restart/outage; continuing inventory/heartbeat/Overview; exact
head/merged-main six-job CI and honest Sonar SKIPPED; delegated operator live
scenario/consented cleanup; actual rollback and retained recovery state.

Acceptance follow-up test commit:
`6007fca6753c1a16336a0fb7743bbf94dfae33a1` —
`test(usn): prove sibling exclusion through HTTPS ingestion`.
Only native test evidence and final documentation differ from the deployed code.
Source/compiled collector module bytes remain those of the accepted release.
After GATE C: **STOP**. No attribution, SMB/VSS/ACL, PVE/PBS, Diagnostics,
Discovery, remediation or fleet rollout was performed.

Acceptance-follow-up CI first attempt
[37768400795](https://github.com/BorisDruzak/storage-console/actions/runs/37768400795)
FAILED in the pre-existing native runtime pressure test, before USN/privacy steps.
It read queue-empty before reading inventory completion and later reread a changing
queue; the assertion observed four pending batches after its earlier empty snapshot.
The test now reads completion before queue status and asserts that same bounded
post-completion empty snapshot; ongoing heartbeat producers do not promise a
permanently empty queue. Pressure, lost ACK/one duplicate, PG effects, heartbeat,
checkpoint and bounded shutdown assertions remain. Product code unchanged.
This corrects a demonstrated observer ordering defect; no claim is made about the
separate older partial-capture timeout whose root cause remains unestablished.
Replacement actual native runtime + USN HTTPS/PostgreSQL regression: 2 passed,
2 warnings, 126.58 seconds; Ruff PASS. Final independent test review reports no
verified Critical/Important. Replacement exact-SHA CI must pass before this
follow-up is merged or Issue #8 is closed.
