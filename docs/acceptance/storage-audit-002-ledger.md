# STORAGE-AUDIT-002 — bounded single-root rollout ledger

Status: A/B/C source PASS; data-disk migration PASS; department live rollout IN_PROGRESS.
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

## A source acceptance / B resource admission

- PR31 merged. Exact head 5910e666f0e422dbb8a33475ee5cc4aec6678a96 run38563646555
  and main 14c9d42546acaf0cca34f488cab15953f6ca47aa run38565123890: six required
  checks PASS; Sonar SKIPPED by external configuration, not Quality Gate PASS.
  Native Windows groups 14 + 104 + 81 + 97 + 1 PASS. Task2 closure regression
  46 PASS / 5 platform SKIP. No FILESERVER deployment acceptance inferred.
- Existing-schema backup restored in an isolated PostgreSQL16 container limited
  to 512 MiB, matching recorded counts/schema. First disposable attempt failed
  because public schema already existed; corrected owned-fixture cleaning only.
  Production was not restored or stopped; off-VM encrypted archive remains.
- B RED→GREEN: seven admission/pool cases; excess heavy request cannot write a
  receipt, heartbeat reserve remains available, replay accepts exactly once.
  Exception/cancel/disconnect/oversize release the admission slots. Ten pooled
  connections are the maximum per process, with finite three-second pool wait.
- Resource verification RED eight cases; GREEN backend/deployment focus69 PASS,
  Ruff and strict application/deployment mypy PASS. Actual cgroup/SQL proof is
  added to disposable production smoke. Enforced production rollout still pending.
- Additional bounded read-only SACL timing helper timed out; cause UNKNOWN and no
  throughput/readiness claim. Fresh short service read found Audit stopped and
  old USN running unchanged; exact helper process selection found no remaining
  child. Do not blindly repeat the same diagnostic or treat it as positive proof.

## B independent review and isolated runtime proof

- Full pre-review frozen backend regression 943 PASS / 86 platform SKIP. Fresh
  independent review reproduced two Important issues: Nginx buffered before
  admission, and cancellation released a permit while a sync handler still held
  its batch. The actual pinned-runtime reproduction left three blocked handlers
  under a two-slot bound; the original async cancellation stub did not cover it.
- RED→GREEN: no-buffer ingest plus HTTP/1.1 forwarding, and cancelled sync workers
  retain a strongly referenced bounded child/permit until completion. Incomplete
  uploads can still cancel. Body-limit errors/disconnects do not leak permits.
  Canonical deployment healthcheck now verifies resources, including a negative
  case. Repeat independent review found no remaining Critical/Important; focused
  independent rerun 61 PASS. Full post-review backend 944 PASS / 86 platform SKIP,
  68 upstream warnings; deployment/admission focus71 PASS, Ruff, mypy126 + strict
  deploy7, OpenAPI and staged Gitleaks PASS (zero findings). Exact-SHA CI pending.
- Actual owned disposable production Compose proof PASS: enforced cgroup memory
  and zero swap, SQL settings, real HTTPS paused Content-Length/chunked third
  uploads rejected before body completion and without receipts, strict TLS,
  real browser authentication/collector lifecycle and isolated backup/restore.
  Initial fixture build failed because host buildx was absent; direct runtime
  build and read-only buildx diagnostic identified it. The owned fixture used
  supported legacy builder fallback; no production Docker changes were made.
  Candidate fixture provenance is separate from upcoming exact-head/main CI.
- Operator disk screenshot does not allocate its unused data disk to PostgreSQL.
  Protected exact-disk migration/rollback plan and restored off-VM backup are
  prepared. Operator separately approved that exact additional-disk plan; disk
  writes and live rollout remain pending. Source acceptance does not imply live.

## B merged-main failure and test observation follow-up

