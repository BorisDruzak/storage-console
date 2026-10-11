# MVP-005 — История изменений и статистика файлового хранилища

**Codex task.** Three stages: A (searchable history), B (activity statistics), C (capacity history). Each yields a visible product result in Web Console. **No repeat 72h soak gate**. Run A -> GATE A -> B -> GATE B -> C -> GATE C -> STOP.

## 0. Product goal and factual baseline

The FILESERVER Windows Collector already sends normalized NTFS USN operations via durable outbox and HTTPS. The original USN-SOAK-001 72h trial was FAIL (five service crashes, long outage). Subsequent fixes PR #20/#21 were installed; the report documents only 41.12h without observed new crashes after the last fix, NOT a new 72h PASS. This task is deliberately about delivering missing functional value, while preserving and reporting the known operational risk.

Read these sources at the latest main SHA before editing:
- docs/acceptance/usn-soak-001.md
- docs/acceptance/mvp-003-004-execution-ledger.md
- docs/spec/storage-control-plane-v0.1.md
- apps/api/read/activity.py
- apps/web/src/pages/ActivityPage.tsx
- apps/web/src/domains/models.ts
- packages/shared/models/activity.py
- packages/shared/models/core.py
- packages/shared/ingest/core.py
- packages/contracts/changes.py and packages/contracts/read.py
- apps/api/user_auth/sessions.py
- apps/api/read/routes.py
- migrations/versions/0006_usn_activity_indexes.py
- AGENTS.md and operator/deployment runbooks

Known limitations in main:
- Existing GET /api/v1/activity defaults to last 24h, only windows <=31d, offset <=10,000; no path/filename search or single-file timeline.
- Current ActivityPage collapses similar events within a minute via groupActivity(), which is unsuitable as complete raw history.
- Existing volumes row holds only latest total/free; no historical capacity samples exist.
- Current general read permission covers five roles. Raw Activity paths are visible to roles which have not been explicitly authorized for sensitive department-file history.
- USN coverage is ONLY the approved monitored roots, from its observation baseline onward; neither all departmental shares nor historical pre-baseline operations are established by current data.

## 1. Global constraints and quality

1. Focus on central API/PostgreSQL/Web; **do not modify the installed Windows Collector**, its state, SCM service, USN Journal or operating system. No FILESERVER reboot, no collector re-enrollment, no ACL/SMB/audit policy change, no full disk scan, no touching production files.
2. Do not implement 4663/5145 attribution, SMB/DFS/FSRM, VSS/PBS/PVE/ZFS, content reading, automatic file operations, system diagnostics or additional monitoring. Do not use 72h soak as a prerequisite.
3. Do not pretend to know events before the baseline or during an unproven historical period. The first STORED event timestamp is NOT a proven collector coverage start. Historical completeness must show UNKNOWN unless supported by durable interval evidence. Source downtime does not necessarily prove USN loss: queued journal may be read later.
4. RENAME is ONE logical event; both old/new paths searchable. Null path stays unknown. USN does not identify user or remote client: actor/client/confidence remain unknown. WRITE event count is NOT bytes written. Event count is NOT number of distinct users/files.
5. FileID must be qualified by source and canonical volume. Recycled FileIDs/aliases may require cautious labeling.
6. Volume capacity from native inventory is measured for the WHOLE NTFS volume, not the size of the monitored root or a department; graph labels must say so. Use only real measurements for growth/delta; do not create fake historical points or forecasts.
7. Preserve existing normalized event deduplication, old events, outbox, credentials, auth, strict TLS, migrations and correctness of Overview/Activity. Never delete historical duplicated RENAME from the old failed pilot automatically.
8. Public GitHub must contain no real paths, identities, credentials, private source metadata or raw production evidence. Sanitized fixture paths only.
9. For each stage: failing RED test -> minimal GREEN implementation -> targeted/full regression -> independent security/code review -> fixes and reruns -> exact PR CI -> merge -> exact main push CI -> operator-visible live UI proof -> gate. Separate PR per stage. CI jobs backend/frontend/windows-pilot/compose-smoke/production-smoke/secrets remain enabled. Sonar SKIPPED is not PASS.
10. Central deployment only using approved deployment runbook and operator permissions: verified PostgreSQL backup, off-VM backup confirmation, rollback checkpoint, migrations check/round-trip, strict HTTPS/session/auth, unchanged collector ingestion. If no authorized runtime access, supply exact operator commands and mark LIVE gate BLOCKED until evidence; do not fake acceptance.
11. Record each stage in docs/acceptance/mvp-005-execution-ledger.md: source SHA, PR, CI URLs, deployed SHA, tests, query plans, screenshots/real counts sanitized, role checks, observed UI, rollback, limitations, gate PASS/BLOCKED/FAIL and operator actions.

