# STORAGE-AUDIT-001 — журнал промежуточной приёмки

Задача: docs/tasks/storage-audit-001-windows-security-attribution.md

**Статус:** A PASS → B PASS → C PARTIAL; живое продолжение ожидает закрытия
живого испытания по согласованному закрытому плану. Оператор отдельно снял лимит числа операций;
узкий scope, объём данных, 30 секунд Audit-only 503 и итоговый Audit STOPPED сохранены.
Следующий этап не начинается до предыдущего PASS.

## Выполнение 2026-10-13 — этап A

- Baseline: e12e59753571beb7b1730e3803d1649c687368ba, отдельный managed worktree,
  branch `codex/storage-audit-001-a`. Исходная рабочая копия main не изменена.
- Issue #22 OPEN; на момент проверки open PR отсутствовали. History/RBAC,
  change_events и существующий Windows USN Collector не изменены.
- GitNexus list_repos: Storage Console не индексируется. Архитектура проверена
  по текущим исходникам/контрактам/тестам; reindex/group_sync не выполнялись.
- Read-only FILESERVER preflight 2026-10-13: Security readable/enabled, circular
  retention, 20 MiB. Audit File System: No Auditing. Audit Logon: Success and
  Failure. В bounded пятиминутном окне 4663/4660 отсутствовали, 4624 присутствовали.
  Отсутствие 4663 не трактуется как отсутствие изменений.
- Pilot root ещё не утверждён; SACL не исследовалась, GPO owner требует подтверждения
  оператора. USN service Running; Audit NOT_INSTALLED. Production mutations NONE.
- Новая служба/lock/SQLite/UUID/token независимы. Этап A — capture_only,
  last_accepted_at NULL, NOT_CONFIGURED/OBSERVE/GAP; central ingest — этап B.
- RED: 22 parser/store cases и 7 runtime cases на отсутствующем независимом
  implementation. GREEN: первоначальные 36 cases; native local tests намеренно
  SKIPPED, так как эта рабочая станция не disposable runner.
- Независимое focused review: Critical 0, Important 6. Воспроизведены и исправлены
  RED→GREEN outside-scope handle reuse, Windows ordinal Unicode comparison,
  fail-closed leaf attributes и byte-bounded long/Cyrillic caches. Добавлены
  native bounds/capacity/rollover margin/bookmark age и усилен installed-wheel
  SCM test настоящим Security capture на owned disposable fixture. Native
  результаты до exact Windows CI остаются PENDING.
- Дополнительный RED→GREEN: queue ID должен совпадать с batch_id в immutable
  envelope; naive timestamp отвергается; session digest не меняется при повторном
  scoped access; host/generation/boot relabeling блокируется.
- Local focused после review fixes: 44 passed / 6 native skipped; legacy focused
  regression: 149 passed / 8 skipped до добавления ещё двух native fixture checks.
  Native local skip означает отсутствие disposable runner, а не приёмку Windows.
- Полная isolated Python 3.13/PostgreSQL 16 regression после `alembic upgrade head`
  и `alembic check`: `pytest -q` — 776 passed / 82 platform skips;
  `pytest tests/deployment -q` — 54 passed. Ruff, mypy (112 source files),
  `python -m packages.contracts.export_openapi --check` PASS.
- Первая попытка полного прогона: 773 passed / 80 skips / 2 failures
  (`test_worker_heartbeat_upsert_and_freshness`,
  `test_canonical_identity_constraints_and_deleted_last_known_path`). Причина —
  отсутствовавший `alembic upgrade head` в disposable harness, не дефект продукта;
  исправленный harness дал полный GREEN без изменения этих тестов/исходников.
- Web regression: `npm run api:check`, `npm run lint`, `npm run typecheck`,
  `npm test` (125 passed), `npm run build`, `npm run test:e2e` (12 passed) PASS.
  `npm ci` сообщает 0 vulnerabilities. Известное build предупреждение о chunk >500 kB
  не изменялось в данном scope. Exact PR/main CI ещё PENDING.
- Installation/upgrade/rollback: `collectors/windows_audit/README.md`.
  Это runbook для отдельного разрешения, не authorization на FILESERVER.

### Exact CI первого source SHA и исправления native

- PR A: https://github.com/BorisDruzak/storage-console/pull/24 (draft),
  source 47704d6fe44de69718eddf704da8190891d70181,
  workflow https://github.com/BorisDruzak/storage-console/actions/runs/38385578983.
- backend/frontend/compose-smoke/production-smoke/secrets SUCCESS; sonar SKIPPED.
  windows-pilot FAIL: existing SCM/USN/HTTPS steps SUCCESS, новый audit step
  46 passed, 3 failed, 1 fixture error. Этот source SHA не даёт GATE A PASS.
- Native RCA: scalar EVT_VARIANT.Count не определён и Windows возвращает
  0xFFFFFFFF; проверять scalar UInt64 Type, не Count. Native read-only probe
  воспроизвёл это; portable RED→GREEN добавлен. Microsoft EVT_VARIANT contract проверен.
- Fixture fixes: XML bookmark использует single quotes — менять RecordId через
  XML parser, не regex; exported EVTX требует своего native bookmark, а replacement
  проверяется по strict miss либо несовпадающему anchor digest. Никакой очистки
  реального Security channel. Fixture SACL создаётся через runner pwsh с соответствующим
  module path, вместо несовместимого powershell.exe environment.
- Дополнительный SCM RED→GREEN: Audit требует отдельного display name; общий USN
  backend использовал одинаковый display name. Собственный AuditBackend сохраняет
  recovery/registration validation; native тест держит две регистрации одновременно
  и проверяет неизменность existing USN registration. Старый backend не меняется.
- После native/SCM fixes local audit focus: 46 passed / 6 native skipped; Ruff/mypy PASS.
  Новый exact-head CI и exact-main CI ещё требуются; результаты старого SHA не переносятся.

### GATE A PASS — 2026-10-13

- Final source head: 42ac2bf716cc5ee1a7e586544c7e8bf153bee63d;
  PR https://github.com/BorisDruzak/storage-console/pull/24 merged.
- Exact-head CI: https://github.com/BorisDruzak/storage-console/actions/runs/38387719478,
  все 6 обязательных jobs SUCCESS, sonar SKIPPED. Native Audit: 52 passed;
  existing native SCM/runtime 81 passed, USN 67 passed, real HTTPS/PG USN acceptance passed.
