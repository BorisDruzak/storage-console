# STORAGE-AUDIT-001 — журнал приёмки

Задача: docs/tasks/storage-audit-001-windows-security-attribution.md

**Статус живой приёмки:** A PASS → B PASS → C PASS. Окончательные exact-head/main
SHA и CI публикации этого ledger фиксируются в PR #26; source CI приведён ниже.
Оператор отдельно снял лимит числа операций; узкий scope, объём данных,
30 секунд Audit-only 503 и итоговый Audit STOPPED сохранены.
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

## Исторический ход C — operator-approved real pilot

Исторический статус после первых четырёх проходов: GATE C PARTIAL /
further live execution BLOCKED. Four approved bounded passes
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

### Восьмой проход: отказ допуска до DELETE, сохранены исходные свидетельства

- Окно 2026-10-14 02:00–02:25 UTC: обе согласованные учётки выполнили
  CREATE/WRITE/RENAME через SMB, native receipts PASS. Суммарно 58 файловых
  операций / 1015 bytes. DELETE не выполнены и не зарезервированы: bounded
  ожидание свежего clean heartbeat завершилось отказом допуска до dispatch.
  Два собственных переименованных файла сохранены для следующего inventory.
- Stop подтверждён 02:07:50 UTC, rollback 02:07:54 UTC: SACL/policy/Failure bit
  и root ACL восстановлены, исходный USN PID сохранён. Queue0, GAP null, strict
  bookmark resume и same boot проверены read-only. C остаётся PARTIAL.
- Read-only PostgreSQL timing: heartbeat interval около 30 s, captured age
  при report 0.111–1.042 s, receipt timestamp delta 0.239–0.278 s (не ACK completion latency); backlog0/GAP false.
  Точная причина отказа локального admission gate **UNKNOWN**; не объявлена
  неисправность Windows collector и не ослаблены критерии Correlation Engine.
- В том же согласованном окне проведена heartbeat-only диагностика140 s,
  без CRUD/503/нового baseline. Затем Audit STOPPED, temporary rollback PASS.
  Actual clean_cache5 PASS; 120 API samples, 12 fresh5 samples,
  minimum capture age0.974 s, maximum response age0.237 s. Для последующего
  прохода добавлена private трасса времени и условий admission; production
  identities, IP, paths и event bodies в Git не попали.
- Продолжение 03:00–03:25 UTC: только два DELETE существующих собственных
  файлов после обычного inventory; CREATE/WRITE/RENAME повторно не выполняются.
  Та же папка/учётки/ПК/поколение, без 503 и нового Security baseline.
  Все guards45/57/60 s и clean5/8 s сохраняются; failure удерживает собственные
  файлы и исходы, success удаляет только собственную папку/helper и оставляет
  Audit остановленным. Existing USN и MVP-005 не изменяются.

### Девятый проход: причина operational admission отказа подтверждена

- 03:00–03:25 UTC: DELETE не выполнены, reservations0; total58 операций /
  1015 bytes. Audit STOPPED, temporary SACL/policy/Failure bit/root ACL rollback
  PASS; два собственных файла сохранены. Queue0/GAP null/strict resume/same boot
  и unchanged old state проверены read-only. исходный USN PID без изменений.
- Exact same-snapshot trace: первый доступный controller clean heartbeat
  имеет age5.199094 s (API evaluation age5.0213 s) при operational limit5 s.
  Все остальные admission conditions true: current cache, configured/policy/SACL,
  context, backlog0/no GAP/error, healthy continuous USN. Refusal происходит
  исключительно на age gate до reservation/dispatch. Причина дополнительной
  latency UNKNOWN; неисправность Windows collector не объявлена.
- Следующий same-scope проход 04:00–04:25 UTC — только два DELETE прежних
  собственных файлов. Operational timing6 s перед witness /10 s перед dispatch
  учитывает измеренный доступный снимок; engine identity60/time window2/full
  historical coverage, prior FileId45/native57 и cache age0–5 s неизменны.
  Никаких новых CREATE/WRITE/RENAME/503/поколения. Failure retain / final STOPPED
  и original rollback сохранены. Independent focused review Critical/Important0.
  RED operational timing check → GREEN; actual age boundaries7, admission/chain/
  rollback32, post-coverage11, scope/complete-chain24 и PS parse/Python compile PASS.

### Десятый проход: оба DELETE и чистое историческое покрытие подтверждены

- 04:00–04:25 UTC: native DELETE A в 04:07:44.540 UTC и B в 04:07:46.242 UTC
  PASS, разные согласованные компьютеры/доменные SID, SMB, оба локальных
  дочерних процесса завершены. Total60 операций /1015 bytes. Queue0/GAP null.
