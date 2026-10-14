# STORAGE-AUDIT-002 — bounded single-root rollout ledger

Status: authorized execution; A IN_PROGRESS, B/C/D PENDING.
Specification and plan: docs/superpowers/{specs,plans}/2026-10-14-storage-audit-002.md.
Production scope and identities remain in the approved private operator design.

- 2026-10-14: operator approved necessary implementation/rollout and emphasized
  bounded Storage Console memory and correct persistent history. Existing audit
  acceptance is not reopened; permanent single-root rollout is separate work.
- Baseline main d95040b19d87ecc0c2e83460bd2d2b75f9592d3f; reused attached managed
  worktree, new branch codex/storage-audit-002-a, clean before new files. Original
  workspace unchanged. Issue22 OPEN, open PR list empty at inspection.
- GitNexus list_repos does not contain Storage Console; verify dynamic source and
  tests directly, no manual group_sync/reindex.
- Private read-only directory and metadata preflight completed; no real values in
  fixtures/public docs. Root exceeds old 256-object readiness bound and is outside
  existing USN scope. Audit remains STOPPED; existing USN running/unmodified.
- Central resource observation: containers currently have no cgroup memory limits.
  Available memory is substantial; disk free is below canonical deployment minimum
  at observation time. No cleanup or runtime mutation yet; deployment headroom must
  be resolved before live rollout. No promise of unlimited disk or history retention.
- Local Python3.14 baseline could not collect tests (ldap3 absent); not a product
  regression. Isolated Python3.13 focus: 28 passed/4 Windows-native skips; upstream
  pyasn1 deprecation warnings retained. No native/full-regression claim yet.
- Ruling: operator explicitly requested execution of the approved written design;
  implementation plan uses inline execution without a redundant permission loop.
  Independent stage review remains mandatory. Cost if wrong: plan changes require
  correction before affected stage gates/deployment.

## Task 1 — bounded readiness, portable verification

- RED: old breadth-first walker consumed the full wide directory before checking
  its first descendant. A complete synthetic 52k walk exceeded the 4 MiB traced
  allocation budget. Both tests fail against committed baseline and pass with
  lazy depth-first enumeration, finite iterator depth/count/deadline and cleanup.
- RED→GREEN: background probe/status independence, startup/stop, scan-start-based
  expiry, exception redaction, exact total budget and late expiry during capture.
  Incomplete/expired proof does not make HEALTHY. Actual negative completed proof
  retains the existing configuration-change GAP behavior.
- RED→GREEN: configured lower budget must not silently use the old default 256.
  First test double omitted Native.sacl and accidentally passed; it was corrected
  to preserve real scope verification behavior, then reproduced the actual RED.
- RED→GREEN: new optional heartbeat diagnostics changed canonical old receipt
  shape without conditional omission. Actual PostgreSQL previous-release receipt
  replay reproduced 409; omission of absent new fields restores 202/duplicate=true
  while retaining previous nullable fields and immutable evidence unchanged.
- Current focus: 63 PASS. Full frozen Python3.13 source regression: 906 PASS /
  85 platform SKIP; 68 upstream warnings retained. Earlier full snapshot 902 PASS
  is recorded separately and is not substituted for the current result.
- Deployment tests 54 PASS; Web 133 PASS, API generation/check/lint/typecheck PASS.
  Focused strict mypy six source modules and Ruff PASS. Native/exact CI PENDING.
- Additional FILESERVER volume API diagnostic timed out; cause UNKNOWN and no
  automatic retry. A short read-only CIM query separately confirmed NTFS and the
  same canonical volume as existing scope; Audit STOPPED/PID0 and old USN same PID.
- Operator screenshot clarified RAM versus disks. Second virtual data disk is
  present, unmounted and has no detected filesystem signature; PostgreSQL remains
  on system filesystem. No disk initialization/mount/migration performed.

## Task 2 — explicit scope transition and independent A review

- RED→GREEN: streamed atomic updates, iterator/capacity failure rollback, duplicate
  identity refusal and unchanged queued bytes. A complete 52k ancestry is staged
  on disk and committed without a width-sized Python group.
- Independent review identified seven Important findings. A real scope commit
  reproduced its own SQLite writer/reader lock after cache spill; transaction-local
  collision/revision reads remove it. The real 52k regression passes under the
  4 MiB traced-allocation budget while preserving the old cursor.
- RED→GREEN: immutable transition backups survive interruption before publication;
  DONE receipts permit later rotation/disable; CLI retry repairs half-written
  config/activation without duplicate roots; default readiness also runs in the
  background with expiry; failed unpublished stages do not accumulate; retained
  producer handles close; changes after the frozen fence remain observable.
- Missing-baseline and old-scope-move counterexamples were checked against source
  and covered by GREEN guards. Extension requires initialized volume baselines;
  staged identities in the old backlog cause refusal. These two guards have no
  separately executed pre-fix RED claim. New-root earlier history stays unknown.
- Journal retention is rechecked immediately before commit, including resume;
  rollover refuses the transition. Published pending stages and historical
  receipts survive for recovery. Existing gaps and credentials remain unchanged.
- Current focused backend/deployment regression 145 PASS / 6 platform SKIP;
  complete strict mypy and Ruff PASS; OpenAPI and staged secret scan PASS.
  Earlier full snapshots 925/86 and 934/86 PASS/SKIP remain separate evidence;
  final frozen full regression 936 PASS / 86 platform SKIP, 68 upstream warnings.
- Owned native NTFS extension and readiness cases were added to Windows CI.
  Native, exact head/main CI and live deployment remain PENDING.
- A fresh existing-schema backup passed pg_restore --list and off-VM DPAPI
  decrypt/hash verification. Writers and history unchanged. Backup integrity
  evidence does not establish restoration acceptance.
- PR31 first exact-head CI 38562589712: Windows readiness assertion failed because
  its test double compared plain and extended path spellings. Changed that
  assertion to filesystem identity; owned local Windows/Python3.14 check PASS,
  Python3.13 readiness focus 64 PASS. Native CI rerun still required. Source
  long-path support remains intact; this is a fixture correction, not a SACL bypass.