- Merged main: dd65c4844e540f235b23f3c456ec09d8784f62e5.
  Exact push-main CI https://github.com/BorisDruzak/storage-console/actions/runs/38389182880:
  все 6 обязательных jobs SUCCESS, sonar SKIPPED.
- Native installed wheel / LocalSystem / own SCM / two simultaneous registrations /
  machine DPAPI / actual scoped Security capture / strict resume / fixture generation
  replacement / reparse privacy / queue restart / crash rollback / byte-identical replay PASS.
- Central API image revision read-only confirmed:
  22667a67b6c5faceb914a114197e92b3a7bac2b7. Publication A не означает deployment.
- Existing installed USN package version 0.1.0; пять критических modules
  (runtime/outbox/service/scm/security) совпали по SHA256 с reported
  eb6312bd431f40ff86e522c621c41e885defc454. Full installed source SHA остаётся
  UNCONFIRMED по частичной сверке, не выводится из локального HEAD.
- FILESERVER: только read-only проверки, новая Audit-служба NOT_INSTALLED;
  никаких SACL/auditpol/GPO/USN/SMB/file CRUD mutations. Original 72h FAIL сохраняется.

GATE A: PASS.
Исторический статус при закрытии A: GATE B IN_PROGRESS — начинается с accepted
merged-main SHA и повторной сверки Issue #22.
GATE C: BLOCKED — нет отдельного разрешения на новую службу, pilot root, SACL/policy и CRUD.

## Исторический ход 2026-10-13 — этап B

Промежуточные pending/failure ниже относятся к указанным ревизиям;
актуальный итог — в разделе «GATE B PASS».

- Branch `codex/storage-audit-001-b`, base accepted A merged-main
  dd65c4844e540f235b23f3c456ec09d8784f62e5. Fresh origin/main совпадает;
  Issue #22 остаётся OPEN. Existing Activity backend изменён только добавлением
  equivalent `read_sensitive_activity` guard; timeline/path history не переписаны.
- Additive frozen migration 0007: immutable evidence, dated identity/health
  witnesses, separate stream, versioned correlations и many-to-many candidates.
  UPDATE/DELETE/TRUNCATE witnesses запрещены. Upgrade/check/0007→0006 roundtrip
  сохраняет USN history; предшествующий destructive 0005 downgrade остаётся blocked.
- Own AUDIT_WINDOWS registration/token и retained HTTPS queue. Exact replay 202,
  altered receipt/event 409; host/source/volume binding и collector-domain 403.
  Old pre-B heartbeat digest/replay сохраняется (optional audit omitted when NULL).
- Freshness regression 0/1/2 WINDOWS и отдельный AUDIT_WINDOWS: audit heartbeat
  не обновляет USN heartbeat/source-success; stopped/missing USN не становится healthy.
  Stalled capture, unconfigured/policy/SACL unknown, gap/quarantine и stale delivery
  видны отдельно. Browser health expires locally при потере сети.
- Rule windows-security-usn-v1: HIGH только corroborated DELETE, не AccessMask сам
  по себе. Независимый prior FileId/link_count=1, dated aliases, coverage до/после
  всего lineage interval, 4663→4660 с host/boot/generation/SID/logon/process/handle,
  unique 4624. Multiple contexts → AMBIGUOUS/actor NULL. Late metadata/second SID
  отменяют прежний HIGH. CREATE/WRITE/RENAME пока access facts + явная причина UNKNOWN.
- Read-only runtime readiness: effective Audit File System Success и SACL всех
  approved SID на bounded selected scope (≤256 entries); root inheritance без
  descendant proof не считается coverage. NP/IO/reparse/overlimit/read failure
  fail closed; временная own-process privilege восстанавливается с проверкой.
  Никакого SACL/policy write. Policy loss latch'ит AUDIT_CONFIGURATION_CHANGED.
- RED→GREEN: absent ingest/routes/schema, 0/2-collector freshness, actor/context,
  old heartbeat replay, capture stalled, lagging cursor, later-read identity,
  metadata invalidation и SACL NP/IO/restore errors. Initial hardcoded migration-head
  test adjusted 0006→0007, без ослабления protected path-history downgrade assertion.
- Isolated genuine Python 3.13/PostgreSQL 16/strict HTTPS ingest and lost ACK PASS.
  100k synthetic audit events: EXPLAIN indexed bounded candidate query, no Seq Scan,
  ≤65 candidate rows. No production fixtures/raw XML.
- Full regression: `python -m pytest -q --tb=short` 848 passed/84 platform skipped;
  `python -m pytest tests/deployment -q --tb=short` 54 passed. Final focused after
  bounded equal-time/late-lineage fixes: 31 passed. Ruff/mypy/OpenAPI PASS.
  Web api:check/lint/typecheck/build PASS, Vitest 133 passed, Playwright 14 passed
  (desktop/mobile/reload, private POST filters, nonadmin deep link), i18n PASS.
  Gitleaks v8.24.3 redacted source scan PASS. Existing >500 kB build warning retained.
- Independent focused reviews: reported Critical 0; Important backend/UI/readiness
  findings reproduced and fixed. Final closure: no open Critical/Important findings.
- Central baseline freshly verified: image revision
  22667a67b6c5faceb914a114197e92b3a7bac2b7, schema 0006. Existing active checkout
  inaccessible for complete clean-status proof; do not overwrite it. New deployment
  must use an isolated clean release checkout with exact accepted SHA.
- Pre-deploy custom PostgreSQL archive: `pg_restore --list` PASS, off-VM encrypted
  DPAPI copy + decrypt/checksum verification PASS. Original API/Web images/config
  retained privately for rollback. No FILESERVER modifications.
- B source SHA/PR/exact head CI/merged SHA/exact main CI/deployed acceptance: PENDING.
  GATE B: IN_PROGRESS; CI and actual central acceptance remain mandatory.
- PR B #25, initial source 989b9ac59a717e2acadc4eaff41dec9564a23ad8,
  exact-head run 38414713338: backend/frontend/compose-smoke/production-smoke/secrets
  SUCCESS, sonar SKIPPED. windows-pilot FAIL: old CLI 14, SCM/runtime 81, USN 67
  and actual USN HTTPS 1 PASS; new Audit suite 68 PASS, installed-wheel deliver
  timeout 1 FAIL. RCA UNKNOWN pending fixed-code status/queue/HTTP diagnostics.
  No acceptance, merge or deployment from this SHA. Audit test moves before long
  USN regressions; every original regression still runs on a passing final source.