- Audit STOPPED подтверждён 04:08:21 UTC, rollback 04:08:25 UTC: исходные
  SACL/policy/Failure bit/root ACL восстановлены, собственная папка удалена.
  Helper второго ПК удалён с exact owned hash guard, без recursive deletion.
  Strict bookmark resume/same boot и untouched old protected GAP state PASS.
  исходный USN PID/конфигурация/cadence и MVP-005 без изменений.
- Read-only реальные engine preconditions для каждого DELETE: complete chain1,
  PROVEN_PRIOR_IDENTITY; identity age36.352 /37.855 s; Access↔USN delta
  0.000011 /0.000743 s. Историческое coverage TRUE: шесть Audit и 55 WINDOWS
  witnesses, bad0, prior/after brackets есть. Два разных Windows client IP.
- Central92 normalized events: 4624=16, 4660=13, 4663=63; SID2, client IP2,
  один FILESERVER source. Actual strict-TLS admin desktop/mobile/reload PASS,
  audit ingest без auth401, legacy USN HEALTHY, остановленный Audit STALE.
  Пока eligible dated aliases0 и текущие изменения UNKNOWN; это не C PASS.
  Следующий штатный volume observation ожидается около 05:07 UTC. До него
  только read-only ожидание, без новой службы/policy/SACL/CRUD или forced USN.
  Обязательны последующие actual HIGH2, точный UI для цепочек4663/4660/4624,
  независимое acceptance review и final exact PR/main CI.

### Реальная приёмка C после штатного volume observation

- 2026-10-14 05:08 UTC: actual admin API возвращает два CORRELATED_HIGH для
  точных DELETE десятого прохода, остальные три изменения текущего окна UNKNOWN.
  Read-only PostgreSQL подтверждает eligible dated alias1 для каждого DELETE;
  ранее доказанные prior identity, полная цепочка и чистое историческое покрытие
  сохранились. Штатный USN inventory не форсировался, confidence rules не менялись.
- Финальный checker связывает ровно один DELETE каждой согласованной учётки
  с утверждёнными source/window/generation, canonical volume и FileId; actor SID,
  account/domain совпадают с исходным 4663. Единственная цепочка требует nonzero
  handle/process, record order, linked 4660 без ObjectName и prior 4624 Type3
  того же host/boot/generation/SID/logon. Возраст FileId36.352/37.855 s,
  Access↔USN delta0.000011/0.000743 s, coverage TRUE (Audit6/WINDOWS55, bad0).
- Windows Security подтверждает две доменные SID, два разных logon session и
  два разных SourceNetworkAddress. WorkstationName отсутствует у обоих:
  имена физических ПК по Windows Security **не установлены**, не выведены из IP.
  Два согласованных компьютера подтверждены native client receipts; второй
  использует точный доменный токен согласованного RDP-сеанса и SMB.
- Actual browser PASS: strict TLS, два точных HIGH change ID, account/SID/session/
  IP и отсутствие workstation, связанные 4663/4660/4624 с точными RecordID,
  два object history с точными FileId/volume, desktop/mobile/reload, overflow0,
  page errors0. Sources показывает USN HEALTHY и остановленный Audit STALE.
  Unauthenticated Audit ingest401, sourceCount1; никакого дублирующего source.
- Негативный сценарий проверен повторно по реальному API после volume observation.
  В исходном согласованном пятом окне/source два scoped Shared-negative WRITE
  имеют AMBIGUOUS и actor NULL. UNKNOWN проверяется отдельно на других scoped
  изменениях того же окна/source; у них actor также NULL.
  Общие классы snapshot (AMBIGUOUS17/UNKNOWN24) не подменяют exact-window checks.
  Rename не объявлен DELETE по одному DELETE AccessMask; actual CREATE→RENAME
  identity proof сохраняет тот же FileId/canonical volume для обоих файлов.
- Независимое focused review финального verifier обнаружило missing account/domain
  binding. RED `WINDOWS_ACCOUNT_DOMAIN_FALSE_PASS` → GREEN сравнение actor с
  исходным 4663 единственной цепочки; wrong-account/wrong-domain отвергаются.
  Actual scope10 + complete-chain14 + account/domain3 PASS; admission/finally/
  pair32, post-coverage11, dispatch lifecycle5, Python compile/Node syntax PASS.
  Повторное source review Critical/Important0. Финальный независимый evidence
  review подтвердил HIGH2, exact Windows fields, обе истории и rollback; уточнено,
  что Shared-negative WRITE доказывает AMBIGUOUS, а scoped UNKNOWN — другие
  изменения пятого окна. Открытых Critical/Important нет; publication CI отдельно.
- Ранее подтверждённый 30 s Audit-only HTTP503 и service restart сохраняют
  byte-identical receipt, один unique event, duplicate0, bookmark и GAP null.
  Replay не повторялся после успешной проверки. Четыре nonadmin роли — viewer,
  analyst, storage_operator, auditor — получили403 на четырёх Audit endpoints;
  чувствительного payload нет, временные sessions отозваны и fixture accounts
  отключены, существующие роли сохранены. LDAP login этим тестом не проверялся.