- PR32 head 9ed7e3354e285761702cb1762b61dde66c6bff93 / run38577118541:
  six required checks PASS; Sonar SKIPPED. Merged main
  cf16928423c1c58026f1f454351871ab7ee11a17 / run38578636658 remains FAIL.
  First native attempt passed groups 14 + 104 + 81 + 97, then Activity returned
  UNAVAILABLE instead of COMPLETE. Its freshness cause is UNKNOWN; no threshold
  or continuity requirement is weakened. Five other required checks PASS.
- One controlled rerun again passed those groups, then the test's writable
  queue observer competed for SQLite BEGIN IMMEDIATE and failed STATE_UNAVAILABLE.
  This observed lock failure is distinct from the first attempt's quality failure.
  No repeated blind rerun or live rollout follows a failed merged-main gate.
- RED: a reserved SQLite writer blocked the existing writable observer. GREEN:
  use the established read-only observer pattern, retry only BUSY/LOCKED inside
  the existing bounded wait, propagate other errors, and preserve database bytes.
  Sanitized post-response diagnostics expose proof age and bounded delivery timing
  without identities, paths, tokens or cursor fingerprints. All COMPLETE,
  CONTINUOUS_SINCE_BASELINE and 15-second validity assertions remain intact.
- Test-only follow-up: focus26 PASS, frozen full regression947 PASS / 86 platform
  SKIP / 68 upstream warnings; Ruff, strict application mypy126 and deployment
  mypy7 PASS. Fresh independent review: no Critical/Important findings, independent
  focus6 PASS. Exact native head/main gates remain pending.
- The earlier read-only timing timeout was isolated to an oversized SSH stdin
  line; bounded framing completed a 2,000-object sample without read errors or
  service changes. This is timing evidence only, not full-tree SACL readiness.

- PR33 head b22d439529a061eaa2ed0293ab234cf56b24f8af / run38587379983:
  six required PASS, Sonar SKIPPED; native14 + 104 + 81 + 97 + 1 PASS.
  Merged main d172a8a726bbe1e4369be25db003e2f13b904139 / run38588737929:
  five required PASS, native FAIL at Activity quality; preceding groups all PASS.
  Read-only observation did not report the previous writer-lock failure. Quality
  RCA remains UNKNOWN because pytest shortened the diagnostic assertion repr.
- RED→GREEN: an actual failing subprocess pytest case proves complete sanitized
  JSON survives captured stdout. Emit that existing bounded snapshot on assertion
  failure; production and all acceptance operands remain unchanged. Focus23 PASS,
  independent focus7 PASS; no Critical/Important findings. New exact CI pending;
  no formatting, migration, SACL/policy or service changes inferred from tests.

## B source closure / C directory contracts

- PR34 exact head47f5e6ab70cfda9dca8adc6b5aef7d05f6eb436b / run38590951155
  and merged main6422cc139263033af1d66f2212033748ef0c4d19 / run38592281935:
  six required checks PASS, Sonar SKIPPED. Native groups14 + 104 + 81 + 97 + 1
  PASS on both. Historical failed runs and UNKNOWN quality RCA remain recorded;
  this exact successor establishes B source acceptance, not a causal claim.
- Additional owned local Windows/Python3.13.15 installed-wheel NTFS→HTTPS→real
  disposable PostgreSQL→Activity test1 PASS (83.21s); production mutations NONE.
  Temporary tunnel closed. Linux-target mypy126 + deploy7 and Ruff PASS; default
  Windows-target mypy sees pre-existing POSIX-only platform attributes, so it is
  not represented as a passing supported deployment-target check.
- Task3 closure focus23 PASS. Task4 started on exact B successor. Initial RED
  absent directory contracts → GREEN17 typed cases: finite pages/counts/TTL,
  explicit incomplete state, source/domain/SID boundaries, disabled users and
  complete PTR/forward/unique-computer witnesses. Directory objects grant no role.
  C persistence, collection, UI, independent review and exact CI remain pending.

## C candidate verification