- Diagnostic source 24d78cbf30740668992f104a928e08aa287a52e1, run 38416807185:
  same native timeout, fixed-code diagnostics show first ACK/HTTP 202 and remaining
  backlog despite last HEALTHY frame. Reproduced Windows protected status-reader
  pin vs atomic replacement on an owned local temporary file: STATE_INVALID.
  No SCM/policy/FILESERVER mutation for the reproduction. Audit delivery now consumes
  a locked deep-copied in-memory status published after the sole writer succeeds;
  common ProtectedState checks unchanged. Portable RED→GREEN and Linux targeted
  runtime/delivery/actual HTTPS 24 PASS; independent focused review reports no open
  Critical/Important findings. Native exact CI must still close the original timeout.
- Source 6068582d0e87d4a98382e99f443221266a561088 / run 38419375267:
  protected status-reader removed, but installed deliver timeout remains (69 PASS,
  1 FAIL in Audit suite). The sharing reproduction alone did not establish the
  complete timeout RCA. Gate B remains IN_PROGRESS, no merge/deploy. Retain redacted
  delivery exception metadata and SCM state in the owned native fixture to identify
  the remaining failure; do not expose messages, locals or private paths.

- Native diagnostic progression: fe12bf0627be963bda746b37f77467acd77523c3 /
  run 38422046726: 70 PASS, 1 FAIL; delivery exception absent, SCM PID changed.
  b3d76ea70ded1e4d3227ac29be55c4f66a5efd03 / run 38423492872:
  own Application provider reports AUDIT_READ_FAILED. No unrelated event contents exported.
  3446b02e905b1dc3b1e6c6e16b9ce6a53a6f2545 / run 38425375281:
  71 PASS, 1 FAIL; bounded numeric diagnostics identify EvtNext Win32 4317,
  rather than a delivery failure. Independent diagnostic review Critical/Important 0;
  runtime/delivery 25 PASS, Ruff/mypy 122 files PASS.
- Pull subscription RCA: empty EvtNext may return ERROR_INVALID_OPERATION (4317)
  with zero returned events; treating this as fatal restarted the own SCM host before
  queued audit delivery. Follow the Microsoft manual-reset signal protocol, accepting
  4317 only for a zero-result EvtNext. Invalid handles and strict stale errors still
  fail/latch; no implicit new baseline. Portable RED 3 failures plus 3 negative passes,
  GREEN runtime/delivery 31 PASS, Ruff/mypy PASS. Exact native CI remains required.
  References: https://learn.microsoft.com/en-us/windows/win32/wes/subscribing-to-events
  and https://github.com/mhammond/pywin32/blob/main/win32/src/win32evtlog.i.
- Source 254b328593179623fb6f06df91c1fbc8704a6ea0 / run 38426238295:
  actual read/delivery progressed; Audit 77 PASS, 1 FAIL at restart retention.
  Fixture had asserted an unchanging queue after successful ACK, although successful
  delivery legitimately removes the head. Native fixture now withholds the ACK only
  after actual PostgreSQL acceptance of at least two evidence records, and proves
  that withheld-ACK branch was exercised; original record-count criterion retained.
  Independent review found two signal/coverage edge cases: reset-after-empty could
  lose a concurrent arrival, and EvtNext timeout did not prove drained coverage.
  Both reproduced RED (4 failures, 4 negative passes), fixed reset-before-drain with
  persistent draining state and a separate pending outcome. GREEN runtime/delivery
  33 PASS; no checkpoint/coverage advance on timeout. Exact native CI still required.

### GATE B PASS — 2026-10-13

- PR B https://github.com/BorisDruzak/storage-console/pull/25 merged.
  Final source head 9bc560319c29d0da955d143b627d167e3d735270.
  Exact-head CI https://github.com/BorisDruzak/storage-console/actions/runs/38427397293:
  backend/frontend/windows-pilot/compose-smoke/production-smoke/secrets SUCCESS,
  sonar SKIPPED (unconfigured).
- Final native Windows: Audit 80 PASS, original CLI 14 PASS, SCM/runtime 81 PASS,
  USN 67 PASS, actual USN HTTPS/PostgreSQL/Activity 1 PASS. Installed Audit owns
  its LocalSystem process/state/DPAPI, captures scoped real runner Security events,
  preserves a committed-but-unacknowledged receipt and retained bytes across restart.
  Strict stale handling remains; concurrent signal and native timeout regressions PASS.
- Final Python 3.13/PostgreSQL CI: 860 PASS / 84 platform skips. Deployment tests,
  migration upgrade/check/downgrade/upgrade, Ruff, mypy (122 source files plus
  deployment scripts), shellcheck, generated OpenAPI and secret scan PASS.
  Frontend 133 PASS and Playwright 14 PASS; final isolated runtime/delivery/real HTTPS
  focus 34 PASS. Independent focused reviews: no open Critical/Important findings.
- Merged main 3d018245a91bec2092e10f38fb06e0c51c967970.
  Exact push-main CI https://github.com/BorisDruzak/storage-console/actions/runs/38428786928:
  all six mandatory jobs SUCCESS, sonar SKIPPED. Deployment waited for this result.
- Fresh verified custom PostgreSQL backup and checksum/decryption-verified encrypted
  off-VM copy prepared before deployment; original API/Web/config retained for rollback.
  No destructive schema downgrade or DB restore performed. Migration 0007 is additive.
- Deployment uses a fresh clean checkout of the exact merged SHA, preserving the
  original active checkout. Initial scoped build failures occurred before writer stop;
  read-only confirmation still showed original API SHA and schema 0006. The operations
  container required a checksum-verified official Buildx binary and writable temporary
  Buildx state. Host-global plugin installation and public lifecycle edits NONE.
  Original canonical preflight/deploy/healthcheck gates then PASS with actual host NTP proof.
- Actual central API/worker/Web image revisions all
  3d018245a91bec2092e10f38fb06e0c51c967970; PostgreSQL schema 0007;
  API/worker/Web/PostgreSQL all HEALTHY. Strict TLS, HTTP redirect, health/readiness,
  root 200 and unauthenticated API 401 PASS.
- Genuine admin Chromium, ru-RU/Asia-Yekaterinburg, strict TLS: login/Sources/Activity
  200; Windows Security Audit NOT_CONFIGURED, empty authorized POST search without
  query filters, old USN change has NULL actor and explicit uncertainty. Desktop,
  mobile 390px and reload PASS, horizontal overflow/page errors 0. Sensitive screenshots
  and snapshots remain in the approved private evidence location. No production fixture.
