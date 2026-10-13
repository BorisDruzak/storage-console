# STORAGE-AUDIT-001 — журнал промежуточной приёмки

Задача: docs/tasks/storage-audit-001-windows-security-attribution.md

**Статус:** A IN_PROGRESS → B PENDING → C BLOCKED (отдельное разрешение отсутствует).
PASS ещё не объявлен; следующий этап не начинается до предыдущего PASS.

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

GATE A: IN_PROGRESS — full regression, native exact-head CI и exact merged-main CI pending.
GATE B: PENDING — не начинался.
GATE C: BLOCKED — нет отдельного разрешения на новую службу, pilot root, SACL/policy и CRUD.

## Baseline (каждый раз перепроверять)

- Baseline documentation main перед созданием задачи: 34d49cc5c1aa42953ce3d400ff9e9ddc448bcac9.
- Issue #22 (MVP-005 History/Statistics): OPEN на момент подготовки; ожидаются возможные конфликтующие изменения Activity/RBAC. Сверять самый новый main/PR.
- Existing Windows USN Collector после USN-SOAK-001: source eb6312bd431f40ff86e522c621c41e885defc454 по опубликованному отчёту.
- Existing central API во время исходного USN soak: 22667a67b6c5faceb914a114197e92b3a7bac2b7; перед deploy проверить фактическую версию заново.
- Original USN-SOAK-001: 72h FAIL, 5 service crashes. Никаких выдуманных утверждений о long-term PASS.
- New Security Audit Collector: NOT INSTALLED / NOT ACCEPTED.
- Real audit policy/SACL preflight: NOT PERFORMED.
- Two users / two PCs live test: NOT AUTHORIZED / NOT PERFORMED.

## A — read-only preflight и независимый Security Collector

GATE A: PENDING

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

GATE B: PENDING

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

GATE C: PENDING / HUMAN APPROVAL REQUIRED

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