## 2. Security gate applied FIRST in Stage A

Existing GET /api/v1/activity inherits the common read permission, which is accessible to storage_admin, storage_operator, auditor, analyst and viewer. This currently discloses detailed file paths too broadly. Before adding search/export/top-folder breakdowns:

- Introduce a dedicated read_sensitive_activity permission initially granted ONLY to storage_admin. Grant to other roles only after an explicit user decision and approved per-scope access policy.
- Enforce it on legacy GET /api/v1/activity and ALL new path-sensitive history, object-timeline, statistics, capacity-history and export APIs. Existing Overview/volumes/sources RBAC stays unchanged.
- Unauthorized roles: server 403, no response payload with raw paths. Unauthenticated: 401. Tests for viewer, analyst, auditor, operator and admin. Hide sensitive navigation for forbidden actors; directly entered hash URLs must also fail safely.
- Sensitive path/filename search strings cannot be placed into URL queries, browser hash, server access logs or audit payloads. Use bounded POST JSON read-only search endpoints, authenticated session plus existing Origin/CSRF protection. No file mutations.
- Export is admin-only, audited with user/time/count/source ID but NO raw path in audit log. No-store response. Prevent CSV/Excel formula injection, newlines in cells and unbounded download.
- Do not grant blanket per-department browsing to ordinary user roles. Department-level scoped authorization is out of scope until explicit mapping is approved.

## 3. STAGE A — History of operations and per-file timeline

### Backend

Create typed POST /api/v1/activity/search (or an equivalent consistent path) with:
- source_id; timezone-aware from/to; event types; path prefix or filename/path search against BOTH old_relative_path and new_relative_path; exact canonical volume_identity + file_id pair; optional page cursor; page size 1..100.
- Ability to query ANY historical period containing stored events. Use a bounded per-query window, e.g. <=366 days, with navigation to prior years if present. Do not silently stop at default 24h, 31-day window or offset 10,000.
- Keyset pagination by occurred_at DESC, id DESC with opaque validated filter-bound cursor and snapshot/watermark strategy so equal timestamps, pagination, replays and late arrivals do not repeat or omit rows inside a stable browsing session. Invalid/changed/malformed/oversize cursor -> deterministic rejection.
- Bound Unicode path search, normalize Windows separator, escape LIKE wildcards, use parameterized SQL and indexes; avoid full scans per keystroke. Justify pg_trgm if used, or implement safe indexed path-prefix fallback without elevated extension permissions. Benchmark EXPLAIN on 100k+ synthetic change events.
- Preserve raw one-event-per-row identity and records with path_quality=UNAVAILABLE. No silent groupActivity coalescing.
- Return earliest_stored_event_at / latest_stored_event_at separately from actual verified coverage start. If no coverage interval proof exists, historical_coverage=UNKNOWN with a user-facing explanation.
- Per-object history endpoint by source_id+volume_identity+file_id, paging and time range, with old/new paths, reason, provenance, unknowns. No mixing FileIds across volumes/sources.
- Bounded CSV export for current filters (max 5000 rows/response or equivalent paging), Excel-friendly UTF-8 BOM with formula-safe escaping. Maintain admin-only access and sanitized audit. No file contents.

### Web: «История изменений»

- New visible History view or explicit tab in Activity; the old Activity route remains navigable for authorized admin.
- Period presets today/7/30/custom and older dates; display in Asia/Yekaterinburg by default, respect explicit saved UTC.
- Friendly source picker, type filter, filename/path search, old/new path handling, file identity filter; source UUID is not an operator-friendly primary input.
- Exact rows, timestamps, Russian operation name, path, rename Before→After, provenance, quality and detail panel. Link «История объекта» to source+volume+FileId timeline.
- Unlimited-in-principle traversal of stored history through bounded pages (not offset=10000); forward/back pages and reload preserve filters without leaking search path in URL.
- Clearly show UNKNOWN historical coverage, unavailable path, empty result vs unavailable evidence; no inferred actor/client.
- Navigation access must be role-aware; loading/error/empty/forbidden, responsive/mobile and i18n ru-RU/en-US.

### A RED→GREEN acceptance

- Existing 401/403 exposure fixed for legacy and new endpoints; admin 200.
- Real stored FILESERVER event is searchable in live UI, including one older than 24h if present; otherwise write N/A live evidence and still require synthetic older-than-24h regression.
- Tests for Cyrillic, old and new rename paths, arbitrary wildcard characters, malformed cursor, >10k records, same-time ordering, replay, no duplicate display, per-file history across rename/delete and source isolation.
- CSV formula-injection tests, no sensitive URL/audit data, strict types/OpenAPI/generated clients.
- Exact CI and real authenticated browser evidence; backup/rollback preserved.
- GATE A PASS only after real UI confirmation of useful history without modifying FILESERVER.