- Existing source ID and WINDOWS collector ID/count preserved, heartbeat and cursor
  advanced after deployment, USN HEALTHY and CONTINUOUS_SINCE_BASELINE before/after.
  Existing token acceptance and historical data retained; no USN reinstall/restart.
  Isolated 0/1/2-collector and all nonadmin 403 regressions PASS. Real central evidence
  remains absent until an authorized pilot; no real nonadmin accounts created for tests.
- Issue #22 remains OPEN; latest main synchronized before merge, no competing open PR.
  Existing timeline/path algorithms retained; only equivalent sensitive-read guard added.
- FILESERVER installation, SACL/audit policy/GPO changes and synthetic file CRUD NONE.
  GATE C BLOCKED. Private Russian operator plan prepared: two accounts/two PCs,
  30-minute window, <=20 total sanctioned operations, <=2 MiB, precise approval fields,
  stop conditions, rollback and cleanup/service disposition. Ordinary inventory schedule
  must admit the <=60-second identity witness; cadence/USN changes are not a workaround.
  Actor/client proof for real domain users remains NOT ACCEPTED, not implied by CI.
- Prepared pilot wheel source 3d018245a91bec2092e10f38fb06e0c51c967970;
  SHA-256 b05d99390fd211cc778d0d850a8390132cb441d460e40441847a5f59b21421ab.
  Transfer checksum verified; all 124 packaged Python sources match committed source
  with CRLF/LF normalization. Stored privately, NOT_INSTALLED on FILESERVER.
  This is package preparation, not exact-artifact installed/live acceptance.

## Historical preparation baseline (перепроверять; live результаты ниже)

- Baseline documentation main перед созданием задачи: 34d49cc5c1aa42953ce3d400ff9e9ddc448bcac9.
- Issue #22 (MVP-005 History/Statistics): OPEN на момент подготовки; ожидаются возможные конфликтующие изменения Activity/RBAC. Сверять самый новый main/PR.
- Existing Windows USN Collector после USN-SOAK-001: source eb6312bd431f40ff86e522c621c41e885defc454 по опубликованному отчёту.
- Existing central API во время исходного USN soak: 22667a67b6c5faceb914a114197e92b3a7bac2b7; перед deploy проверить фактическую версию заново.
- Original USN-SOAK-001: 72h FAIL, 5 service crashes. Никаких выдуманных утверждений о long-term PASS.
- New Security Audit Collector: NOT INSTALLED / NOT ACCEPTED.
- Real effective policy preflight выполнен read-only; pilot SACL/GPO owner UNKNOWN.
- Two users / two PCs live test: NOT AUTHORIZED / NOT PERFORMED.

## A — read-only preflight и независимый Security Collector

GATE A: PASS — completed results and exact CI above; template below is historical.

~~~text
Started at / exact source SHA:
Read-only effective audit policy / GPO:
Read-only Security log capacity/rate:
Scoped SACL configured? (yes/no/unknown):
Own independent service installation test:
SCM / SYSTEM / DPAPI / TLS:
4663, 4660, 4624, 1102 parsing + native Windows proof:
Out-of-scope filtering / 4624 privacy:
Strict Windows Event Log bookmark / gap / log clear:
Atomic bookmark / outbox / byte-identical lost ACK:
USN unaffected, separate process/lock/state:
Targeted RED→GREEN + full relevant regression:
Independent Critical/Important review:
PR / exact head CI:
Merged SHA / exact main CI:
No FILESERVER mutation confirmed:
Remaining blocker / next step authorized:
~~~

## B — central evidence и correlation engine

GATE B: PASS — completed exact CI and central live checks above; template below is historical.

~~~text
Source SHA / PR / merged SHA / exact CI:
Existing source and original USN collector identity preserved:
New AUDIT_WINDOWS role and independent credential:
USN stream-only continuity despite two collectors:
AUDIT configured/healthy/stale/gap independent:
Schema migrations / verified backup / rollback:
Idempotent evidence, replay conflict test:
4663↔4660↔4624 join tests:
Audit↔USN strong match / ambiguous / unknown:
Distinct host/boot/logon/handle; 2 concurrent users:
Same time/path only cannot produce high confidence:
No raw XML / out-of-scope evidence leaked:
Admin-only read API, RBAC 401/403/200:
Russian UI + Playwright desktop/mobile:
Isolated genuine strict HTTPS/PostgreSQL:
100k synthetic events, bounded query plans:
Exact head/main CI and Sonar status:
Central deployed SHA and real preserved USN freshness:
Independent review and known limitations:
Remaining blocker / next step authorized:
~~~

## C — operator-approved real pilot

GATE C: PARTIAL / further live execution BLOCKED. Four approved bounded passes
were fully rolled back. Strong live attribution for both users and byte-identical
pending replay are not accepted. The extended <=36-operation allowance is exhausted.

### Live execution 2026-10-13 UTC (sanitized)

- Operator approved the separate service, narrow SACL/policy and two existing domain
  accounts on two distinct computers; final Audit state STOPPED, evidence preserved.
  Actual identities, topology, paths and Security evidence remain private.
- Effective-policy/GPO preflight found no managed FileSystem setting requiring a
  bypass. Temporary FileSystem Success and synthetic-directory write/append/delete
  SACL applied only to the two approved SIDs. Failure, Logon policy, working/root
  DACLs, GPO, SMB configuration and USN journal were preserved.
- Initial independent Audit install used source
  `3d018245a91bec2092e10f38fb06e0c51c967970`, wheel SHA-256
  `b05d99390fd211cc778d0d850a8390132cb441d460e40441847a5f59b21421ab`; offline
  bundle/file hashes and protected own-code ACL validation passed.
- First pass 17:50–18:20 UTC: eight operations. Audit restart retained bookmark with
  no gap/queue; this was not pending byte-identical replay. Full rollback verified.
- Second pass 19:00–19:20 UTC, reply «делай сейчас»: both CREATE/WRITE/RENAME,
  common-file negative test and bounded cleanup. First two passes: 20 operations,
  345 bytes. Independent inventory was real but the identity-freshness window was
  missed. No matching requirements were relaxed.
- Real evidence from these passes: 24 scoped 4663 + five linked 4660, two SIDs and
  seven session contexts. A private read-only exact SID/logon lookup found Type 3
  logons version 3 with IP and no WorkstationName. These facts were not manually
  backfilled into the centre. Centre 4624 remains zero; no client identity claim.