- Additive revision0009 keeps native audit rows/digests immutable and indexes
  separate IP/directory observations. Paged collector delivery uses signed/sealed
  machine Kerberos, bounded child jobs, cache and encrypted independent queue.
  Current directory names do not alter historical actor/confidence or Web roles.
- Independent review found five Important defects: regex domain split, missing
  numeric enabled proof, missing terminal snapshot-byte reserve, collector-rotation
  index scan and directory capability exposed through ordinary collector listing.
  All received focused RED→GREEN regressions. Packaged PowerShell AST/installed
  wheel and owned deadline/stop tests8 PASS; PostgreSQL EXPLAIN verifies collector
  equality in latest indexes with zero obsolete-history rows filtered.
- Backend frozen candidate1003 PASS/88 platform SKIP; full successor verification
  after the last RBAC/native cases is pending. Source/read/migration22 PASS;
  Web135 PASS, focused desktop/mobile enriched audit browser1 PASS. Ruff and
  Linux-target mypy135 PASS; TypeScript/i18n/API generation/build PASS.
- Actual isolated production Compose acceptance PASS: strict TLS/auth/browser,
  ingest refusal, cgroup memory/swap/SQL budgets and backup/restore. Fresh current
  schema0008 backup and off-VM encrypted hash/decrypt verified; independent bounded
  PostgreSQL restore PASS with matching counts and no production writes.
- Exact disk baseline matches approved250GiB target; read-only migration guard
  PASS. Disk formatting, DB cutover and permanent department rollout not executed.
  Final independent C source verdict APPROVE: fresh34 PostgreSQL/source cases,
  prior41 native/backend and7 Web cases independently PASS. Exact head/main CI
  remains required before disk apply and production rollout.

## C exact source acceptance and approved data-disk migration

- PR35 exact head0a825a5c1546f24e04751c313266f24c11bc4bf2 / run38609971123 and
  merged main927e4c5107785765b5040f571dd6b9cf6f119014 / run38611708662:
  six required checks PASS; Sonar SKIPPED. Both native groups
  14 + 41(directory) + 104 + 81 + 97 + 1 PASS. Independent source review APPROVE.
  Final frozen backend1003 PASS / 91 platform SKIP / 74 upstream warnings;
  Web135 and desktop/mobile Playwright14 PASS. Ruff, supported Linux-target
  mypy135 plus strict deployment7, OpenAPI/API generation, TypeScript, i18n,
  production Compose and secret scan PASS. Historical B failures remain recorded.
- Installed main wheel SHA256
  3659d4202360b52e481d22ca7456c29280a68082d14e23545bb877a0536406b5;
  selected packaged module bytes match exact merged main. Central revision is
  927e4c5107785765b5040f571dd6b9cf6f119014; schema0009.
- Operator-approved additional250GiB disk migration PASS. Fresh identity/blank
  guards, independent protected-helper review and restored off-VM backup preceded
  the single formatting operation. UUID-mounted data filesystem; original system
  disk and stopped original state retained. Four writers were proven quiescent.
  Full old/new manifest:1565 files / 725702501 bytes, equal SHA/size/mode/owner/group.
  SHA256 fa1ef7f3c22754e114207a3cb6b809d5b5d58480990c40e7faf0e0f9e3ac5bfd.
- Canonical deployment/strict TLS/browser verification PASS. PostgreSQL actual
  data mount is on the approved new filesystem. Every historical table count
  remains at least its closed pre-stop baseline; native evidence and GAP records
  retained. Free data-disk bytes248919089152 (about231.8GiB). Enforced memory/swap
  ceilings: PostgreSQL2048/API768/worker512/Web128MiB; no OOM. Follow-up read at
  2026-10-14T19:00Z confirms data mount and healthy running containers, about
  13.7GiB VM memory available. Rollback must retain new writes/schema and cannot
  silently replace current history with the stopped old copy.
- Live department rollout is separate from this migration acceptance and remains
  in progress. No synthetic production CRUD, content capture or GPO write.