- Итог60 тестовых файловых операций /1015 bytes. Audit STOPPED/PID0, queue0,
  собственная папка и exact-owned helper второго ПК удалены; исходные
  SACL/policy/Failure bit/root ACL восстановлены. Старое protected state с GAP
  сохранено целиком. Legacy USN service, token/state/scope/cadence не изменялись;
  его исходный PID сохранён. Whole-package SHA legacy collector остаётся
  UNCONFIRMED: ранее сопоставлены только пять critical modules, не весь пакет.
- Installed Audit source `982c442e5760d265efba8e59bd2933b4b20e2889`, wheel SHA256
  `d15e06d01e2af2b03ffbdb0cac6018fa03ea5cbe2d42f8be50d10dcb8e0fd6a5`;
  124 source files сверены byte-for-byte. Central API/worker/Web deployed
  `05eaa7fadd3d6d9c9833f40f6811b68db771a755`, schema0008. Их exact PR/main
  CI (шесть обязательных jobs SUCCESS, Sonar SKIPPED как unconfigured)
  приведён в разделах #29/#30. Эта документация не требует нового deployment.
- Промежуточный docs head `a64dfadac1f511de8a22214bbfce19d197f88a33`:
  run https://github.com/BorisDruzak/storage-console/actions/runs/38510783091,
  six required jobs SUCCESS с этим exact SHA, Sonar SKIPPED. Окончательная
  публикационная приёмка проверяется по exact head и merged-main PR
  https://github.com/BorisDruzak/storage-console/pull/26; self-referential SHA
  текущего документа не вписывается в его собственный commit.
- Private evidence: `c-evidence-tenth-final.json`,
  `c-evidence-fifth-final-negative.json`, `c-final-acceptance-browser.dpapi`,
  `c-final-histories.json`, native receipts, replay и rollback proofs в
  согласованном закрытом evidence directory. Real identities/IP/paths/event
  bodies/screenshots/credentials в публичный Git не опубликованы.
- Границы сохранены: MVP-005 history/RBAC не перезаписаны; SMB/USN journal/GPO,
  Security log retention/size не менялись, FILESERVER не перезагружался.
  5145/WEF/SIEM/версии/массовый аудит не реализованы; исходный USN soak остаётся
  FAIL. После final review и exact publication CI — STOP, без новых live действий.

### Исторические первые попытки CI окончательной публикации C

- Docs commit `06448ccc1417535a9cffade85c49267c9de07fd3`
  (`docs(audit): record two-account live attribution acceptance`) изменяет только
  ledger. Run https://github.com/BorisDruzak/storage-console/actions/runs/38515701582,
  attempt1: five required jobs SUCCESS, windows-pilot FAIL, Sonar SKIPPED.
  Audit84/SCM81 PASS; USN65 PASS/2 FAIL: `test_completed_inventory_does_not_clear_usn_gap`
  увидел USN_BOOTSTRAP вместо CONTINUITY_GAP к wall deadline4 s;
  `test_success_then_blocked_usn_never_keeps_fresh_heartbeat_continuous` не увидел
  USN_STALE к deadline2 s. Код runtime и эти тесты совпадали с accepted source05.
- Один failed-job retry того же SHA, attempt2: предыдущие USN67 PASS, но
  `test_native_usn_runtime_changes_https_lost_ack_and_activity_read` FAIL после
  реальных accepted CRUD и lost-ACK duplicate: pending_count не достиг0 за40 s.
  Пять остальных jobs SUCCESS. Обе неуспешные попытки сохранены; причина
  каждого CI отказа **UNKNOWN**, они не объявлены исправленными или успешными.
  Живое доказательство C не заменяет publication gate; PR не объединялся.
- Дополнительное локальное воспроизведение двух исходных portable functions на
  Windows/Python3.14.3: по три PASS. Это не CI Python3.13.15 и не доказанная RCA.
  Source review выявило диагностические ограничения baseline fixtures:
  wall4/2 s не разделяет poll/production/SQLite/delivery; monotonic×100 ускоряет
  state-retry budget, но не реальные ожидания SQLite; Sender records до ACK.
  Эти факты не доказывают конкретную причину provider failure.
- Test-only commit `bdab761117d8b5cb93175e18bb479d92c47e22a9`
  (`test(collector): expose safe USN runtime failure diagnostics`) меняет четыре
  тестовых файла. При отказе выводятся только fixed codes/kinds, validated
  RuntimeFailure detail, последние24 runtime events/outcomes и один read-only
  queue-count snapshot (SQLite mode=ro/query_only, timeout0.1 s). Реальный HTTPS
  outcome отделён от synthetic lost-ACK outcome; bodies/headers/IDs/paths/token/
  exception messages не выводятся. Ошибка snapshot даёт UNAVAILABLE и сохраняет
  исходный FAIL. Assertions, deadlines и production runtime не ослаблены.