- After normal USN retry recovered, second-pass Activity held 11 UNKNOWN, two
  ACCESS_OBSERVED and six AMBIGUOUS; actor was NULL for all 19 results. No false
  cross-user attribution was reported. Real strict-TLS admin audit/source pages,
  desktop/mobile/reload: no page errors or overflow.
- Four controlled synthetic authorization sessions exercised actual deployed
  viewer, analyst, storage_operator and auditor restrictions: /auth/me 200, three
  protected GETs and valid-CSRF audit-search POST all 403/no evidence payload;
  selected Source Detail loaded, Audit controls hidden. This proves authorization,
  not actual LDAP authentication. Scoped fixture users disabled and sessions revoked
  (active count zero); existing accounts/roles unchanged. A cleanup selector failed
  during concurrent one-off preflight; fixed oneoff=False and explicit cleanup
  verified zero sessions. No cleanup PASS was claimed before this verification.
- Final extension, reply «Разрешаю всё необходимое» to the concrete 20:00–20:20 UTC
  plan: eight additional operations, cumulative limit 28, and 30 seconds audit-only
  HTTPS-ingest 503. Same directory/accounts/computers and rollback. Per-pass <=8 and
  cumulative <=28 guarded under the existing atomic single-flight operation ledger.
- Both participants completed CREATE/WRITE/RENAME, then DELETE after independent
  ordinary inventory contained both FileIds/link_count=1 (witness ages ~7 seconds).
  Three passes total **28 successful operations / 475 bytes written**. No USN forced
  inventory, cadence change, service restart or queue clearing was performed.
- The exact Audit-ingest route returned 503 for 30 seconds under the deployment lock;
  self-contained restoration used same-directory verified files and atomic rename.
  Original configuration restored; real strict-TLS browser POST without collector
  credentials returned 401 afterwards, proving active 503 was removed. Other routes,
  TLS, FILESERVER firewall and USN ingest were not blocked. A late review found
  restoration nginx-test failure could be masked; helper corrected and live route
  restoration verified independently. This does not establish pending replay.
- Final queue check showed AUDIT_BOOT_CHANGED, zero queued batches. The service had
  refused capture at startup; it did not collect the final CRUD as Security evidence.
  Native read-only RCA: unchanged OS boot and old-USN process creation, but exact
  SystemTimeOfDay BootTime changed by 3820 ticks (0.382 ms). The old numeric epoch
  used this mutable value as boot identity. Real final Activity: 14 UNKNOWN, actor
  NULL throughout. No CORRELATED_HIGH or successful replay is claimed.
- At 20:07 UTC, Audit STOPPED; temporary SACL/Success policy restored, Failure bit and
  original root ACL verified, empty owned folder removed through retained NTFS
  identity. Original USN Running with its unchanged PID; cursor advanced normally,
  own pilot nodes gone, queue empty. Config/credentials/bookmark/evidence/GAP retained.
  Centre reports Audit GAP separately from USN HEALTHY. No automatic baseline reset.

### Compatibility corrections and exact deployed provenance

- PR #27 `fix(ingest): preserve USN index inference in prepared plans`:
  head `d16fd298a75f951f5944d0bda86379515562d180`, merge
  `21294c9cdae9597c55c9421957234821cdd1b498`. Pre-existing parameterized partial-index
  predicate failed PostgreSQL generic prepared plans (42P10/503), blocking changes
  while heartbeat stayed fresh. RED two tests; GREEN eight idempotency tests and
  65 targeted/deployment/schema checks. Independent Critical/Important zero. Exact
  head run 38449850312 all six SUCCESS/Sonar SKIPPED. Main run 38451204922 initially
  failed native STATE_UNAVAILABLE while reading the USN queue; provider attempt 2
  completed all six SUCCESS on the same merge SHA. The initial failure's cause was
  not confirmed. Verified backup and canonical deploy passed; normal USN retry then
  drained backlog to zero without manually replaying or altering the collector.
- PR #28 `fix(audit): accept Windows network logon event version 3`:
  head `151aeeb7eb93bb20beed67b2f1334091c8313b01`, merge
  `ef1daf13e5e3130565981ab11ee6f401c9e04749`. v3 accepted only for 4624; same minimal
  fields/scoped linking; v4 and other-event v3 rejected. RED parser returned None;
  GREEN 103 Audit regression tests and final event/HTTPS selection 25 PASS/eight
  Windows-native SKIP on Linux. Independent Critical/Important zero. Exact head
  run 38453315506 and main run 38454679148: all six SUCCESS/Sonar SKIPPED.
- Central deployed **ef1daf13e5e3130565981ab11ee6f401c9e04749**, schema 0007, all four
  services healthy, exact image labels verified. Fresh PostgreSQL custom backups,
  pg_restore --list and hash-verified protected copies off VM preceded each deploy.
- The third-pass stopped Audit runtime used the exact merge SHA above; wheel SHA-256
  `5e979299e826ef8fc20ced8bf13251ccb79c3c8f07d7b6dd8e11625796862b17`; all 124 installed
  Python file bytes verified. Config, credentials and bookmark SQLite hashes remained
  unchanged. Original USN package/state/token/cadence/PID untouched. The original USN
  whole-package SHA remains unconfirmed; checked critical modules match its baseline.
- PR #29 `fix(audit): keep boot identity stable across clock corrections`:
  head `26984c3114b65980b4ae9be84dae3dbe50b0e881`, merge
  `982c442e5760d265efba8e59bd2933b4b20e2889`.
  Independent review Critical/Important zero. Focused correction: immutable local Kernel-General boot
  event identity, bounded current-boot consistency check, no old-witness fallback or
  automatic GAP clearance. Nine regression tests RED; 148 Audit/USN tests GREEN,
  nine Windows-native SKIP on Linux; 54 deployment tests, Ruff/mypy131/strict6,
  OpenAPI and source secret scan PASS. Read-only candidate on FILESERVER returned a
  stable epoch across three calls and retained the existing GAP. Exact head run
  38461692345 and merged-main run 38462941302: all six SUCCESS/Sonar SKIPPED.
  Main native checks: Windows CLI 14, Audit 84, SCM 81, USN 67 and real-USN HTTPS 1
  passed; backend 874 PASS/85 SKIP. Own stopped installed wheel SHA-256
  `d15e06d01e2af2b03ffbdb0cac6018fa03ea5cbe2d42f8be50d10dcb8e0fd6a5`:
  all 124 Python files verified; old state/config/token hashes preserved.
  Collector-only correction required no central API/Web redeployment: central
  remains the separately verified `ef1daf13e5e3130565981ab11ee6f401c9e04749`.