## 4. STAGE B — Activity statistics and live charts

Implement POST /api/v1/activity/statistics, typed bounded filters/role/CSRF, SQL-side aggregates. Do not fetch thousands of events to aggregate in React.

Required measures (counts of STORED normalized events only):
- total operations in selected period, by six supported event types;
- time-series per day for 7/30/90/custom days, and distribution by local hour and weekday;
- top N observed directory prefixes by operation count, with an explicit UNKNOWN path bucket; RENAME counts ONCE (document which old/new path is used for primary categorization);
- earliest/latest stored event in range, count coverage and confidence/continuity state when available; do not equate absent data to true zero if historical coverage UNKNOWN;
- source filter; business timezone Asia/Yekaterinburg (UTC option), no mistaken grouping around midnight/DST boundary;
- unique FileId metrics only if qualified by source/volume and clearly named object IDs, not "unique files" or "users".

Web: a discoverable **«Статистика активности»** page using actual typed API. Show KPI cards and at least THREE real charts: (1) operations by day, (2) operation type distribution, (3) weekday/hour heatmap or equivalent hour chart, plus a top-directory table. Period/source controls, chart drill-down to History if feasible, accessible table equivalents, responsive desktop/mobile and Russian UI. No static/fake figures. An existing lightweight chart library may be added if necessary; no global UI rewrite.

RED→GREEN: replay and rename counted once, Cyrillic and unknown path bucket, multiple sources, exact calendar boundaries around UTC/Asia-Yekaterinburg, 100k-event query plan, authorized vs unauthorized roles, loading/empty/error, Playwright charts on real API. Independent SQL reference aggregates match. Exact PR/main CI and real browser demonstration. GATE B PASS only with nonempty real source and correctly matched numeric series.

## 5. STAGE C — Real historical capacity collection and display

Current volumes table is latest-only. **Do not fake backwards history** from its current value or from WRITE event counts.

### Backend

- Add narrow table volume_capacity_samples with volume_id, observed_at, total_bytes, free_bytes, ingested_at, indexed for volume/time and unique by (volume_id, observed_at) or more precise immutable native source key.
- Store a measured sample in the SAME existing inventory ingest transaction whenever a valid VolumeRecord (total>0, 0<=free<=total) arrives. No Windows Collector changes. Replays idempotent, older out-of-order valid sample may remain in history but must never regress the current volume row.
- No sample for missing/fake/partial values. Preserve original source timestamps. No fabricated pre-deployment backfill or retroactive points from latest-only volumes.
- Add a typed bounded read API by source and canonical volume, time range and resolution, with real observed sample count and quality. Index-aware backend aggregation for longer periods; bounded payload. Role gate as above.
- Compute used=total-free, used_percent and first-to-last NET delta. Do not call it bytes-written, growth of monitored directory or future forecast. Below two measured points show "Недостаточно измерений".
- No new cron, background agents, automatic deletes, event retention changes or collection-frequency change.

### Web

Visible **«История ёмкости томов»** page or distinct Statistics tab:
- volume/source filters and observed total/free/used trend chart;
- net used delta between real first and last snapshot; first/last sample timestamps and freshness/quality;
- explicit notice: this is the entire physical/logical NTFS volume, not the sum of files in currently approved monitored roots;
- one/zero-sample truthful state, not a straight invented line.

RED→GREEN: exact duplicate ingest does not create duplicate sample, distinct valid observations do; older records do not overwrite latest, source separation, invalid/partial values excluded; migration roundtrip, 100k synthetic sample bound and query plan, correct timezone display, real client/contract tests, rollback. Protect existing Overview, USN, change_events and source freshness from regression.

Live acceptance: at least **TWO real scheduled inventory capacity samples** after deployment plotted in the Web UI. If only one exists, GATE C remains BLOCKED until next ordinary scheduled scan (roughly hourly); don't force FILESERVER restart or create files. No 72h soak.

## 6. Stop and final report

After GATE C PASS: STOP. Do not start Windows audit user attribution, broader monitoring scope, ACL/SMB, backups/PVE/PBS or another stability campaign automatically.

Required final report:
- A / B / C PASS|BLOCKED|FAIL and explicit reasons;
- PR, merged main SHA, exact push CI URL and central deployed SHA for each stage;
- real History search + per-file timeline, real Activity 3 charts and counts, real capacity sample timeline and net delta (if enough samples);
- non-admin 401/403 tests, no-path-leak proof, unknown coverage and no-fake-attribution proof;
- migration/backups/rollback, any recorded regressions, outstanding risks from original USN-SOAK FAIL.

The task exists to make previously collected data usable, not to generate endless tests without working screens.