- RED missing diagnostic helper → GREEN; отдельный RED malformed-outcome token
  leakage → GREEN whitelist sanitation. На isolated Python3.13.16: target10 PASS /
  1 Windows-native SKIP; вся USN regression65 PASS /8 native SKIP на Linux.
  Ruff, Python compile, diff check и tracked-source Gitleaks PASS, findings0.
  Independent complete four-file review Critical/Important0. Native acceptance
  остаётся обязательной в новом exact-head/main CI, Linux skips её не заменяют.
- Production API/worker/Web source05 и installed Audit source982 не изменились;
  нового deployment/службы/SACL/policy/CRUD/baseline нет. Финальные publication
  SHAs/run IDs и terminal verdict записываются в PR #26; первые FAIL сохранены.

## Mandatory reporting

- Не ставить PASS по одному CI, без реального подтверждения обязательных live критериев.
- Не подменять отсутствие 4663/SACL «нет событий». Не назначать пользователя по одному совпадению времени.
- Не раскрывать реальные имена, SID, IP, пути, XML Security Events, ключи, токены и operator screenshots в публичном репозитории. Хранить это только в согласованном закрытом месте.
- Не продолжать 5145, WEF, централизованный EVTX архив и версионные копии без отдельной задачи.


## Authorized single-root expansion follow-up

Original STORAGE-AUDIT-001 acceptance remains unchanged. The separately approved
bounded department rollout, exact CI successors, additional data-disk migration
and installed-runtime follow-up are recorded in
[STORAGE-AUDIT-002 ledger](storage-audit-002-ledger.md). Data-disk migration PASS;
corrected runtime exact-SHA CI/installation PASS, permanent Audit RUNNING.
Expanded ordinary-event/history acceptance remains PENDING in that ledger;
bounded quiet-interval checks do not establish full live acceptance.
Existing USN-SOAK failure and immutable original evidence/GAP remain retained.

2026-10-15: operator requested correction of Activity UNAVAILABLE/UNKNOWN and
completion of the separately approved root's live acceptance. Confirmed inventory
scope-transition omission, native/canonical volume mismatch and genuine narrow
SACL coverage failure are recorded in the linked002 ledger. Correction/source
verification does not by itself establish a new live PASS or clear any old GAP.


2026-10-15 recovery follow-up: PR #40 repairs the inventory scope mismatch and
stable-volume ingest aliasing. Full inventory/continuous Activity and genuine
selected-root ordinary-event replay/evidence are now verified in the linked002
ledger. Old Audit GAP/state and all immutable queue backups remain retained;
original001 HIGH/delete acceptance and historical USN-SOAK failure are unchanged.
Final002 queue drain/resource/history witnesses close its bounded live gate PASS,
including the explicit old-generation replay limitation. Both services RUNNING; STOP.

Later2026-10-15 ordinary activity also confirms the fresh-generation path: four
CREATE/WRITE changes linked to two new4663 records and verified in the actual UI.
The earlier quiet-generation limitation is superseded in the002 ledger; actor
remains unconfirmed and two fresh DELETE changes remain UNKNOWN. No operator CRUD.

Publication follow-up: documentation-main CI hit an untraced delivery-thread
failure in the portable USN-proof test; original FAIL is retained in the002
ledger. Diagnostic-only successor requires new exact head/main gates. Live
recovery/fresh-generation evidence and original001 acceptance remain unchanged.

Current-root two-account actor follow-up2026-10-15: four authorized owned-file
operations produced real4663/4660/4624 and USN DELETE chains, but the next ordinary
volume witness exposed INTERVAL_COVERAGE_UNKNOWN for both changes. This is not a
new strong-attribution PASS. The002 ledger records the bounded diagnostic API
needed to explain the historical rejection without direct database access or
confidence overrides. Original001 acceptance, retained GAP and USN-SOAK FAIL remain.

2026-10-15 actor-proof follow-up: coverage diagnostics PR #44 exact head
`5830057a1166df8b14372d6265cbab5ce39c934b`, run38738840435, retained its first
Windows FAIL: native inventory stopped with retryable SQLite contention after
four batches. Other five required jobs passed. The exact contention stage in
that run remains unproven; the run is not retried unchanged or reported PASS.