- Fourth pass 21:00–21:20 UTC was explicitly approved, including a new protected
  Audit state/generation, eight additional operations (cumulative <=36) and another
  audit-only 30-second 503. Old state and its latched AUDIT_BOOT_CHANGED were preserved
  intact. New state retained enrollment, scoped roots/SIDs and credentials, with the
  stable native boot identity; no old GAP was cleared. Audit current HEALTHY,
  policy/SACL, generation and native SCM binding were verified before every CRUD.
  A stopped/GAP negative control refused file operations before budget reservation.
- Both accounts completed CREATE/WRITE/RENAME. Two real scoped 4624 version-3 network
  logons and two different Security-provided client IPs reached the centre. No
  WorkstationName was reported and no computer name was inferred from an IP.
  An independent ordinary USN inventory observed both renamed FileIds/link_count=1.
  The controller's manual analysis delayed DELETE beyond the identity-validity
  window; admission refused without deleting or consuming its operation budget.
  This was an execution error, not an unavailable inventory or relaxed requirement.
- Permission to retain the two files and move their remaining DELETE/replay to a
  later window was requested but had not arrived before cleanup. Both remaining
  authorized DELETE operations were used only for cleanup; their stale identity
  witnesses cannot establish CORRELATED_HIGH. At 21:18 UTC the owned empty folder
  was removed through its pinned NTFS identity, temporary SACL/Success policy and
  original root ACL were restored, Failure preserved, Audit STOPPED and original
  USN Running with the same PID. Four passes total **36 operations / 605 bytes**.
  New Audit queue empty, checkpoint retained and GAP null; this is not pending replay.
  The fourth-pass 503 was not executed. The proposed two-file transfer is superseded
  because those files were cleaned up; it does not authorize further CRUD.
- Final genuine strict-TLS admin browser: 45 total retained audit events (34 scoped
  4663, seven linked 4660, four scoped 4624), two SIDs, eleven session contexts and
  two Security-provided client IPs. Fourth-pass Activity: fourteen UNKNOWN, actor
  NULL throughout. Desktop/mobile/reload had no page errors or overflow. Exact
  audit-ingest route returned unauthenticated 401, confirming no residual 503.
  Service STOPPED and last accepted HEALTHY evidence are distinct observations;
  no claim of a currently collecting stopped service is made. Health-check browser
  session logged out and closed. Real file-history navigation was also verified,
  but live strong actor attribution and queued replay remain unaccepted.
- Issue #23 remains open; final live file-history attribution for both users and
  pending byte-identical replay remain required. Any further CRUD needs a separately
  approved new window/operation extension; the new valid Audit generation can resume
  without another baseline reset if its strict bookmark/continuity still validate.
  Before another pass, review an automatic dependent inventory-to-DELETE/replay
  runner so manual controller pauses cannot consume the freshness window. C stays
  draft; its final exact-head/main acceptance and merge are not claimed. Original
  USN-SOAK-001 remains FAIL; no new long-term PASS is inferred.

### Поздний volume witness и разрешённое продолжение

- Read-only RCA четвёртого прохода: фактические Security/USN совпадения существовали,
  но часовой volume inventory поступил позднее обычного ±120-second receipt window.
  Уже закрытое dated alias coverage не вызывало повторного сопоставления старых
  изменений. Сильные identity/coverage/delete-chain критерии не ослаблялись.
- PR #30: https://github.com/BorisDruzak/storage-console/pull/30,
  `fix(audit): reconcile changes after late volume witnesses`. Для принятого forward
  WINDOWS volume observation транзакционно создаётся отдельная idempotent job на
  реально продвинутый source/volume interval; pagination по time/UUID, page 32.
  Duplicate, старые/equal receipts, object-only batches и heartbeat её не создают.
  Миграция 0008 добавляет только source/volume/time/id index; history/RBAC и runtime
  существующего USN не изменены. Issue #22 остаётся в своём scope.
- RED: обе arrival-order проверки оставались UNKNOWN после достаточного позднего
  witness; GREEN: обе проходят. RED EXPLAIN на 100k synthetic rows фильтровал 19,845
  посторонних строк; GREEN first/middle/last pages ≤33 rows, ≤65 filtered rows,
  ≤128 shared buffers, без sequential scan, все 65 target rows посещены ровно один раз.
  Проверены retry, изоляция source/volume, receipt replay, отсутствие identity/coverage,
  transactional rejection и 0007→0008→0007→head с сохранением immutable evidence.
- Focused backend: 31 PASS; Audit/USN/ingest/schema/deployment regression:
  308 PASS, 17 native Windows SKIP на Linux. Independent review: zero remaining
  Critical/Important. Ruff, mypy122/strict deployment6, OpenAPI, Alembic check,
  tracked-source Gitleaks и diff check PASS.
- Первый head `4fe373acd1bc727c2609c569d55f5e97183dba67`, run 38474010920:
  пять jobs PASS, backend 882 PASS/85 SKIP и три FAIL. Две migration assertions
  фиксировали старый head 0007; прежняя USN timing fixture зависела от 1.2-second
  wall-clock deadline. Эти ошибки сохранены в истории приёмки, не скрыты rerun.
- Отдельные test commits: `9f6b3d222ebf71e3bb05b2df7b0e415d30aef3fe`
  (`test(migrations): preserve current revision on rejected rollback`, один migration
  test file) и `0e691e3fdfc61c6caa4a258fb86a6163683635dc`
  (`test(collector): control heartbeat proof timing deterministically`, один USN test
  file). Protected revision проверяется сразу после rejected downgrade; controlled
  clock ждёт capture completion до следующего шага. Production USN не менялся.
  Target 14 PASS, пять timing повторов PASS, disabled heartbeat cap даёт expected RED.
  Fresh static/schema/secret checks PASS; focused review zero Critical/Important.
- Exact PR head `0e691e3fdfc61c6caa4a258fb86a6163683635dc`, run 38477066486:
  все шесть обязательных jobs SUCCESS, Sonar SKIPPED. Backend 885 PASS/85 SKIP;
  Windows CLI14/Audit84/SCM81/USN67/real-USN HTTPS1 PASS. PR объединён в
  `05eaa7fadd3d6d9c9833f40f6811b68db771a755`; exact main run 38478424249: все шесть jobs SUCCESS, Sonar SKIPPED.