## Live bootstrap and readiness performance follow-up

- Independent protected SACL/lifecycle/enrollment helper reviews APPROVE. Fresh
  metadata scan51988 objects; read-only signed/sealed directory preflight208 users.
  Narrow selected-root11-principal Success Write/Append/Delete SACL and local
  FileSystem Success policy applied. DACL/Owner/Group, Failure and GPO unchanged;
  all six governing GPO audit definitions checked read-only. Full-tree proofs
  initially PASS29.696/29.901s against the unchanged30-second deadline.
- USN exact-main stopped-runtime extension PASS: prior queue bytes/digests,
  credentials and old cursor/journal preserved; protected backup and immutable
  transition receipt retained. Restarted with two roots; fresh readonly queue0,
  nodecount62342, continuity codeNULL. Independent Audit generation/state initialized;
  old state/GAP retained. Machine-only directory collection/delivery has no local
  collection/delivery error or backlog; no operator password was installed.
- Actual service readiness remains unaccepted: OBSERVE with
  AUDIT_READINESS_UNAVAILABLE. Audit explicitly STOPPED for correction; USN remains
  RUNNING. Profiling reproduces AUDIT_READINESS_INCOMPLETE at30.0009s after51229
  objects, with11.79s ancestry work. The same installed-main readonly probe can
  complete near29.9s; there is insufficient timing margin. No deadline, proof
  freshness or configured/HEALTHY requirement is weakened.
- RED8 to GREEN36 focused cases for reuse of typed Win32 binding and bounded256
  immutable SID-byte decoding. Every current parent/leaf attribute, ACL, ACE mask,
  SID validity and length still checked; failed conversion is not cached. Read-only
  in-memory candidate diagnostic complete51988 proof22.375s; no deployment/gate
  claim from that diagnostic. Fresh full regression, independent review and exact
  CI remain required before restarting Audit with the corrected package.
- Repeated isolated browser checks reached the existing5-login/10-minute account
  rate bound. Normal window expiry is awaited; no throttle/reset/policy bypass.
  A real strict-TLS Sources-detail check confirms the new directory component and
  honest NOT_CONFIGURED/STALE pre-start state. Final role/name/live checks pending.

- Performance correction source commit6891130e3d3c0976da0221547fcd69ef8c3a9dd6:
  frozen full backend1011 PASS / 91 platform SKIP / 74 upstream warnings (377.97s),
  focused64 PASS, Ruff, supported deployment-target mypy and OpenAPI PASS; public
  source Gitleaks zero findings. Independent source verdict APPROVE, with actual
  owned local Win32 SID/attribute fixtures. Exact new head/main CI pending.
  Local combined focus initially lacked TEST_DATABASE_URL for one stored-heartbeat
  replay test; that environment setup error is separate from the passing full
  disposable PostgreSQL regression and is not represented as a product failure.
- Normal login window expired; exact prior Audit API registration disabled PASS.
  One enabled scoped Audit registration remains; prior history and user roles
  retained. Audit service remains STOPPED pending the corrected installed package;
  USN remains RUNNING. No automatic baseline reset or history deletion.


## Readiness cadence correction

- PR36 exact head79457f5a7e16afd85909a56ed7b4491d7ca8ef4a / run38624122965
  and merged maindd90de4499a23f4f2652e26b83c58328d16ff67a / run38626465344:
  six required checks PASS; Sonar SKIPPED. Both Windows groups
  14 + 41 + 104 + 81 + 97 + 1 PASS. Corrected installed package remains pending;
  no source-only result is represented as department live acceptance.
- Deterministic RED3 reproduces an additional scheduling defect: sleeping30s
  after a22s scan lets the previous proof age reach74s before the next valid
  proof is published. GREEN schedules the next complete probe from its start;
  failure/nonfinite/backwards-clock paths retain30s backoff. Deadline30s and
  freshness60s remain unchanged. Current ancestry/policy/SACL are never cached.
