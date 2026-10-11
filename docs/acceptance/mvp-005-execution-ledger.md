# MVP-005 — execution ledger

**Status: A PENDING → B PENDING → C PENDING.** This file is an implementation checklist, NOT a declaration that the new features are already deployed.

Task: docs/tasks/mvp-005-history-and-statistics.md

## Baseline (revalidate when work starts)

- Initial observed code main prior to task documentation: 3fa87ddbe4ba82ec2dd5e8d2f1cbc775c444742e
- USN-SOAK-001 original 72-hour window: FAIL; post-fix 41.12h observed, not a new 72h PASS.
- Last reported installed FILESERVER Collector source: eb6312bd431f40ff86e522c621c41e885defc454
- Last reported central runtime in original soak: 22667a67b6c5faceb914a114197e92b3a7bac2b7
- Check exact real deployed revisions at the start; no assumptions from git HEAD.
- Scope and historical completeness are limited to durable real evidence. No fabricated pre-baseline data.

## A — History and object timeline

GATE A: PENDING

```text
Source SHA:
PR:
Exact PR CI:
Merged main SHA:
Exact main push CI:
Backend/Windows/Web/Playwright regression:
Admin vs viewer/analyst/operator/auditor 200/403 tests:
Legacy Activity authorization regression:
Path search / identity timeline:
Keyset cursor / >10k / same-time + late arrivals:
No-path-in-URL/logs / CSV injection and audit:
PostgreSQL indexes / query plans:
Predeploy backup / rollback:
Central deployed SHA:
Live old/current event search and object timeline:
Unknown historical completeness correctly displayed:
Operator acceptance:
BLOCKER or caveats:
Next stage authorized:
```

## B — Activity statistics

GATE B: PENDING

```text
Source SHA:
PR:
Exact PR/main CI:
Aggregate SQL/reference counts:
By day / event type / weekday x hour:
Top directories and unknown path bucket:
Repeated RENAME and replay counted once:
Timezone tests:
Source/path RBAC and pagination bounds:
Web desktop/mobile real charts:
Post-deploy backup/rollback:
Live stats totals and independently checked SQL counts:
Operator acceptance:
BLOCKER or caveats:
Next stage authorized:
```

## C — Capacity time-series

GATE C: PENDING

```text
Source SHA:
PR:
Exact PR/main CI:
Migration upgrade/check/downgrade/upgrade:
Source/volume/time uniqueness and replay/out-of-order tests:
Invalid/fake samples rejected:
Existing inventory/USN/Overview regression:
Predeploy verified PostgreSQL backup and rollback:
Central deployed SHA:
Real scheduled capacity samples count:
Observed points / first-last times:
Verified net used delta (NOT bytes written):
Whole-volume vs monitored-root labeling:
Web chart / source & volume filter:
Operator acceptance:
BLOCKER or caveats:
After PASS — STOP:
```

## Evidence rules

- PASS only with tests, exact SHA/CI and observed real Web UI. Otherwise BLOCKED or FAIL.
- No 72-hour retest required by this task.
- Do not publish internal production file paths, identities, credential data, raw dumps, screenshots or private telemetry into public GitHub.
- Preserve original USN-SOAK-001 FAIL and its operational risk, irrespective of MVP-005 outcome.