- Fresh verified PostgreSQL backup текущего central EF/schema0007 и hash-verified
  protected off-VM copy готовы. Read-only table-size/EXPLAIN: 710 changes, 917,504
  bytes total, 0.396 ms. После exact main six-job PASS canonical stop old API/worker → migrate → start
  matching API/worker/Web выполнен. Central deployed
  `05eaa7fadd3d6d9c9833f40f6811b68db771a755`, schema0008; healthcheck PASS.
  Actual new-index EXPLAIN: Index Only Scan, 14 rows, six shared buffers, 0.241 ms.
- Оператор ответил «Разрешаю любой лимит»: operation-count cap снят. Следующий
  закрытый план выбирает 23:00–23:25 UTC вокруг обычного inventory; плановые 12 CRUD
  включают прежний согласованный shared-file negative. Те же две учётки/ПК и папка,
  ≤2 MiB, 30 секунд exact Audit-only 503, без forced inventory/USN изменений. Уже
  существующая valid Audit generation/state сохраняется, новый baseline не создаётся.
- До выполнения независимое ревью private automatic runner обязательно. Actual
  local guards: 8 admission, 8 target-chain, 6 executed-finally outcome и 4 pair lifecycle/timing checks PASS,
  без host/file операций. B/старый 4660 не заменяет A DELETE; actual 503 interval,
  exact enabled-WINDOWS source/volume/path witness и durable rollback failure
  проверяются отдельно. Shared pair и полный dependent flow прошли focused independent review: zero
  remaining Critical/Important. Bounded supervisor timeout сохраняет client UNKNOWN
  и owned folder, но не задерживает Stop/policy/SACL rollback; исходный cfg не пишет.
- Read-only перед продолжением: Audit STOPPED/PID0, native registration verified,
  current_healthy_verified=false, queue0/GAP null/checkpoint retained, old USN Running
  с прежним PID. Read-only strict resume anchor/same boot подтверждены без изменения new/old state;
  old latched GAP сохранён целиком. Actual admin/mobile/reload после central deploy
  PASS, Audit STALE/USN HEALTHY, 14 UNKNOWN, unauthenticated Audit401.
  Новый проход ещё НЕ выполнен. C остаётся PARTIAL до реальных
  CORRELATED_HIGH для обеих учёток, negative AMBIGUOUS/UNKNOWN, queued replay и
  полного rollback/UI/acceptance; Git publication и CI этого не заменяют.

### Фактический пятый проход и проверка replay

- 23:00–23:25 UTC 13 октября: реально выполнены 10 операций, суммарно 46
  операций / 820 bytes; незавершённых reservations нет. Две учётки работали через
  SMB с двух согласованных компьютеров. Одновременный shared-file negative
  выполнен; в сохранённой выборке его WRITE пока UNKNOWN до позднего dated alias.
  Шесть AMBIGUOUS относятся к original-name операциям A/B, не к shared pair;
  финальная приёмка проверяет точный shared WRITE, source и approved window.
- B DELETE выполнен после обычного inventory. A DELETE остановлен до reservation:
  private admission требовал witness не старше 30 секунд; последовательные проверки
  исчерпали этот срок. Свидетельство FileId в payload существовало: отсутствие
  FileId НЕ является установленной причиной. Сильный engine предел 60 секунд
  не изменён. Продолжение использует admission 45 секунд и native UTC deadline
  oldest witness +57 секунд непосредственно перед DELETE.
- Разрешённые 30 секунд HTTP 503 затронули только точный Audit ingest route.
  Исходная nginx-конфигурация восстановлена; unauthenticated Audit route снова 401.
  Один queued 4660 batch сохранил raw receipt digest и event identity между двумя
  read-only STOPPED snapshots. После отдельного обычного resume доставка дала
  BYTE_IDENTICAL_RECEIPTS: один batch, одно unique event, zero duplicate event IDs;
  queue0 / GAP null. Replay не считается сильной атрибуцией B DELETE: его coverage
  соседствует с outage.
- Audit STOPPED/PID0; temporary policy Success и SACL восстановлены, Failure bit
  и root ACL сохранены; старый USN Running с прежним PID. Два собственных synthetic
  файла пока удержаны для продолжения; полный cleanup ещё не объявлен.
- Actual strict-TLS admin/mobile/reload: 62 events (4624=8, 4660=8, 4663=46),
  два SID, 15 session contexts, два Windows-reported client IP; workstation не
  выведен из IP. В текущем окне 17 changes: UNKNOWN9 / AMBIGUOUS6 /
  ACCESS_OBSERVED2. CORRELATED_HIGH для обеих учёток ещё не подтверждён.
- Следующее узкое продолжение: 00:00–00:25 UTC 14 октября, те же folder/accounts/
  компьютеры/generation, шесть плановых операций, без нового baseline и без 503.
  После обоих DELETE — clean coverage, Stop, scoped rollback/cleanup; поздний
  ordinary volume witness проверяется read-only. Новый native check не разрешает
  DELETE после 60-second engine identity bound. Source review zero Critical/Important;
  actual local checks: admission9, target-chain8, outage-finally6, positive-finally5,
  pair lifecycle/timing4 PASS. Installed PC-B helper обновлён и проверен:
  exact new SHA, trusted owner/write grants, unchanged file/directory ACL.
  Четыре реальные браузерные role sessions на новом central получили 403
  по четырём Audit endpoints, no sensitive payload и hidden pane; fixtures
  отключены, active sessions0, existing roles unchanged, LDAP login не заявлен.
- PR #26 остаётся draft. Exact head
  `4c59a6deb918269dde30c67345fc68609505d715`, run 38480628501:
  шесть required jobs SUCCESS, Sonar SKIPPED. Это CI предыдущего ledger head;
  C остаётся PARTIAL, окончательная live приёмка и final head/main CI не заявлены.

### Фактический шестой проход и узкий параллельный DELETE

- 00:00–00:25 UTC 14 октября: B CREATE/WRITE/RENAME PASS (три операции /
  65 bytes); DELETE не запущены, отказ до reservation. Суммарно 49 операций /
  885 bytes, незавершённых client reservations нет. Три собственных файла удержаны.
- Actual timing RCA: обычное identity observation 00:06:39, повторный central
  witness probe закончился 00:07:26; старый 45-second admission правильно отказал.
  Последовательные native Status/clean-heartbeat проверки расходовали freshness;
  FileId в данных был. Engine60 / native57 / admission45 не ослаблены.
- Automatic Stop/Restore PASS: Audit STOPPED/PID0, root ACL и Failure bit сохранены,
  temporary SACL/Success восстановлены, old USN Running с прежним PID. Queue0 /
  GAP null, checkpoint retained. Read-only strict resume/same boot подтверждены,
  new/old states не менялись диагностикой; old latched GAP сохранён.