A separate real-SQLite RED reproduction proves that Delivery loses a completed
HTTP outcome when subsequent local generation/settlement encounters BUSY. The
same controller then returns idle until the old lease expires. The bounded fix
retains one claim/outcome for local finalization before claiming more work,
preserves generation/lease/close fences and network outside the controller lock,
and keeps the original retry deadline. Real writer-contention tests cover all
four outcomes; refresh, reclaim, close and concurrent calls are negative controls.
GREEN regression: Python3.13/Linux/PostgreSQL1069 PASS/91 platform SKIP;
Ruff and strict mypy136 modules PASS. Windows focused88 PASS/4 platform SKIP,
independent focused68 PASS/4 SKIP, reviewAPPROVE; tracked Gitleaks findings0.
This fixes the reproduced defect, without claiming it establishes the original
CI root cause or the historical live coverage failure. Publication and live
actor/UI acceptance remain PENDING; no collector installation or business-file
operation is performed for this delivery fix.


## Post-interval Audit backlog RCA and explicit recheck2026-10-15

- Authenticated coverage explanations of the two existing owned DELETEs proved
  prior FileId identity and complete historical USN brackets. The only failure
  was a pure Audit backlog observation more than16 seconds after both operation
  intervals ended. A later dated healthy collected-through witness covered that
  observation. Current HEALTHY was not substituted for historical evidence.
- Rule windows-security-usn-v2 defers only that fully bounded post-interval
  backlog and requires the later historical drain. It never treats the queued
  row as a healthy bracket. Pre/in-interval backlog, missing/old/future drain,
  policy/SACL/GAP/host/boot/generation/quarantine/errors, USN lag, ambiguity and
  prior limits remain fail-closed. CREATE/WRITE/RENAME do not gain strong actors.
- Added admin+CSRF exact-change, once-per-rule recheck through the canonical
  transaction/job/worker flow, with two-second lock timeout, version fencing,
  conflict rejection and audit log before/after. No actor/confidence override,
  source mutation or broad historical sweep. Raw rows and v1 candidate links
  are retained; detail selects the stored verdict's version without duplicates.
- Real PostgreSQL RED reproduced ACCESS_OBSERVED instead of the eligible HIGH
  and404 for explicit recheck. Focused118 tests PASS, frontend135 tests PASS;
  generated contracts/typecheck/lint/i18n/build PASS. Independent source review
  found no material blockers. Full Python3.13/PostgreSQL regression1140 PASS,
  91 platform SKIP; Ruff and strict mypy138 PASS. Tracked Gitleaks findings0.
  Exact publication gates remain required before rollout.
- A fresh canonical backup, hash-verified encrypted off-VM archive/config and
  full transactional restore in an isolated512MiB database PASS. Namespaced
  central-only rollout preserves disk UUID/bind/image/lock/rollback guards;
  independent ops review APPROVE and21 local guard controls PASS. No business
  file operation, FILESERVER installation/configuration, forced inventory,
  baseline change or direct production data SQL was required for this fix.
- Actual recheck of the same two immutable DELETEs, positive browser acceptance
  and owned empty-directory cleanup remain PENDING until exact PR/main CI and
  deployment. Original acceptance, GAP and USN-SOAK FAIL remain unchanged.


## Two-account mutation-actor live acceptance follow-up2026-10-15

- Scope: same separately approved root, two approved domain users on two
  different computers, one owned synthetic directory. Four authorized file
  operations only: two39-byte CREATEs and two DELETEs,78 bytes total. The second
  participant used an ordinary interactive session. No business file changed.
  No new service/task, protection bypass, SACL/policy/GPO edit, baseline or
  forced inventory was needed for this follow-up.
- Each DELETE followed ordinary inventory. Protected original batch bytes,
  digest and checkpoint prove prior FileId ages4.018363/3.548444 seconds at4663.
  Exclusive verified handles enforced expected FileId/volume/link count/marker.
  Independently retained native/USN/inventory/operator checks:21 per participant,
  including distinct expected SIDs/computers, same source/host/boot/generation,
  compatible4663 DELETE, linked4660 and unique earlier Type3 4624. Both chains
  have native IP/workstation; no DNS/AD inference is needed for these two events.
- The next ordinary inventory closed both aliases. Initial UNKNOWN and later
  ACCESS_OBSERVED/INTERVAL_COVERAGE_UNKNOWN results were retained as negative
  controls, including actual desktop/mobile/reload showing no confirmed actor.
  Grouped Activity rows retain null actor/client/confidence; the exact selected
  event's confirmation panel carries attribution and its evidence.
- Diagnostic PR44 head db4958e24293cf85132c72d26a11d708432f2089,
  run38744543787 and main5c29ccb87bda45676f5873f1b74ba07036dc1b19,
  run38746324694: six required checks PASS with actual exact checkout verification.
  Combined Python3.13/PostgreSQL1094 PASS/91 platform SKIP, Ruff/mypy136 and
  Gitleaks0 PASS, independent combined-tree review APPROVE. Central deployed5c29
  after canonical backup/off-VM/full isolated restore and guarded storage check.
  Original PR44 native Windows failure remains retained, not retried unchanged.
