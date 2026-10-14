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