- Поздний обычный volume witness реально разрешил fifth negative: две именно
  shared-file WRITE получили AMBIGUOUS / MULTIPLE_CONTEXTS, actor NULL. Actual
  strict-TLS admin/mobile/reload: 67 events (4624=9, 4660=8, 4663=50), SID2,
  session contexts16, Windows client IP2; в расширенной выборке changes23 /
  UNKNOWN9 / AMBIGUOUS11 / ACCESS_OBSERVED3. Граница fifth window/source/target
  проверяется отдельно; эти общие counts не подменяют scoped proof.
- Операторское разрешение на любой operation-count сохраняется. Следующее узкое
  окно 01:00–01:25 UTC: только два DELETE разных файлов параллельно и shared-file
  cleanup (три операции), прежние folder/accounts/PC/generation, no new baseline,
  no CREATE/no 503, ≤2 MiB. После захвата clean coverage → Audit STOPPED → scoped
  rollback/cleanup; поздний ordinary volume witness проверяется read-only.
- Private batch делает один реальный native SCM/current HEALTHY check и один
  fresh FileId query. Local cache проверяется после witness, перед atomic two-row
  reservation и непосредственно перед spawn: HTTP200, exact generation/host,
  configured policy/SACL, gap null, clean backlog/error, age0–5s/collected0–35s,
  old USN HEALTHY/continuous. Absolute native deadline имеет ≥12s remaining перед
  reserve/spawn, оба клиента проверяют oldest identity +57 перед File.Delete.
  Остальные strong engine criteria неизменны; B helper exact SHA проверяется при
  загрузке. Любой частичный результат сохраняет reservations, no automatic retry,
  rollback удерживает own folder; pre-spawn отказ фиксирует operations0.
- RED отсутствующий dispatch → GREEN actual success/partial launch/timeout/bad
  receipt/wrong identity controls5. Existing admission/finally/pair32 и actual
  scope/complete-chain23 PASS; pycompile/PowerShell parse/node syntax PASS.
  Independent focused review zero remaining Critical/Important. Secret scan
  tracked sources PASS, findings0. C остаётся PARTIAL; positive HIGH для обеих
  учёток и окончательная exact-head/main приёмка ещё не объявлены.

### Седьмой проход: capture подтверждён, историческое покрытие не принято

- Окно 2026-10-14 01:00–01:25 UTC: оба DELETE выполнены двумя согласованными
  доменными учётками с двух компьютеров; native receipts PASS, дочерние процессы
  завершены. Суммарно 52 тестовые файловые операции / 885 bytes; незавершённых
  операций нет. Разрешение оператора снимает численный лимит операций, сохраняя
  узкую папку, две учётки/ПК и остальные границы пилота.
- DELETE в 01:07:01.600 и 01:07:03.262 UTC имеют по одной полной цепочке
  4663 → 4660 с предшествующим 4624 Type3. Read-only проверка реального engine:
  PROVEN_PRIOR_IDENTITY, возраст prior FileId 15.300 / 16.810 s, расхождение
  Windows/USN 0.000781 / 0.001268 s; подтверждены два разных клиентских IP.
  Dated alias ещё отсутствует. Это диагностические предпосылки, не HIGH/PASS.
- Историческое coverage FALSE для обоих DELETE: один Audit heartbeat
  01:07:17.641 UTC имеет backlog_clear FALSE. Последнее необходимое событие
  принято в 01:07:19.222 UTC. WINDOWS coverage чистое. Критерий engine не
  ослаблен; повторная корреляция после inventory не исправляет такое покрытие.
- Audit остановлен в 01:08:34 UTC, rollback завершён в 01:08:38 UTC:
  исходные SACL/policy/Failure bit и root ACL восстановлены, собственная папка
  и собственный helper второго ПК удалены. Queue0, GAP null, strict bookmark
  resume/same boot проверены read-only; старое состояние с GAP сохранено целиком.
  Legacy USN PID/конфигурация/cadence без изменений. C остаётся PARTIAL.
- Следующий согласованный проход 02:00–02:25 UTC: восемь CRUD, та же узкая
  папка и учётки/ПК, без 503 и без нового Security baseline/generation.
  Native Status проверяется перед ожиданием свежего чистого heartbeat;
  captured age ≤5 s перед новым witness, ≤8 s перед reservation/dispatch.
  FileId admission45 / native deadline57 / engine60 s сохранены. После DELETE
  coverage проверяется через API без дополнительных SSH-входов.
  RED missing age parameter → GREEN: 7 actual age boundaries; regression
  admission/chain/rollback/pair32, post-coverage11, dispatch lifecycle5 PASS.
  Independent focused review: замечание по внешнему timeout устранено
  ограниченным supervisor160 s для фаз native50 + heartbeat40 + witness18 +
  dispatch25 + reaping10 s; повторное ревью Critical/Important0.
  Успех capture по-прежнему требует последующего реального HIGH и UI-приёмки.

~~~text
Explicit approval reference (not this technical task):
Exact narrow synthetic folder (private evidence only):
Effective GPO / Audit File System before and after:
Approved SACL diff and rollback:
Security log capacity risk accepted:
Approved test UserA and UserB (private evidence only):
Approved PC-A and PC-B (private evidence only):
Domain SID A/B observed in native 4663:
Logon IDs and 4624 Type3 session linkage:
SourceNetworkAddress/WorkstationName actually available?:
USN CREATE/WRITE/RENAME/DELETE evidence:
4660 deletion w/out fabricated path:
Matching / ambiguous / unknown results and reasons:
No false cross-user attribution:
Admin Web history and evidence, nonadmin 403:
Bookmark restart, network loss/replay, queue:
Old USN remains healthy, unchanged cursor/collector identity:
Operator-approved cleanup and SACL rollback:
No reboot / no 5145 / no WEF:
Exact installed Audit package SHA, central deployed SHA:
Issue/PR/CI and live acceptance evidence:
STOP or precise remaining operator action:
~~~

## Mandatory reporting

- Не ставить PASS по одному CI, без реального подтверждения обязательных live критериев.
- Не подменять отсутствие 4663/SACL «нет событий». Не назначать пользователя по одному совпадению времени.
- Не раскрывать реальные имена, SID, IP, пути, XML Security Events, ключи, токены и operator screenshots в публичном репозитории. Хранить это только в согласованном закрытом месте.
- Не продолжать 5145, WEF, централизованный EVTX архив и версионные копии без отдельной задачи.