- Delivery PR45 independently reproduced and fixed loss of a completed local
  Delivery outcome on SQLite BUSY. Head5583ec123e9bbf03e0bb311b6c29686afa9fd641
  run38742698371 and main22a53838ce70dfadcbbbed9801779e8051ba7743
  run38744603167: six exact required checks PASS. This does not prove the precise
  contention stage of the original Windows failure.
- Historical coverage API identified the exact actor-gate RCA: pure Audit
  backlog after both operation intervals, with a later dated healthy drain.
  Rulev2 fixes only this case and requires all former identity/continuity/
  health/ambiguity bounds. Current HEALTHY is not borrowed for old coverage.
  Explicit recheck jobs preserve source data, USN history, raw evidence and
  prior-rule links. No broad historical sweep or manual actor override.
- Rulev2 source PR46 head d23a6db67e57457f9fcc0f8951ad9f60748013b7,
  run38752633899 and main3dc445414ed34d6aaf2d2e15fa518faf8cf939fe,
  run38754547522: six required jobs PASS with exact checkout verification.
  Reviewed tree92ebe8aa5fe4ae36ddd49d0acfd16c7f65ab84a2 is identical on
  merged main. Full regression1140 PASS/91 platform SKIP, Ruff/mypy138+7,
  disposable Alembic roundtrip/check, OpenAPI, frontend135/types/lint/i18n/build
  and Gitleaks0 findings PASS. Independent source/rollout/helper reviews APPROVE.
  Central build/preflight/deploy/healthcheck all PASS at that main SHA, schema0009;
  both Windows wheels/configurations unchanged. Sonar SKIPPED/unconfigured.
  Fresh canonical138349648-byte backup/off-VM archive/config/full isolated
  transactional restore PASS,512MiB fixture removed. Disk UUID, actual PG bind,
  image IDs/revisions, deployment lock and rollback guards preserved.
- Exact two-ID admin/CSRF API recheck: both actual DELETEs CORRELATED_HIGH /
  UNIQUE_DELETE_CHAIN with the expected distinct accounts/sessions/computers,
  native client IP/workstation and4663/4660/4624. Both historical coverage
  reports PASS with PROVEN_PRIOR_IDENTITY and the dated cleared backlog.
  Original immutable change payload hashes equal their pre-recheck values;
  a repeated request returned the same COMPLETE job per rule/change, not new work.
- Actual isolated admin browser PASS: both exact events, rulev2, account/SID,
  logon session, native client IP/workstation, identity witness and exact native
  event records/methods rendered. Desktop1440, mobile390 and reload preserve
  the same actors, errors0 and no overflow. Actual screenshots inspected;
  strict TLS/logout/revocation and ephemeral-state removal verified. User-owned
  browser tabs untouched. Earlier observed-access UI remains a negative control.
- Owned empty-directory cleanup PASS after the strict actual-HIGH/UI gate,
  fresh health admission and ordinary USN outbox drain. Verified handles/FileId/
  volume/deadline, no recursive deletion, business files0. Both file receipts
  and all source history/evidence are retained protected; no working file changed.
- Post-cleanup native read-only snapshots: both collectors RUNNING, Audit HEALTHY,
  policy/SACL/readiness complete and fresh,52044 objects/~24.3 seconds. Audit,
  directory and USN queues0, GAP/error/quarantine absent; inventory completed,
  exact scope, cadence3600, selected root present,62464 USN nodes. Both existing
  runtimes/identities/credentials retained; all operation owners QUIESCENT,
  old GAP/full backups retained. No service/policy/SACL mutation during follow-up.
- Resource sample: RAM available~13.24GiB, PG~758MiB/2GiB, API~84MiB/768MiB,
  worker~58MiB/512MiB, Web~6.3MiB/128MiB; noOOM. Root free~17.95GiB. Approved
  data disk250GiB has~230.5GiB available; PostgreSQL remains on its verified
  RW bind/device, not the system disk. No direct production data SQL reads.
- Extra operator logins hit the existing5-per10-minute account limit; actual
  HTTP429 explains a legacy helper's25-second wait timeout. No auth policy was
  weakened, no recheck/CRUD repeated. Bounded RO helper, sealed failure receipt
  and independent session revocation used; final read after cooldown: PASS.
  It includes the exact two original HIGH decisions with unchanged payloads and
  one extra owned-directory DELETE from cleanup. That extra row is checked by
  exact directory FileId/path/source/volume and a two-second receipt window;
  its UNKNOWN/actorNULL is retained. No new API/CRUD/recheck was needed to
  validate the already sealed response. Independent final-evidence review
  APPROVE,14 independent plus19 local negative fence controls PASS.
