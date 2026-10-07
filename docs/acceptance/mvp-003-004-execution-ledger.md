# MVP three-stage execution ledger — A / B / C

Контрольный журнал к docs/tasks/mvp-003-004-three-stage-delivery-train.md.

**Данный файл инициализирован до запуска Codex. Ни один следующий gate ещё не подтверждён.**

## Known baseline

- PR #7: merged into main at code SHA 07fbb9fdc31603a6309887684805ffb98ec5a9db.
- Issues #5 and #6: require explicit reconciliation/closure with operator acceptance evidence.
- Post-merge CI: check fresh terminal result, never infer from PR green.
- Existing Windows Collector: foreground wheel/CLI, tested live inventory/heartbeat.
- Current dashboard capacity: tested in real pilot; production SHA must be revalidated against main.
- User attribution and USN Activity: not implemented/accepted at this point.
- GitHub repository is public: no operational secrets/paths or internal data in this ledger.

## Stage A — main and operating MVP

GATE A: PENDING

~~~text
Source SHA:
Merged main SHA:
Exact push CI run:
Tests:
Central deployed SHA:
Backup/rollback evidence:
Real Overview/capacity/inventory proof:
Issue #5 state/evidence:
Issue #6 state/evidence:
Exceptions/Sonar:
Operator confirmation:
Next stage authorized:
~~~

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