- Focus69 PASS; fresh frozen full backend1016 PASS / 91 platform SKIP / 74 upstream
  warnings (375.34s). Ruff, mypy135 plus strict deploy7, OpenAPI and diff check PASS.
  Independent cadence review APPROVE, including30s boundary and clock failure
  fixtures. New exact head/main CI required before corrected package installation.
- Separate protected version/lifecycle installation helpers reviewed APPROVE.
  All four prior owner journals must be QUIESCENT; both SACL and lifecycle mutexes
  are acquired in one order. Child timeout cannot incorrectly publish QUIESCENT.
  Target is only a new Audit runtime; old USN code/PID and Audit state/generation
  are preserved. No new SACL/policy/GPO change or baseline reset.
- Current read-only Security bookmark verification PASS, positive remaining record
  margin; original20MiB channel setting untouched. VM follow-up: about13.6GiB
  memory available, no container OOM, PostgreSQL mount still on approved data disk.

## USN regression witness correction

- PR37 head7753d09c3ac3aef4a60edbbccbee26cf8261763d / run38629369287:
  five required checks PASS, windows-pilot FAIL; Sonar SKIPPED. Windows Audit109,
  directory41 and SCM/runtime81 PASS. USN96 PASS / 1 FAIL: completed-inventory
  GAP test observed delivered BOOTSTRAP while GAP was already durably queued.
- Controlled RED reproduces the failure by delaying the first transport ACK.
  GREEN checks the latest durable heartbeat through a closed read-only SQLite
  connection after completed inventory, retaining exact CONTINUITY_GAP and gap
  cursor assertions. ACK is released and threads joined in finally. Production
  USN behavior, delivery contract and continuity requirements are unchanged.
- Focused regression126 PASS; final focused5 PASS, Ruff and diff check PASS.
  Independent review APPROVE; negative mutations removing GAP or replacing its
  cursor are detected. Frozen full regression1016 PASS / 91 platform SKIP /
  74 upstream warnings (394.57s); global Ruff, supported Linux-target mypy137
  and public-source secret scan PASS. New exact head/main CI required.

## Finite native delivery witness

- PR37 final head649be2d5792043a5ea0a5c25e09f7184a1274cb1 / run38633163428:
  six required checks PASS, Sonar SKIPPED. Native groups14 + 41 + 109 + 81 + 97
  + 1 PASS. Merged main1798af144854a5acf7a2c0880c8a584b461d285e /
  run38634602404: five required checks PASS, Windows FAIL in the unchanged native
  USN-to-HTTPS integration at queue_drained. Groups14 + 41 + 109 + 81 + 97 PASS.
  Audit installation remains BLOCKED on exact main CI; no gate bypass.
- Exact delay cause UNKNOWN: successful native changes/lost-ACK replay preceded
  the failure, but pytest shortened the runtime/queue diagnostic. New failure
  output prints the full bounded sanitized runtime witness, never payloads.
- Controlled RED: globally-empty polling rejects acknowledged closed work when
  the active producer adds another heartbeat. GREEN closes one sequence watermark
  after accepted_changes and requires every earlier batch to disappear by ACK;
  all domains/states count, including leased/quarantined work. Retryable reads
  never mean success. Future batches do not change that finite requirement.
- This is a finite delivery witness, not global empty-queue or latency acceptance.
  The original40s deadline, strict four Activity freshness/continuity reads,
  lost-ACK/duplicate and scope/privacy checks remain unchanged. Production code
  and collector configuration are unchanged. Targeted65 PASS / 4 native SKIP;
  portable witness3 PASS, global Ruff and Linux-target mypy137 PASS. Independent
  review APPROVE:43 PASS / 4 SKIP, leased-batch witness and negative mutations
  reject pending-only/global-empty predicates. Public source secret scan zero
  findings. New exact head/main CI required before installing Audit.