- CREATE negative controls retain observed-access/actorNULL. CREATE disposition,
  WRITE aggregation bounds and RENAME operation links remain absent; this
  acceptance does not establish universal everyday authorship or fleet rollout.
  A60-second prior FileId bound against3600-second ordinary inventory still
  restricts eligible events. Original001 acceptance, old GAP, backups/state and
  USN-SOAK FAIL remain unchanged. Real identities/evidence/plans stay private.

- Bounded two-account/two-computer DELETE follow-up live gate: PASS. Source/CI,
  deployed runtime, actual native/API evidence, positive and negative browser
  controls and cleanup are distinguished above. No broader readiness or other
  operation author claim. STOP after publishing this acceptance record.


## Final publication recovery-test gate2026-10-15

- PR47 original head9cceb764a01c59f588dff9da944ac093523eafe2,
  run38758910160: five required jobs PASS; Windows FAIL at the portable recovery
  test after writer-lock release,91 other tests in that step PASS. The failing
  assertion hid worker/fatal diagnostics. Its exact runtime failure cause remains
  UNKNOWN; no production defect or scheduling RCA is claimed. This run is retained
  and is not retried unchanged.
- Controlled real-SQLite RED: a six-second retry scheduling gate inside the
  existing30-second operation budget fails the former four-second assertion with
  a live worker and no fatal failures. The fixture now observes actual BUSY,
  rolls back the real writer, then requires a new heartbeat and its committed
  local ACK by the same batch ID, live worker, no fatal diagnostics and graceful
  host exit0. A35-second test guard does not alter the runtime30-second deadline.
  Existing fatal/deadline/stop negative controls remain. Failure output includes
  bounded safe worker/host/stage/elapsed/progress diagnostics.
- Atomic test commit d83b84bc683bd7e68b8e9a0fd168d25eaa512c83 changes only
  test_runtime_recovery.py. Focused Windows50 PASS, Linux41 PASS/9 platform SKIP;
  after final same-batch-ID strengthening, the full modified file21 Windows PASS.
  Ruff/mypy138/diff check and Gitleaks0 PASS. Independent final test-blob review
  APPROVE. Production code/configuration and the accepted live evidence are
  unchanged; no new deployment, live operation, service or policy change.
- The test commit is integrated normally into PR47 together with these append-only
  acceptance records. The previous failed head/pin remains retained. Revised
  exact head/main CI is required before publication; no force push/history rewrite.


## Final publication localhost HTTPS fixture gate2026-10-15

- PR47 revised head94c256177ffdb1ea66806e177a38d0669db65461,
  run38762743706: five required jobs PASS; Windows recovery/SCM step PASS,
  final native USN/HTTPS/Activity step FAIL. The final API correctly returned
  UNAVAILABLE/UNKNOWN: proof age16233ms exceeded the unchanged15000ms bound,
  despite general source health. This failed run/pin/log remains retained;
  no unchanged-SHA rerun or freshness relaxation.
- The shared test HTTPS server bound only IPv4 while its origin and verified
  certificate used localhost. The native resolver attempted IPv6 first. A real
  local TCP probe measured2086ms through localhost versus16ms through IPv4;
  strict-CA/SNI TLS RED passed IPv4 and failed IPv6 with connection refused.
  This proves a fixture mismatch and a latency contributor. Exclusive causality
  for the original CI expiry is not claimed.
- The fixture now binds only both explicit loopbacks on one port, IPv6 V6ONLY;
  fallback is limited to unsupported IPv6 errors. Unexpected errors, including
  port collision, fail closed. Owned sockets close on partial setup, startup,
  body and shutdown failures. Hostname/CA checks remain strict; production
  transport, freshness limits and all four native Activity assertions are intact.
- Real TLS GREEN11 Windows PASS, including both address families and negative
  lifecycle/error controls; independent reviewer11 Windows PASS and APPROVE.
  The unchanged native Windows USN/HTTPS/PostgreSQL/Activity test1 PASS with the
  repaired fixture. No production/file/service/policy/deployment operation.

- Atomic fixture commit b0543be1b02a62d1406d5ed4e0b47ff6e75f5161 contains only
  the HTTPS fixture and its regression tests. Focused Windows61 PASS, Linux
  deployment63 PASS, Ruff, Linux-target mypy138 and deployment mypy7 PASS;
  Gitleaks0 findings. Independent source/evidence reviews APPROVE. Full
  PostgreSQL regression and exact revised head/main CI must pass before STOP;
  immutable receipts and final run links are published through PR47 metadata,
  keeping the source and documentation pinned during CI. No runtime deployment.


## Native heartbeat publication follow-up2026-10-15

