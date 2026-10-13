# STORAGE-AUDIT-001 — журнал промежуточной приёмки

Задача: docs/tasks/storage-audit-001-windows-security-attribution.md

**Статус:** A PASS → B IN_PROGRESS → C BLOCKED (отдельное разрешение отсутствует).
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
GATE B: IN_PROGRESS — начинается с accepted merged-main SHA и повторной сверки Issue #22.
GATE C: BLOCKED — нет отдельного разрешения на новую службу, pilot root, SACL/policy и CRUD.

## Выполнение 2026-10-13 — этап B (code verified, publication pending)

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

## Baseline (каждый раз перепроверять)

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

GATE B: IN_PROGRESS — completed code checks above; publication/deployment pending.

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

GATE C: BLOCKED / HUMAN APPROVAL REQUIRED. Private bounded pilot plan prepared;
exact folder, two domain accounts, two PCs and GPO owner await operator selection.
No new FILESERVER service, synthetic directory, SACL/policy/GPO write or CRUD executed.

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