- PR47 head27d3c2f95c9fe268ffd19b1b7d392115aedeac72,
  run38766628203: all six required jobs PASS, actual checkout verified in each;
  Sonar SKIPPED/unconfigured. Merge2e6e6f18c1476296e9931e1c0b1918d1d8274606
  has the same reviewed tree. Its main run38768425593 has five required jobs
  PASS and Windows FAIL; this failed pin/log is retained without unchanged retry.
- The native queue-pressure fixture stopped on inventory completion and empty
  outbox, then required two committed heartbeats. In this actual failure the
  runtime lifetime was below3.42seconds, shorter than the configured5-second
  second-heartbeat interval; the first heartbeat was committed successfully.
  Source and timestamps establish premature test shutdown. This is not a new
  production runtime, delivery, actor or live-evidence failure.
- Controlled native RED with a45-second test heartbeat interval reproduced the
  old predicate's one-versus-two committed heartbeat failure. The10-second
  local probe passed and is retained as such, not presented as RED. The revised
  fixture observes completed inventory, two committed heartbeats for the exact
  synthetic collector, then a read-only empty-queue snapshot before shutdown.
  The same45-second case is retained alongside5seconds as regression coverage.
- Existing60-second observation deadline, shutdown5seconds, queue high-water,
  one lost inventory ACK/one duplicate,11 objects, checkpoint revision6, no
  runtime failures and bounded event history remain required. Safe failure
  diagnostics include elapsed/interval/counts/runtime state. No production
  source, settings, installed wheels or live operations change; the accepted
  actor evidence, cleanup, original001 gate, old GAP and backups remain intact.

- Native Windows GREEN: both5/45-second heartbeat cases plus the unchanged
  USN/strict-HTTPS/PostgreSQL/Activity test3 PASS. Ruff, Linux-target mypy138,
  compile/diff checks PASS. Independent exact test-blob review APPROVE.
  Final evidence review, tracked-source secret scan and new exact head/main CI
  remain required before publication/STOP. Final immutable receipts/run links
  are published in the follow-up PR metadata, keeping the candidate pinned.


## Capture child initialization contention follow-up2026-10-15

- PR48 head154ed1df4fdfe60d7ca4d556176ef6f059611189,
  run38771119240: six required jobs PASS with exact checkout verification;
  backend1152 PASS/92 platform SKIP. Same-tree merge/main
  d35e94cd584bef9e2d279a2118045ca898db58ca, run38772616990:
  five required jobs PASS, Windows FAIL (one failure/93 PASS in the SCM step).
  The failed pin/log remains retained, not retried unchanged. Sonar is separately
  SKIPPED/unconfigured.
- New actual trace identifies retryable SQLite BUSY5 during the installed child's
  Outbox constructor, at PRAGMA synchronous=FULL. Blanket OutboxError handling
  returned STATE_MISMATCH; inventory never began, and its next attempt was delayed
  by the normal3600-second schedule. This differs from the repaired premature
  heartbeat test shutdown. Diagnostic heartbeat count0 was an unmeasured default
  because inventory never completed, not evidence that no heartbeat committed;
  the test now reports null for that unmeasured value.
- Real SQLite RED: the original worker blob from the failed exact main still
  returned STATE_MISMATCH after a real exclusive writer was released. The narrow
  child startup repair retries only BUSY/LOCKED for outbox opening and credential
  binding, revalidating protected state each time. STOP/control starts before
  initialization and is checked before capture. Unsafe/schema/identity/binding
  failures remain fail-closed; auth suspension/checkpoints/credentials are intact.
- The30-second budget limits starting another retry. An already-started
  constructor has multiple configured SQLite statement waits and can finish
  later; no hard30-second constructor guarantee is claimed. The unchanged parent
  process/Job lifecycle remains the hard cancellation boundary. Waits are
  cancellable. No common Outbox API, schema, journal or timeout setting changes.
- Final targeted Windows25 PASS, including actual installed-wheel BUSY/unlock
  capture and cooperative STOP while still locked (exit0), plus prior Job/crash,
  bad-input and startup controls. Independent Windows15 PASS and source review
  APPROVE. Related Linux26 PASS/11 platform SKIP; unchanged native Windows
  USN/strict-HTTPS/PostgreSQL/Activity plus5/45-second runtime cases3 PASS.
  Ruff/mypy138+7/diff checks and deployment63 PASS. Full PostgreSQL regression,
  final evidence review, secret scan and new exact head/main CI remain required;
  final immutable receipts/run links are published through follow-up PR metadata.
- This repair is verified in source and an isolated installed wheel. No new
  FILESERVER package, service, policy/SACL, USN state or live file operation is
  applied. The accepted two-account/two-computer actor gate on central3dc4454 and
  its existing Windows packages remains unchanged. Original001 acceptance,
  old GAP/state/backups, business history/RBAC and the earlier USN soak failure
  remain intact. Publication does not imply a new production collector rollout.
